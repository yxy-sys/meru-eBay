# detectors/yahoo.py
from bs4 import BeautifulSoup

# 购买/在售信号（任一出现即可认为在售）
BUY_SIGNALS = [
    "購入手続きへ",   # PayPayフリマ 在售按钮
    "カートに入れる", # 一般商店
    "今すぐ購入",     # 常见
    "購入する",
    "入札する",       # 拍卖进行中
    "落札する",
]

# 售罄/结束信号（仅在不存在购买按钮的前提下才生效）
SOLD_SIGNALS = [
    "sold",               # 丝带文字（可能是英文）
    "売り切れました",
    "在庫切れ",
    "このオークションは終了しています",
    "出品が取り消されました",
    "終了日時",           # 常与“落札者”同时出现
    "落札者",
]

# 删除/不存在（备用；HTTP 404/410 已在主流程兜底）
GONE_SIGNALS = [
    "ページが見つかりません",
    "ご指定のページは見つかりません",
    "このページは存在しません",
]

def detect(html: str) -> str:
    """
    返回：
      - IN_STOCK     有“购买/结算/入札”按钮
      - OUT_OF_STOCK 无购买按钮，且出现售罄/结束的强信号
      - UNKNOWN      其他情况（不做动作，避免误报）
    """
    if not html:
        return "UNKNOWN"

    soup = BeautifulSoup(html, "lxml")

    # 把整页文本转小写，方便包含判断
    text = soup.get_text(" ", strip=True).lower()

    def contains_any(haystack: str, needles) -> bool:
        for s in needles:
            if s.lower() in haystack:
                return True
        return False

    # 1) 先看是否有购买/结算按钮 —— 只要有就认为在售
    if contains_any(text, BUY_SIGNALS):
        return "IN_STOCK"

    # 2) 没有购买按钮，再看售罄/结束强信号
    if contains_any(text, SOLD_SIGNALS):
        return "OUT_OF_STOCK"

    # 3) 备用的“页面不存在”提示（一般主流程已用 404/410 处理）
    if contains_any(text, GONE_SIGNALS):
        return "OUT_OF_STOCK"

    return "UNKNOWN"

