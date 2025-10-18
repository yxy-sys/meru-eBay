# detectors/mercari.py
from bs4 import BeautifulSoup

def detect(html: str) -> str:
    """
    识别 Mercari 商品状态：
      - 删除/下架：返回 DELETED  （如需与现有逻辑完全兼容，也可改为 OUT_OF_STOCK）
      - 售罄：     返回 OUT_OF_STOCK
      - 有货：     返回 IN_STOCK
      - 无法判断： 返回 UNKNOWN
    """
    if not html:
        return "UNKNOWN"

    soup = BeautifulSoup(html, "lxml")
    text = soup.get_text(" ", strip=True)

    # ---- 删除 / 下架 / 非公开 ----
    deleted_markers = [
        "該当する商品は削除されています。",
        "この商品は削除されました",
        "この商品は出品停止中です",
        "この商品は公開停止中です",
        "ページが見つかりません",
    ]
    if any(m in text for m in deleted_markers):
        return "DELETED"        # 若无需区分，可改成：return "OUT_OF_STOCK"

    # ---- 售罄 ----
    soldout_markers = [
        "売り切れました",
        "売り切れ",
        "SOLD OUT",
        "Sold Out",
        "SOLD",   # 兼容少数英文模板
    ]
    if any(m in text for m in soldout_markers):
        return "OUT_OF_STOCK"

    # ---- 有货（购买按钮）----
    if "購入手続きへ" in text:
        return "IN_STOCK"

    return "UNKNOWN"
