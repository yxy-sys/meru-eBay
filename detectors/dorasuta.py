from bs4 import BeautifulSoup
import re

BUY_WORDS = ["カートに追加", "カートへ入れる", "購入"]
SOLD_WORDS = ["SOLD OUT", "品切れ", "在庫切れ"]

def _contains_any(text: str, words) -> bool:
    t = text.lower()
    return any(w.lower() in t for w in words)

def detect(html: str) -> str:
    """
    返回:
      - IN_STOCK     有购买按钮或在庫数>=1
      - OUT_OF_STOCK 有售罄字样或在庫数=0
      - UNKNOWN      其他（不动作）
    """
    if not html:
        return "UNKNOWN"

    soup = BeautifulSoup(html, "lxml")
    text = soup.get_text(" ", strip=True)

    m = re.search(r"在庫数\s*[:：]\s*(\d+)", text)
    if m:
        try:
            qty = int(m.group(1))
            if qty >= 1:
                return "IN_STOCK"
            else:
                return "OUT_OF_STOCK"
        except ValueError:
            pass

    if _contains_any(text, BUY_WORDS):
        return "IN_STOCK"

    if _contains_any(text, SOLD_WORDS):
        return "OUT_OF_STOCK"

    return "UNKNOWN"
