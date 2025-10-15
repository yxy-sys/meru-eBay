# detectors/yahoo.py
from bs4 import BeautifulSoup

def detect(html: str) -> str:
    """
    识别 Yahoo 拍卖状态：
    - 已结束：返回 "OUT_OF_STOCK"
    - 正在拍卖：返回 "ACTIVE"
    - 页面结构异常：返回 "UNKNOWN"
    """
    if not html:
        return "UNKNOWN"

    soup = BeautifulSoup(html, "lxml")
    text = soup.get_text(" ", strip=True).lower()

    # 一些常见的结束提示
    if "このオークションは終了しています" in text:
        return "OUT_OF_STOCK"
    if "落札者" in text and "終了日時" in text:
        return "OUT_OF_STOCK"
    if "出品が取り消されました" in text:
        return "OUT_OF_STOCK"
    if "出品者により削除" in text:
        return "OUT_OF_STOCK"

    # 正在拍卖
    if "入札件数" in text or "残り時間" in text:
        return "ACTIVE"

    return "UNKNOWN"
