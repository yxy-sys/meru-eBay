# detectors/yahoo.py
from bs4 import BeautifulSoup

def detect(html: str) -> str:
    """
    检测 Yahoo / PayPayフリマ 页面状态。
    返回：
      - "SOLD"：已售出
      - "OUT_OF_STOCK"：无货 / 已结束
      - "IN_STOCK"：可购买
      - "ACTIVE"：拍卖中
      - "UNKNOWN"：无法判定
    """
    if not html:
        return "UNKNOWN"

    soup = BeautifulSoup(html, "lxml")
    text = soup.get_text(" ", strip=True)

    lower_text = text.lower()

    # ✅ 1. PayPayフリマ 已售出标志（页面上有红色 SOLD 标签）
    if "sold" in lower_text or "売り切れました" in text or "販売終了" in text:
        return "SOLD"

    # ✅ 2. 页面明确显示“この商品は販売終了しました”或“出品が終了しました”
    if "販売終了しました" in text or "出品が終了" in text or "出品終了" in text:
        return "OUT_OF_STOCK"

    # ✅ 3. 出品已被删除或不存在
    if "出品者により削除" in text or "商品が見つかりません" in text or "ページが見つかりません" in text:
        return "OUT_OF_STOCK"

    # ✅ 4. 拍卖页面中“入札件数”“残り時間”等关键词
    if "入札件数" in text or "残り時間" in text:
        return "ACTIVE"

    # ✅ 5. 可购买标识
    if "カートに入れる" in text or "購入手続き" in text:
        return "IN_STOCK"

    return "UNKNOWN"
