# detectors/yahoo.py
import re
from bs4 import BeautifulSoup

SOLD_SIGNALS = [
    "sold",                     # PayPayフリマ 图片角标文字（有时会进到可见文本）
    "売り切れ", "売り切れました",
    "在庫切れ", "在庫なし",
    "販売終了", "取扱い終了",
    "公開が終了", "出品が終了",
    "購入できません", "購入不可",
]

YAUCTION_ENDED = [
    "このオークションは終了しています",
    "落札者", "終了日時",
    "出品が取り消されました",
    "出品者により削除",
]

IN_STOCK_HINTS = [
    "今すぐ購入", "カートに入れる", "購入手続きへ",  # 购物
    "入札する", "入札件数", "残り時間",              # 拍卖
]

def _has_any(text: str, keywords) -> bool:
    return any(k in text for k in keywords)

def detect(html: str) -> str:
    """
    统一判断 Yahoo 系列页面的货态：
      - 返回: "SOLD" / "OUT_OF_STOCK" / "IN_STOCK" / "UNKNOWN"
      - PayPayフリマ: SOLD 徽标、売り切れ文案等
      - ヤフオク: 終了/落札者/終了日時 等
      - Shopping: 在庫切れ/売り切れ/販売終了 等
    """
    if not html:
        return "UNKNOWN"

    soup = BeautifulSoup(html, "lxml")

    # 1) 先抓全页面文本（小写&日文原样都检查）
    text = soup.get_text(" ", strip=True)
    text_lower = text.lower()

    # 2) PayPay フリマ：页面里经常有英文 "SOLD" 角标或「売り切れ」之类提示
    #   - 用原文和小写双重判断，尽量兜底
    if _has_any(text, SOLD_SIGNALS) or _has_any(text_lower, ["sold"]):
        return "SOLD"

    # 3) ヤフオク（拍卖）
    if _has_any(text, YAUCTION_ENDED):
        return "OUT_OF_STOCK"

    # 4) Yahoo!ショッピング
    if _has_any(text, ["在庫切れ", "売り切れ", "販売終了", "この商品は現在お取り扱いできません"]):
        return "OUT_OF_STOCK"

    # 5) 若出现明显在售按钮/文案，判定为有货
    if _has_any(text, IN_STOCK_HINTS):
        return "IN_STOCK"

    # 6) 兜底：有些站点把 SOLD 放在 aria/alt 里，再额外扫一下常见属性
    possible = " ".join([
        " ".join(tag.get("alt", "") for tag in soup.find_all(True)),
        " ".join(tag.get("aria-label", "") for tag in soup.find_all(True)),
        " ".join(tag.get("content", "") for tag in soup.find_all("meta"))
    ])
    possible_lower = possible.lower()
    if _has_any(possible, SOLD_SIGNALS) or ("sold" in possible_lower):
        return "SOLD"

    return "UNKNOWN"

