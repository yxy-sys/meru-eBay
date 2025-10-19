# detectors/mercari.py
from bs4 import BeautifulSoup
import json, re

BUY_REGEX = re.compile(r"購.?入.*(手続|へ|に進む)", re.S)   # 更宽松：允许空白/换行/变体
SOLD_REGEX = re.compile(r"(売り切れ(ました)?|取引が終了|SOLD\s*OUT)", re.I)

def _has_buy_link(html: str) -> bool:
    # 购买动作通常会出现 /transaction/buy
    return "/transaction/buy" in html or "/transaction/buys" in html

def _jsonld_availability(soup: BeautifulSoup):
    """
    解析 JSON-LD。尽量不抛异常，返回 'in', 'out', 或 None。
    """
    for tag in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            data = json.loads(tag.string or "{}")
        except Exception:
            continue
        # 单对象或数组
        candidates = data if isinstance(data, list) else [data]
        for obj in candidates:
            # 可能在 "offers" 或对象本身
            avail = None
            offers = obj.get("offers") if isinstance(obj, dict) else None
            if isinstance(offers, dict):
                avail = offers.get("availability")
            if not avail:
                avail = obj.get("availability")
            if not avail:
                continue
            val = str(avail).lower()
            if "instock" in val or "in_stock" in val or "schema.org/instock" in val:
                return "in"
            if "outofstock" in val or "out_of_stock" in val or "schema.org/outofstock" in val:
                return "out"
            if "sold" in val:
                return "out"
    return None

def detect(html: str) -> str:
    """
    更稳的 Mercari 状态检测：
      - 删除/下架：DELETED
      - 售罄：     OUT_OF_STOCK
      - 有货：     IN_STOCK
      - 无法判断： UNKNOWN
    并打印命中的证据，方便排查。
    """
    if not html:
        print("[MERCARI DETECT] empty html")
        return "UNKNOWN"

    soup = BeautifulSoup(html, "lxml")
    text = soup.get_text(" ", strip=True)

    # 1) 明确的 “已删除/下架”
    deleted_markers = [
        "該当する商品は削除されています。", "この商品は削除されました",
        "この商品は出品停止中です", "この商品は公開停止中です",
        "ページが見つかりません", "商品が見つかりません",
    ]
    if any(m in text for m in deleted_markers):
        print("[MERCARI DETECT] matched: deleted marker")
        return "DELETED"

    # 2) JSON-LD availability（结构化最可靠）
    jl = _jsonld_availability(soup)
    if jl == "in":
        print("[MERCARI DETECT] matched: jsonld=IN_STOCK")
        return "IN_STOCK"
    if jl == "out":
        print("[MERCARI DETECT] matched: jsonld=OUT_OF_STOCK")
        return "OUT_OF_STOCK"

    # 3) meta availability
    meta = (
        soup.find("meta", {"itemprop": "availability"}) or
        soup.find("meta", {"property": "product:availability"}) or
        soup.find("link", {"itemprop": "availability"})
    )
    if meta:
        val = (meta.get("content") or meta.get("href") or "").lower()
        if any(k in val for k in ("instock", "in_stock")):
            print("[MERCARI DETECT] matched: meta=IN_STOCK")
            return "IN_STOCK"
        if any(k in val for k in ("outofstock", "out_of_stock", "sold")):
            print("[MERCARI DETECT] matched: meta=OUT_OF_STOCK")
            return "OUT_OF_STOCK"

    # 4) 灰色“売り切れました”按钮（禁用按钮/aria）
    btn = soup.find("button", string=SOLD_REGEX)
    if btn:
        print("[MERCARI DETECT] matched: gray sold button text")
        return "OUT_OF_STOCK"
    btn_aria = soup.select_one('button[aria-disabled="true"]')
    if btn_aria and SOLD_REGEX.search(btn_aria.get_text(" ", strip=True) or ""):
        print("[MERCARI DETECT] matched: aria-disabled sold button")
        return "OUT_OF_STOCK"

    # 5) 红色购买按钮（文本/aria/较宽正则）
    #    a) 文本命中
    red_btn = soup.find("button", string=BUY_REGEX)
    if red_btn:
        print("[MERCARI DETECT] matched: buy button text")
        return "IN_STOCK"
    #    b) aria-label 命中
    for b in soup.find_all("button"):
        label = (b.get("aria-label") or "").strip()
        if label and BUY_REGEX.search(label):
            print("[MERCARI DETECT] matched: buy button aria-label")
            return "IN_STOCK"

    #    c) 购买动作链接命中（最稳的后备）
    if _has_buy_link(html):
        print("[MERCARI DETECT] matched: /transaction/buy link")
        return "IN_STOCK"

    # 6) SOLD 贴片（仅作辅助，避免单靠 class 误判）
    #    通过图片容器附近的 SOLD 文本作为“加分项”（不是唯一依据）
    sold_badge = soup.find(string=re.compile(r"\bSOLD\b"))
    if sold_badge:
        # 如果有 SOLD 文本但没有买按钮/购买链接，同时也没有明确 IN_STOCK 信号，则判售罄
        print("[MERCARI DETECT] matched: SOLD badge without buy signals")
        return "OUT_OF_STOCK"

    print("[MERCARI DETECT] no rule matched -> UNKNOWN")
    return "UNKNOWN"











