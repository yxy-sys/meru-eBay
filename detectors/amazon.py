# detectors/amazon.py
import re
from bs4 import BeautifulSoup

_price_num = re.compile(r"[\d,]+")

def _to_int(txt: str):
    if not txt:
        return None
    txt = txt.replace("￥", "").replace("円", "")
    m = _price_num.search(txt)
    if not m:
        return None
    try:
        return int(m.group(0).replace(",", ""))
    except Exception:
        return None

def detect(html: str) -> str:
    """
    Amazon 库存粗判：
      - 文本包含「在庫あり」「通常1～2日以内に発送」→ IN_STOCK
      - 文本包含「在庫切れ」「一時的に在庫切れ」「現在在庫切れです」→ OUT_OF_STOCK
      - 其它无法确认 → UNKNOWN
    """
    if not html:
        return "UNKNOWN"
    soup = BeautifulSoup(html, "lxml")
    text = soup.get_text(" ")
    t = text

    # 有货常见文案
    if any(w in t for w in ["在庫あり", "通常1～2日以内に発送", "通常1~2日以内に発送", "残り", "お急ぎ便"]):
        return "IN_STOCK"

    # 无货常见文案
    if any(w in t for w in ["在庫切れ", "一時的に在庫切れ", "現在在庫切れ", "この商品は現在お取り扱いできません"]):
        return "OUT_OF_STOCK"

    return "UNKNOWN"

def extract_price(html: str):
    """
    提取“当前应付价”。优先 core/apex 区域，避开划线价（a-text-price 等）。
    兼容 PC/移动（/gp/aw/…）页面。
    """
    if not html:
        return None
    soup = BeautifulSoup(html, "lxml")

    # 1) 新版应付价容器（桌面）
    sel_pref = [
        "#corePriceDisplay_desktop_feature_div span.a-price span.a-offscreen",
        "#apex_desktop span.a-price span.a-offscreen",
        "#price span.a-price span.a-offscreen",
    ]
    for sel in sel_pref:
        el = soup.select_one(sel)
        if el and el.get_text(strip=True):
            val = _to_int(el.get_text())
            if val is not None:
                return val

    # 2) 兼容移动页 (/gp/aw/…)
    sel_mobile = [
        "span.a-price .a-offscreen",
        "#apex_price_inside_buybox .a-offscreen",
    ]
    for sel in sel_mobile:
        el = soup.select_one(sel)
        if el and el.get_text(strip=True):
            # 跳过划线价容器祖先
            bad_ancestor = el.find_parent(class_="a-text-price")
            if bad_ancestor:
                continue
            val = _to_int(el.get_text())
            if val is not None:
                return val

    # 3) 旧 ID 兜底
    for old_id in ("priceblock_dealprice", "priceblock_ourprice", "priceblock_saleprice"):
        el = soup.find(id=old_id)
        if el and el.get_text(strip=True):
            val = _to_int(el.get_text())
            if val is not None:
                return val

    # 4) 最后兜底：整页文本里的“￥ 12,345”，但排除划线价区域文本
    for bad in soup.select(".a-text-price, .basisPrice, .priceBlockStrikePriceString"):
        bad.decompose()
    m = re.search(r"￥\s*([\d,]+)", soup.get_text(" "))
    if m:
        try:
            return int(m.group(1).replace(",", ""))
        except Exception:
            pass

    return None

