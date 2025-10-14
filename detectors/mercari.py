
from bs4 import BeautifulSoup
import re

SOLD_PATTERNS = [
    r"売り切れました", r"売り切れ", r"この商品は売り切れました",
    r"SOLD\s*OUT", r"\bSOLD\b", r"Sold\s*Out", r"\bsold\b",
    r"購入できません", r"在庫なし", r"販売停止中"
]

def detect(html: str):
    soup = BeautifulSoup(html, "lxml")
    metas = " ".join(m.get("content","") for m in soup.find_all("meta"))
    if any(re.search(p, metas, flags=re.I) for p in SOLD_PATTERNS):
        return "OUT_OF_STOCK"
    text = soup.get_text(" ", strip=True)
    if any(re.search(p, text, flags=re.I) for p in SOLD_PATTERNS):
        return "OUT_OF_STOCK"
    img_alts = " ".join(img.get("alt","") for img in soup.find_all("img"))
    aria_labels = " ".join(e.get("aria-label","") for e in soup.find_all(attrs={"aria-label": True}))
    if any(re.search(p, img_alts + " " + aria_labels, flags=re.I) for p in SOLD_PATTERNS):
        return "OUT_OF_STOCK"
    return "UNKNOWN"
