# detectors/amazon.py
import re
from bs4 import BeautifulSoup

_OUT_WORDS = [
    "在庫切れ", "在庫なし", "一時的に在庫切れ", "現在在庫切れ",
    "出品者からお求めいただけません", "この商品は現在お取り扱いできません",
    "入荷の予定は立っていません", "販売を停止", "販売休止", "販売終了",
]
_LOW_WORDS = ["残り", "点です", "点のみ", "在庫は残り", "残りわずか"]

_price_num = re.compile(r"[\d,]+")

def _txt(s):
    if not s:
        return ""
    return re.sub(r"\s+", " ", s).strip()

def detect(html: str) -> str:
    """
    返回库存状态：
      - 'OUT_OF_STOCK'：明确无货/售罄
      - 'LOW_STOCK'   ：文案显示仅剩少量
      - 'IN_STOCK'    ：能明确看到有货/购买按钮
      - 'UNKNOWN'     ：无法判断
    """
    if not html:
        return "UNKNOWN"

    soup = BeautifulSoup(html, "lxml")
    text = _txt(soup.get_text(" ")).lower()

    # 明确无货词
    for w in _OUT_WORDS:
        if w.lower() in text:
            return "OUT_OF_STOCK"

    # 低库存词（“残り◯点”）
    for w in _LOW_WORDS:
        if w.lower() in text:
            return "LOW_STOCK"

    # 按钮/购买迹象（简易判断）
    buy_btn = soup.select_one("#buy-now-button, input#add-to-cart-button, input#add-to-cart-button-ubb")
    if buy_btn:
        return "IN_STOCK"

    # 有时价格存在也可侧面说明在售
    p = extract_price(html)
    if p:
        return "IN_STOCK"

    return "UNKNOWN"


def extract_price(html: str):
    """
    提取日元价格（int）。可能返回 None。
    逻辑：
      1) a-price > a-price-whole
      2) #corePriceDisplay_desktop_feature_div 中的文案
      3) 页面文本中的 ￥123,456 兜底
    """
    if not html:
        return None

    soup = BeautifulSoup(html, "lxml")

    # 1) 标准价格块
    node = soup.select_one("span.a-price > span.a-price-whole")
    if node and node.text:
        try:
            return int(_price_num.search(node.text).group(0).replace(",", ""))
        except Exception:
            pass

    # 2) 另一种容器
    container = soup.select_one("#corePriceDisplay_desktop_feature_div")
    if container:
        m = _price_num.search(container.get_text(" "))
        if m:
            try:
                return int(m.group(0).replace(",", ""))
            except Exception:
                pass

    # 3) 兜底：文本里搜“￥ 12,345”
    m = re.search(r"￥\s*([\d,]+)", soup.get_text(" "))
    if m:
        try:
            return int(m.group(1).replace(",", ""))
        except Exception:
            pass

    return None
