# detectors/rakuten.py
from bs4 import BeautifulSoup
import re

def detect(html: str) -> str:
    """
    Rakuten 商品状态检测：
      - 删除/下架  -> DELETED
      - 售罄       -> OUT_OF_STOCK
      - 可购买     -> IN_STOCK
      - 无法判断   -> UNKNOWN
    """
    if not html:
        print("[RAKUTEN DETECT] empty html")
        return "UNKNOWN"

    soup = BeautifulSoup(html, "lxml")
    text = soup.get_text(" ", strip=True)
    html_lower = html.lower()

    # ---------- (1) 删除 / 下架 ----------
    deleted_markers = [
        "この商品は販売しておりません",
        "お探しの商品は見つかりませんでした",
        "現在ご指定のページは表示できません",
        "販売期間が終了しました",
        "ページが見つかりません",
    ]
    if any(m in text for m in deleted_markers):
        print("[RAKUTEN DETECT] matched: deleted marker text")
        return "DELETED"

    # ---------- (2) 售罄 ----------
    sold_markers = [
        "売り切れました",
        "売り切れ",
        "在庫なし",
        "販売終了",
        "現在売り切れ中です",
    ]
    if any(m in text for m in sold_markers):
        print("[RAKUTEN DETECT] matched: sold text marker")
        return "OUT_OF_STOCK"

    # meta availability
    meta = (
        soup.find("meta", {"itemprop": "availability"})
        or soup.find("meta", {"property": "product:availability"})
    )
    if meta:
        val = (meta.get("content") or "").lower()
        if "out_of_stock" in val or "sold" in val:
            print("[RAKUTEN DETECT] matched: meta out_of_stock")
            return "OUT_OF_STOCK"
        if "in_stock" in val:
            print("[RAKUTEN DETECT] matched: meta in_stock")
            return "IN_STOCK"

    # ---------- (3) 可购买 ----------
    buy_signals = ["商品をかごに追加", "購入手続きへ", "ご購入手続き", "カートに入れる"]
    if any(s in text for s in buy_signals):
        print("[RAKUTEN DETECT] matched: buy button text")
        return "IN_STOCK"

    # ---------- (4) 未匹配 ----------
    print("[RAKUTEN DETECT] no match → UNKNOWN")
    return "UNKNOWN"
