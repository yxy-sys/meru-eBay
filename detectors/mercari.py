# detectors/mercari.py
from bs4 import BeautifulSoup
import re

BUY_RX = re.compile(r"購\s*入\s*手\s*続\s*き\s*へ")          # “購入手続きへ” 允许空格/换行
SOLD_BTN_RX = re.compile(r"売\s*り\s*切\s*れ\s*ま\s*し\s*た")  # “売り切れました”

def _has_buy_button(soup, html: str) -> bool:
    """尽量通过结构找可买按钮；其次看 /transaction/buy 链接"""
    # 1) 直接找 <button> 元素文本
    for btn in soup.select("button, a, div[role=button]"):
        txt = (btn.get_text(" ", strip=True) or "")
        if BUY_RX.search(txt):
            # 按钮若被禁用，通常会有 disabled/aria-disabled/不可点 class
            if btn.has_attr("disabled") or btn.get("aria-disabled") in ("true", "1"):
                continue
            cls = " ".join(btn.get("class", []))
            if any(x in cls for x in ["disabled", "is-disabled"]):
                continue
            return True

    # 2) 兜底：购买链接（PC端会有）
    if "/transaction/buy" in (html or ""):
        return True

    return False


def _has_soldout_button(soup) -> bool:
    """灰色按钮 ‘売り切れました’（可靠的售罄信号）"""
    for btn in soup.select("button, div[role=button]"):
        txt = (btn.get_text(" ", strip=True) or "")
        if SOLD_BTN_RX.search(txt):
            return True
    return False


def detect(html: str) -> str:
    """
    Mercari 状态检测（结构化版，避免误判）：
      - 删除/下架：DELETED
      - 有货（出现“購入手続きへ”/buy 链接且未禁用）：IN_STOCK
      - 售罄（出现灰按钮“売り切れました”或明确 SOLD 标识）：OUT_OF_STOCK
      - 其它：UNKNOWN
    """
    if not html:
        return "UNKNOWN"

    soup = BeautifulSoup(html, "lxml")
    page_text = soup.get_text(" ", strip=True)

    # ---- 删除 / 下架 ----
    deleted_markers = [
        "該当する商品は削除されています。", "この商品は削除されました",
        "この商品は出品停止中です", "この商品は公開停止中です",
        "ページが見つかりません", "商品が見つかりません",
    ]
    if any(m in page_text for m in deleted_markers):
        return "DELETED"

    # ---- 有货：优先结构化找购买按钮 ----
    if _has_buy_button(soup, html):
        return "IN_STOCK"

    # ---- 售罄：优先灰按钮；再用 meta availability；最终再文本兜底 ----
    if _has_soldout_button(soup):
        return "OUT_OF_STOCK"

    meta = (
        soup.find("meta", {"property": "product:availability"})
        or soup.find("meta", {"itemprop": "availability"})
        or soup.find("link", {"itemprop": "availability"})
    )
    if meta:
        val = (meta.get("content") or meta.get("href") or "").lower()
        if "in_stock" in val:
            return "IN_STOCK"
        if "out_of_stock" in val:
            return "OUT_OF_STOCK"

    # 文本兜底：仅匹配明确日文售罄，避免图片里英文 SOLD 误判
    sold_markers = ["売り切れました", "売り切れ", "売り切れのため購入できません"]
    if any(m in page_text for m in sold_markers):
        return "OUT_OF_STOCK"

    return "UNKNOWN"









