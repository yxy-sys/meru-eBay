from bs4 import BeautifulSoup

def detect(html: str) -> str:
    """防止图片上 SOLD 误判的煤炉检测"""
    if not html:
        return "UNKNOWN"

    soup = BeautifulSoup(html, "lxml")
    text = soup.get_text(" ", strip=True)

    # === 删除或下架 ===
    deleted = [
        "該当する商品は削除されています。",
        "この商品は削除されました",
        "この商品は出品停止中です",
        "ページが見つかりません",
    ]
    if any(t in text for t in deleted):
        return "DELETED"

    # === 先看是否可购买（优先）===
    for b in soup.find_all(["button", "a"]):
        t = (b.get_text() or "").strip()
        if "購入手続きへ" in t or "購入に進む" in t:
            if "売り切れました" not in t:  # 防止灰按钮
                return "IN_STOCK"
    if "/transaction/buy" in html:
        return "IN_STOCK"

    # === 售罄（仅灰色按钮 / meta 明确）===
    for b in soup.find_all(["button", "span", "div"]):
        t = (b.get_text() or "").strip()
        if "売り切れました" in t or "売り切れのため購入できません" in t:
            return "OUT_OF_STOCK"

    # === meta availability ===
    meta = soup.find("meta", {"itemprop": "availability"})
    if meta:
        val = (meta.get("content") or "").lower()
        if "out_of_stock" in val:
            return "OUT_OF_STOCK"
        if "in_stock" in val:
            return "IN_STOCK"

    # === 忽略图片容器中的 SOLD class ===
    for div in soup.find_all("div"):
        cls = " ".join(div.get("class", []))
        if "sold" in cls and "overlay" in cls:
            # 明确是图片角标，忽略
            continue

    return "UNKNOWN"




