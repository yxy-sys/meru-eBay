# detectors/yahoo.py
from bs4 import BeautifulSoup

def detect(html: str) -> str:
    """
    返回页面状态（供 main_yahoo.py 使用）：
      - "SOLD"           ：二手闲鱼/PayPayフリマ SOLD、或显式“売り切れ/在庫なし”
      - "ENDED"          ：拍卖已结束/被取消/被删除
      - "IN_STOCK"       ：仍在售/在拍
      - "UNKNOWN"        ：无法判断
    """
    if not html:
        return "UNKNOWN"

    soup = BeautifulSoup(html, "lxml")
    text = soup.get_text(" ", strip=True)
    tl = text.lower()

    # —— 删除/取消/结束（拍卖常见文案）——
    ended_keys = [
        "このオークションは終了しています",
        "出品が終了しました",
        "出品が取り消されました",
        "出品者により削除",
        "商品は削除されました",
    ]
    if any(k in text for k in ended_keys):
        return "ENDED"

    # —— PayPayフリマ/二手 SOLD 徽标 & 售罄文案 —— 
    # 页面会直接出现 "SOLD" 徽标，或“売り切れ/在庫なし”等字样
    if ("SOLD" in html) or ("sold" in tl) or ("売り切れ" in text) or ("在庫なし" in text):
        return "SOLD"

    # —— 拍卖进行中的常见文案（仅作“还在进行”的弱判断）——
    if ("入札件数" in text) or ("残り時間" in text):
        return "IN_STOCK"

    # 默认：当做还在售
    return "IN_STOCK"

