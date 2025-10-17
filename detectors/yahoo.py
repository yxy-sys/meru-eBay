# detectors/yahoo.py
from bs4 import BeautifulSoup

def detect(html: str) -> str:
    """
    检测 Yahoo / PayPayフリマ 页面状态。
    返回：
      - "SOLD"：已售出
      - "OUT_OF_STOCK"：下架或删除
      - "IN_STOCK"：可购买
      - "ACTIVE"：拍卖中
      - "UNKNOWN"：无法判定
    """
    if not html:
        return "UNKNOWN"

    soup = BeautifulSoup(html, "lxml")
    text = soup.get_text(" ", strip=True)

    # ----------- 1️⃣ 结构检测：SOLD 标签或图标 ----------
    # <div class="Label--sold"> 或 aria-label="SOLD"
    sold_badges = soup.find_all(
        lambda tag: (
            tag.name in ["div", "span", "p"]
            and (
                ("sold" in (tag.get("class") or []))
                or ("Label--sold" in " ".join(tag.get("class", [])))
                or ("SOLD" in (tag.get_text() or "").upper())
                or (tag.get("aria-label", "") == "SOLD")
            )
        )
    )
    if sold_badges:
        return "SOLD"

    # ----------- 2️⃣ 文本检测（兼容“売り切れ”/“販売終了”） ----------
    lower_text = text.lower()
    if (
        "sold" in lower_text
        or "売り切れ" in text
        or "販売終了" in text
        or "販売停止中" in text
        or "この商品は販売を終了しました" in text
    ):
        return "SOLD"

    # ----------- 3️⃣ 无货/下架 ----------
    if (
        "出品が終了しました" in text
        or "出品が取り消されました" in text
        or "出品終了" in text
        or "商品が見つかりません" in text
        or "ページが見つかりません" in text
        or "削除されました" in text
    ):
        return "OUT_OF_STOCK"

    # ----------- 4️⃣ 可购买 ----------
    if "カートに入れる" in text or "購入手続き" in text:
        return "IN_STOCK"

    # ----------- 5️⃣ 拍卖进行中 ----------
    if "入札件数" in text or "残り時間" in text:
        return "ACTIVE"

    return "UNKNOWN"

