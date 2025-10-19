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

    # 4) 售罄提示
   # ---------- (3) 灰色按钮「売り切れました」 ----------
    for btn in soup.find_all("button"):
        label = btn.get_text(strip=True)
        if "売り切れました" in label:
            print("[MERCARI DETECT] matched: disabled button text 売り切れました")
            return "OUT_OF_STOCK"
        if (btn.has_attr("disabled") or btn.get("aria-disabled") == "true") and re.search("売|切|れ", label):
            print("[MERCARI DETECT] matched: disabled button (aria-disabled)")
            return "OUT_OF_STOCK"

    # ---------- (4) meta availability ----------
    meta = (
        soup.find("meta", {"property": "product:availability"})
        or soup.find("meta", {"itemprop": "availability"})
        or soup.find("link", {"itemprop": "availability"})
    )
    if meta:
        val = (meta.get("content") or meta.get("href") or "").lower()
        if "out_of_stock" in val or "sold" in val:
            print("[MERCARI DETECT] matched: meta out_of_stock/sold")
            return "OUT_OF_STOCK"
        if "in_stock" in val:
            print("[MERCARI DETECT] matched: meta in_stock")
            return "IN_STOCK"

    # ---------- (5) HTML class 中的 sold ----------
    if re.search(r'class=["\'].*sold.*["\']', html_lower):
        print("[MERCARI DETECT] matched: class contains sold")
        return "OUT_OF_STOCK"
    if "itemstatuslabel__sold" in html_lower or "itemsoldbadge" in html_lower:
        print("[MERCARI DETECT] matched: sold class keywords")
        return "OUT_OF_STOCK"

    # ---------- (6) 文本包含「売り切れ」 ----------
    sold_markers = ["売り切れました", "売り切れました。", "売り切れ", "売り切れのため購入できません"]
    if any(m in text for m in sold_markers):
        print("[MERCARI DETECT] matched: sold text marker")
        return "OUT_OF_STOCK"

    # 5) 其余情况
    return "UNKNOWN"


