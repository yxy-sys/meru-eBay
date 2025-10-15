# detectors/yshopping.py
import re
from bs4 import BeautifulSoup

_OUT_WORDS = [
    "在庫なし", "在庫切れ", "売り切れ", "完売", "販売終了",
    "お取り扱いできません", "この商品は現在お取り扱いできません",
]
_IN_WORDS = ["在庫あり", "在庫あり。", "通常在庫", "在庫残り"]

_price_num = re.compile(r"[\d,]+")

def _txt(s):
    if not s:
        return ""
    return re.sub(r"\s+", " ", s).strip()

def detect(html: str) -> str:
    """
    返回:
      - 'OUT_OF_STOCK' : 明确售罄/无货
      - 'IN_STOCK'     : 明确有货
      - 'UNKNOWN'      : 无法判断
    """
    if not html:
        return "UNKNOWN"

    soup = BeautifulSoup(html, "lxml")

    # 1) 优先看 og:availability
    og = soup.find("meta", {"property": "og:availability"})
    if og and og.get("content"):
        v = og["content"].lower()
        if "out_of_stock" in v:
            return "OUT_OF_STOCK"
        if "instock" in v or "in_stock" in v:
            return "IN_STOCK"

    # 2) 常见库存提示区域（Y!ショッピング有多种主题，这里走文本兜底）
    text = _txt(soup.get_text(" "))
    if any(w in text for w in _OUT_WORDS):
        return "OUT_OF_STOCK"
    if any(w in text for w in _IN_WORDS):
        return "IN_STOCK"

    return "UNKNOWN"


def extract_price(html: str):
    """
    尽量提取日元价格，返回 int 或 None。
    逻辑：先找 itemprop/og:price，再兜底文本解析。
    """
    if not html:
        return None
    soup = BeautifulSoup(html, "lxml")

    # itemprop=price
    n = soup.find(attrs={"itemprop": "price"})
    if n:
        v = n.get("content") or n.get_text()
        if v:
            m = _price_num.search(v)
            if m:
                return int(m.group(0).replace(",", ""))

    # meta property="product:price:amount" / "og:price:amount"
    for prop in ["product:price:amount", "og:price:amount"]:
        m = soup.find("meta", {"property": prop})
        if m and m.get("content"):
            try:
                return int(_price_num.search(m["content"]).group(0).replace(",", ""))
            except Exception:
                pass

    # 兜底：页面文本中挑最近的“￥123,456”
    m = re.search(r"￥\s*([\d,]+)", soup.get_text(" "))
    if m:
        return int(m.group(1).replace(",", ""))

    return None
