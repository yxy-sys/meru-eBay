# detectors/mercari.py
from bs4 import BeautifulSoup
from typing import Iterable, Optional

# ---- 可根据需要扩展的配置 ----
HIDE_CLASSES = {"sr-only"}  # 常见隐藏类
HIDE_STYLE_KEYWORDS = ("display:none", "visibility:hidden")  # 简单样式隐藏判定
BUY_LABELS = ("購入手続きへ", "購入に進む", "購入へ")        # 购买按钮常见文案
SOLD_LABELS = ("売り切れました", "売り切れのため購入できません")  # 售罄按钮常见文案

DELETED_MARKERS = (
    "該当する商品は削除されています。",
    "この商品は削除されました",
    "この商品は出品停止中です",
    "この商品は公開停止中です",
    "ページが見つかりません",
    "商品が見つかりません",
)


def _text(el) -> str:
    """安全取文本（已 strip）。"""
    return (el.get_text(strip=True) or "") if el else ""


def _has_any(text: str, needles: Iterable[str]) -> bool:
    return any(n in text for n in needles)


def _is_node_or_ancestor_hidden(el) -> bool:
    """
    判断元素或其祖先是否被“隐藏”：
    - hidden / aria-hidden="true"
    - style 显式隐藏（display:none / visibility:hidden）
    - 隐藏类（如 sr-only）
    """
    cur = el
    while cur is not None:
        # attribute
        if cur.has_attr("hidden") or cur.get("aria-hidden") == "true":
            return True

        # style
        style = (cur.get("style") or "").replace(" ", "").lower()
        if any(k in style for k in HIDE_STYLE_KEYWORDS):
            return True

        # class
        cls = cur.get("class") or []
        if any(c in HIDE_CLASSES for c in cls):
            return True

        cur = cur.parent
    return False


def _find_visible_label(soup: BeautifulSoup, labels: Iterable[str]) -> Optional[str]:
    """
    在 button/a 等候选可点击元素上寻找“可见”的目标文案。
    返回命中的文案；找不到返回 None。
    """
    candidates = soup.find_all(["button", "a"])
    for el in candidates:
        label = _text(el)
        if not label:
            continue

        if _has_any(label, labels):
            # 过滤不可见/禁用
            if _is_node_or_ancestor_hidden(el):
                continue
            if el.get("disabled") is not None or el.get("aria-disabled") == "true":
                # 被禁用通常可见但不可点（售罄按钮常如此）；这里不提前排除，交给上层判断：
                # - 售罄按钮：禁用但可见 => 当作 OUT_OF_STOCK
                # - 购买按钮：若禁用（非常少见），当作不可购买
                pass
            return label
    return None


def _meta_availability(soup: BeautifulSoup) -> Optional[str]:
    """
    读取 meta availability 的兜底：in_stock/out_of_stock。
    返回 'IN_STOCK' / 'OUT_OF_STOCK' / None
    """
    meta = (
        soup.find("meta", {"property": "product:availability"})
        or soup.find("meta", {"itemprop": "availability"})
        or soup.find("link", {"itemprop": "availability"})
    )
    if not meta:
        return None

    val = (meta.get("content") or meta.get("href") or "").strip().lower()
    if "out_of_stock" in val or "sold" in val:
        return "OUT_OF_STOCK"
    if "in_stock" in val:
        return "IN_STOCK"
    return None


def detect(html: str) -> str:
    """
    Mercari 状态检测（可见性优先、防误报版）：
      - 删除/下架: DELETED
      - 灰按钮“売り切れました”可见: OUT_OF_STOCK
      - 红按钮“購入手続きへ”可见: IN_STOCK
      - meta availability 兜底
      - 文本兜底（最后才做）
      - 仍不确定: UNKNOWN
    """
    if not html:
        return "UNKNOWN"

    soup = BeautifulSoup(html, "lxml")

    # 1) 删除/下架
    page_text = soup.get_text(" ", strip=True)
    if _has_any(page_text, DELETED_MARKERS):
        return "DELETED"

    # 2) 售罄（只看“可见”的按钮）
    sold = _find_visible_label(soup, SOLD_LABELS)
    if sold:
        # 售罄按钮（通常可见且禁用）优先级最高
        return "OUT_OF_STOCK"

    # 3) 可购买（只看“可见”的按钮）
    buy = _find_visible_label(soup, BUY_LABELS)
    if buy:
        return "IN_STOCK"

    # 4) meta availability 兜底
    meta_status = _meta_availability(soup)
    if meta_status:
        return meta_status

    # 5) 纯文本兜底（放最后，避免把隐藏节点文本误当真）
    #    例如：只有图片角标 SOLD、或模板里同时渲染买/售罄但隐藏其中之一
    if _has_any(page_text, SOLD_LABELS):
        return "OUT_OF_STOCK"
    if _has_any(page_text, BUY_LABELS):
        return "IN_STOCK"

    return "UNKNOWN"







