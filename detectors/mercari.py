# detectors/mercari.py
from bs4 import BeautifulSoup
import json, re

# 允许在字符之间穿插任意标签/空白的 HTML 级别匹配
def _html_has_phrase(html: str, phrase: str) -> bool:
    # 构造形如:  購(?:<[^>]*>|\s|&nbsp;)*入(?:<...>)*手(?:<...>)*続(?:<...>)*き(?:<...>)*へ
    parts = []
    for ch in phrase:
        parts.append(re.escape(ch))
        parts.append(r'(?:<[^>]*>|\s|&nbsp;|&#160;)*')  # 允许标签、空白、nbsp
    pat = ''.join(parts[:-1])  # 去掉最后一个“允许夹杂”的片段
    try:
        return re.search(pat, html, flags=re.I | re.S) is not None
    except re.error:
        return False

def _norm(s: str) -> str:
    if not s:
        return ""
    s = s.replace("\u3000", " ")            # 全角空格->半角
    for ch in ("\u200b", "\u200c", "\u200d", "\ufeff"):
        s = s.replace(ch, "")
    s = re.sub(r"\s+", " ", s, flags=re.S)
    return s.strip()

def _jsonld_availability(soup: BeautifulSoup):
    for tag in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            data = json.loads(tag.string or "{}")
        except Exception:
            continue
        objs = data if isinstance(data, list) else [data]
        for obj in objs:
            if not isinstance(obj, dict): 
                continue
            avail = None
            offers = obj.get("offers")
            if isinstance(offers, dict):
                avail = offers.get("availability")
            avail = avail or obj.get("availability")
            if not avail:
                continue
            v = str(avail).lower()
            if "instock" in v or "in_stock" in v or "schema.org/instock" in v:
                return "in"
            if "outofstock" in v or "out_of_stock" in v or "schema.org/outofstock" in v or "sold" in v:
                return "out"
    return None

def detect(html: str) -> str:
    if not html:
        print("[MERCARI DETECT] empty html")
        return "UNKNOWN"

    soup = BeautifulSoup(html, "lxml")
    text = _norm(soup.get_text(" ", strip=True))

    # 1) 删除/下架
    deleted = [
        "該当する商品は削除されています。",
        "この商品は削除されました",
        "この商品は出品停止中です",
        "この商品は公開停止中です",
        "ページが見つかりません",
        "商品が見つかりません",
    ]
    if any(m in text for m in deleted):
        print("[MERCARI DETECT] deleted marker")
        return "DELETED"

    # 2) 结构化信号（最快的）
    jl = _jsonld_availability(soup)
    if jl == "in":
        print("[MERCARI DETECT] jsonld=IN_STOCK")
        return "IN_STOCK"
    if jl == "out":
        print("[MERCARI DETECT] jsonld=OUT_OF_STOCK")
        return "OUT_OF_STOCK"

    # 3) meta/link 可用性
    meta = (soup.find("meta", {"itemprop": "availability"})
            or soup.find("meta", {"property": "product:availability"})
            or soup.find("link", {"itemprop": "availability"}))
    if meta:
        val = _norm(meta.get("content") or meta.get("href") or "").lower()
        if any(k in val for k in ("instock", "in_stock")):
            print("[MERCARI DETECT] meta=IN_STOCK")
            return "IN_STOCK"
        if any(k in val for k in ("outofstock", "out_of_stock", "sold")):
            print("[MERCARI DETECT] meta=OUT_OF_STOCK")
            return "OUT_OF_STOCK"

    # 4) HTML 级别“宽松短语匹配”，允许字符间穿插标签/空白
    buy_hit  = (
        _html_has_phrase(html, "購入手続きへ")
        or _html_has_phrase(html, "購入に進む")
        or _html_has_phrase(html, "購入へ")
        or "/transaction/buy" in html or "/transaction/buys" in html
    )
    sold_hit = (
        _html_has_phrase(html, "売り切れました")
        or _html_has_phrase(html, "売り切れ")
        or _html_has_phrase(html, "取引が終了")
        or re.search(r"S\s*O\s*L\s*D\s*O\s*U\s*T", html, flags=re.I | re.S) is not None
    )

    # 打印命中情况用于调试
    print(f"[MERCARI DETECT] html-match buy={buy_hit} sold={sold_hit}")

    # 5) 规则
    if buy_hit and not sold_hit:
        print("[MERCARI DETECT] => IN_STOCK (buy only)")
        return "IN_STOCK"
    if sold_hit and not buy_hit:
        print("[MERCARI DETECT] => OUT_OF_STOCK (sold only)")
        return "OUT_OF_STOCK"
    if sold_hit and buy_hit:
        # 若两者都出现，优先 SOLD（更保守）
        print("[MERCARI DETECT] => OUT_OF_STOCK (both signals)")
        return "OUT_OF_STOCK"

    print("[MERCARI DETECT] no rule matched -> UNKNOWN")
    return "UNKNOWN"








