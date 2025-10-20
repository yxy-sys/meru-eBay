# detectors/mercari.py
from bs4 import BeautifulSoup
import re

def detect(html: str) -> str:
    """
    Mercari 状态检测（防误报版）
      - 删除/非公开 -> DELETED
      - 主商品可买 -> IN_STOCK
      - 主商品卖完 -> OUT_OF_STOCK
      - 其它 -> UNKNOWN
    关键：用“位置优先”避免把推荐区的『売り切れました』误当主商品售罄。
    """
    if not html:
        return "UNKNOWN"

    soup = BeautifulSoup(html, "lxml")
    text = soup.get_text(" ", strip=True)

    # 1) 删除/下架
    deleted_markers = [
        "該当する商品は削除されています。",
        "この商品は削除されました",
        "この商品は出品停止中です",
        "この商品は公開停止中です",
        "ページが見つかりません",
        "商品が見つかりません",
    ]
    if any(m in text for m in deleted_markers):
        return "DELETED"

    # 2) 先用结构化强特征判“可买”
    #   - 购买表单
    if soup.find("form", attrs={"action": re.compile(r"/transaction/buy")}):
        return "IN_STOCK"
    #   - 红色购买按钮（按钮或链接）
    buy_btn = soup.select_one('a,button')
    if buy_btn and buy_btn.get_text(strip=True) == "購入手続きへ":
        return "IN_STOCK"

    # 3) 位置优先法：谁先出现谁生效（避免推荐区的『売り切れました』干扰）
    #    仅在没有强特征“可买”时才进入本分支
    flat = re.sub(r"\s+", " ", html)  # 用原始 HTML，便于定位相对位置
    flat_low = flat.lower()

    idx_buy  = flat_low.find("購入手続きへ".encode("utf-8").decode("utf-8").lower())
    idx_form = flat_low.find("/transaction/buy")
    idx_sold = flat_low.find("売り切れました".encode("utf-8").decode("utf-8").lower())

    # 可买信号（任一出现且更靠前）优先
    earliest_buy = min([i for i in [idx_buy, idx_form] if i != -1], default=-1)

    if earliest_buy != -1:
        # 若也出现了『売り切れました』，比较谁更靠前；主区通常在前
        if idx_sold == -1 or earliest_buy < idx_sold:
            return "IN_STOCK"

    # 没有任何可买信号，且出现了『売り切れました』
    if idx_sold != -1 and earliest_buy == -1:
        return "OUT_OF_STOCK"

    # 4) 兜底：再做一次弱特征检查（主图 SOLD 丝带常是图片上的字，不用它）
    # meta availability（有站点会填，有的不会）
    meta = (
        soup.find("meta", {"property": "product:availability"})
        or soup.find("meta", {"itemprop": "availability"})
        or soup.find("link", {"itemprop": "availability"})
    )
    if meta:
        val = (meta.get("content") or meta.get("href") or "").lower()
        if "in_stock" in val:
            return "IN_STOCK"
        if "out_of_stock" in val or "sold" in val:
            return "OUT_OF_STOCK"

    return "UNKNOWN"







