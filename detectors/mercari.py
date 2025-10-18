# detectors/mercari.py
from bs4 import BeautifulSoup
import re

def detect(html: str) -> str:
    """
    改进版 Mercari 商品状态检测：
      - 删除/下架：返回 DELETED
      - 售罄：     返回 OUT_OF_STOCK
      - 有货：     返回 IN_STOCK
      - 无法判断： 返回 UNKNOWN
    """

    if not html:
        return "UNKNOWN"

    soup = BeautifulSoup(html, "lxml")
    text = soup.get_text(" ", strip=True)

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
        return "DELETED"
    # ---------- (3) 售罄 ----------
    soldout_markers = [
        "売り切れました",
        "売り切れ",
        "SOLD OUT",
        "Sold Out",
        "SOLD",
    ]
    if any(m in text for m in soldout_markers):
        return "OUT_OF_STOCK"

    # ---------- (4) HTML 元信息辅助 ----------
    meta = (
        soup.find("meta", {"property": "product:availability"})
        or soup.find("meta", {"itemprop": "availability"})
        or soup.find("link", {"itemprop": "availability"})
    )
    if meta:
        val = (meta.get("content") or meta.get("href") or "").lower()
        if "out_of_stock" in val or "sold" in val:
            return "OUT_OF_STOCK"
        if "in_stock" in val:
            return "IN_STOCK"
# ---------- (2) 可购买信号（优先判定有货） ----------
    # 若出现购买按钮、加入购物车等文字 → 明确 IN_STOCK
    buy_signals = [
        "購入手続きへ",      # 常规购买按钮
        "購入に進む",        # 一些AB测试按钮文案
        "カートに入れる",    # 加入购物车（App端）
    ]
    if any(s in text for s in buy_signals):
        return "IN_STOCK"
    # ---------- (5) 其它情况 ----------
    return "UNKNOWN"

