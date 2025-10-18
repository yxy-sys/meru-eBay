from bs4 import BeautifulSoup

def detect(html: str) -> str:
    """
    Mercari 状态检测（防误报版）：
      - 删除/下架  -> DELETED
      - 可购买     -> IN_STOCK  （优先判断）
      - 售罄       -> OUT_OF_STOCK
      - 不确定     -> UNKNOWN
    """
    if not html:
        return "UNKNOWN"

    soup = BeautifulSoup(html, "lxml")
    text = soup.get_text(" ", strip=True)

    # 1) 删除 / 下架
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

    # 2) 可购买（优先判断）：按钮文案 / 购买链接特征
    buy_signals = [
        "購入手続きへ",   # 常规购买按钮
        "購入に進む",
        "購入へ",
        "カートに入れる",
    ]
    if any(s in text for s in buy_signals):
        return "IN_STOCK"
    # PC 端常见的购买链接
    if "/transaction/buy" in html:
        return "IN_STOCK"

    # 3) meta availability（在未命中“可购买”后参考）
    meta = (
        soup.find("meta", {"property": "product:availability"})
        or soup.find("meta", {"itemprop": "availability"})
        or soup.find("link", {"itemprop": "availability"})
    )
    if meta:
        val = (meta.get("content") or meta.get("href") or "").lower()
        if "in_stock" in val:
            return "IN_STOCK"
       # if "out_of_stock" in val or "sold" in val:
       #    return "OUT_OF_STOCK"

    # 4) 明确的日文售罄提示（避免英文 SOLD/SOLD OUT 造成图片水印误伤）
    sold_markers = [
        "売り切れました",
        "売り切れました。",
        "売り切れ",
        "売り切れのため購入できません",
    ]
    if any(m in text for m in sold_markers):
        return "OUT_OF_STOCK"

    # 5) 其余情况
    return "UNKNOWN"


