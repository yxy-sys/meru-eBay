# detectors/mercari.py
from bs4 import BeautifulSoup
import json, re

_ZW = "\u200b\u200c\u200d\uFEFF"
def norm_text(s: str) -> str:
    if not s:
        return ""
    s = s.replace("\u3000", " ")
    for ch in _ZW:
        s = s.replace(ch, "")
    s = re.sub(r"\s+", " ", s, flags=re.S)
    return s.strip()

BUY_REGEX  = re.compile(r"購\s*入.*(手\s*続\s*き\s*へ|へ|に\s*進\s*む)", re.S)
SOLD_REGEX = re.compile(r"(売\s*り\s*切\s*れ(\s*ま\s*し\s*た)?|取引が終了|SOLD\s*OUT)", re.I)

def _jsonld_availability(soup: BeautifulSoup):
    for tag in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            data = json.loads(tag.string or "{}")
        except Exception:
            continue
        arr = data if isinstance(data, list) else [data]
        for obj in arr:
            avail = None
            if isinstance(obj, dict):
                offers = obj.get("offers")
                if isinstance(offers, dict):
                    avail = offers.get("availability")
                if not avail:
                    avail = obj.get("availability")
            if not avail:
                continue
            v = str(avail).lower()
            if "instock" in v or "in_stock" in v or "schema.org/instock" in v:
                return "in"
            if "outofstock" in v or "out_of_stock" in v or "schema.org/outofstock" in v or "sold" in v:
                return "out"
    return None

def _extract_text_dump(html: str) -> str:
    m = re.search(r"<!--TEXT_DUMP_START-->(.*?)<!--TEXT_DUMP_END-->", html, re.S)
    if not m:
        return ""
    return norm_text(m.group(1))

def detect(html: str) -> str:
    if not html:
        print("[MERCARI DETECT] empty html")
        return "UNKNOWN"

    soup = BeautifulSoup(html, "lxml")
    page_text = norm_text(soup.get_text(" ", strip=True))
    text_dump = _extract_text_dump(html)

    # 1) 删除/下架
    deleted_markers = [
        "該当する商品は削除されています。",
        "この商品は削除されました",
        "この商品は出品停止中です",
        "この商品は公開停止中です",
        "ページが見つかりません",
        "商品が見つかりません",
    ]
    if any(m in page_text for m in deleted_markers):
        print("[MERCARI DETECT] matched: deleted marker")
        return "DELETED"

    # 2) JSON-LD / meta
    jl = _jsonld_availability(soup)
    if jl == "in":
        print("[MERCARI DETECT] matched: jsonld=IN_STOCK")
        return "IN_STOCK"
    if jl == "out":
        print("[MERCARI DETECT] matched: jsonld=OUT_OF_STOCK")
        return "OUT_OF_STOCK"

    meta = (soup.find("meta", {"itemprop": "availability"})
            or soup.find("meta", {"property": "product:availability"})
            or soup.find("link", {"itemprop": "availability"}))
    if meta:
        val = norm_text(meta.get("content") or meta.get("href") or "").lower()
        if any(k in val for k in ("instock", "in_stock")):
            print("[MERCARI DETECT] matched: meta=IN_STOCK")
            return "IN_STOCK"
        if any(k in val for k in ("outofstock", "out_of_stock", "sold")):
            print("[MERCARI DETECT] matched: meta=OUT_OF_STOCK")
            return "OUT_OF_STOCK"

    # 3) 遍历按钮/链接
    buy_found  = False
    sold_found = False
    samples = []

    for b in soup.find_all("button"):
        t = norm_text(b.get_text(" ", strip=True))
        a = norm_text(b.get("aria-label") or "")
        if t:
            samples.append(t)
        disabled = (b.has_attr("disabled") or b.get("aria-disabled") in ("true", "1"))
        if BUY_REGEX.search(t) or BUY_REGEX.search(a):
            buy_found = True
        if SOLD_REGEX.search(t) or SOLD_REGEX.search(a):
            if disabled or "売り切れ" in t or "売り切れ" in a:
                sold_found = True

    for a in soup.find_all("a"):
        t = norm_text(a.get_text(" ", strip=True))
        ar = norm_text(a.get("aria-label") or "")
        if t and len(samples) < 6:
            samples.append(t)
        if BUY_REGEX.search(t) or BUY_REGEX.search(ar):
            buy_found = True
        if SOLD_REGEX.search(t) or SOLD_REGEX.search(ar):
            sold_found = True

    if samples:
        print("[MERCARI DETECT] buttons sample:", " | ".join(samples[:6]))

    # 购买动作链接兜底
    if "/transaction/buy" in html or "/transaction/buys" in html:
        buy_found = True

    if buy_found and not sold_found:
        print("[MERCARI DETECT] matched: BUY signals")
        return "IN_STOCK"
    if sold_found and not buy_found:
        print("[MERCARI DETECT] matched: SOLD signals")
        return "OUT_OF_STOCK"

    # 4) 纯文本兜底（来自 fetcher 注入的 TEXT_DUMP）
    if text_dump:
        if BUY_REGEX.search(text_dump):
            print("[MERCARI DETECT] matched: TEXT_DUMP BUY")
            return "IN_STOCK"
        if SOLD_REGEX.search(text_dump):
            print("[MERCARI DETECT] matched: TEXT_DUMP SOLD")
            return "OUT_OF_STOCK"

    # 5) 再兜底：整页文本见到“売り切れ”且没有 buy
    if not buy_found and SOLD_REGEX.search(page_text):
        print("[MERCARI DETECT] matched: SOLD badge (fallback)")
        return "OUT_OF_STOCK"

    print("[MERCARI DETECT] no rule matched -> UNKNOWN")
    return "UNKNOWN"









