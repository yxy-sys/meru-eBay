from bs4 import BeautifulSoup
import re

def detect(html: str) -> str:
    """
    Mercari 状态检测（含灰色售罄按钮 + 调试来源输出）：
      - 删除/下架  -> DELETED
      - 可购买     -> IN_STOCK
      - 售罄       -> OUT_OF_STOCK（含灰按钮「売り切れました」）
      - 不确定     -> UNKNOWN
    """
    if not html:
        print("[MERCARI DETECT] empty html")
        return "UNKNOWN"

    soup = BeautifulSoup(html, "lxml")
    text = soup.get_text(" ", strip=True)
    html_lower = html.lower()

    # ---------- (1) 删除 / 下架 ----------
    deleted_markers = [
        "該当する商品は削除されています。",
        "この商品は削除されました",
        "この商品は出品停止中です",
        "この商品は公開停止中です",
        "ページが見つかりません",
        "商品が見つかりません",
    ]
    if any(m in text for m in deleted_markers):
        print("[MERCARI DETECT] matched: deleted marker text")
        return "DELETED"

    # ---------- (2) 可购买 ----------
    buy_signals = ["購入手続きへ", "購入に進む", "購入へ", "カートに入れる"]
    if any(s in text for s in buy_signals):
        print("[MERCARI DETECT] matched: buy button text")
        return "IN_STOCK"
    if "/transaction/buy" in html_lower:
        print("[MERCARI DETECT] matched: buy link")
        return "IN_STOCK"

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

    # ---------- (7) 未匹配 ----------
    print("[MERCARI DETECT] no match → UNKNOWN")
    return "UNKNOWN"



