# detectors/mercari.py
from bs4 import BeautifulSoup
import json
import re

def _norm(txt: str) -> str:
    return re.sub(r"\s+", "", txt or "")

def detect(html: str) -> str:
    """
    Mercari 状态检测（稳健版）
      - 返回: IN_STOCK / OUT_OF_STOCK / DELETED / UNKNOWN
    日志中会打印命中规则，方便排查。
    """
    if not html:
        print("[MERCARI DETECT] empty html -> UNKNOWN")
        return "UNKNOWN"

    soup = BeautifulSoup(html, "lxml")
    page_text = soup.get_text(" ", strip=True)

    # ---------- 0) 页面删除/下架 ----------
    deleted_markers = [
        "該当する商品は削除されています。", "この商品は削除されました",
        "この商品は出品停止中です", "この商品は公開停止中です",
        "ページが見つかりません", "商品が見つかりません",
    ]
    if any(m in page_text for m in deleted_markers):
        print("[MERCARI DETECT] page deleted markers -> DELETED")
        return "DELETED"

    # ---------- 1) JSON-LD availability ----------
    try:
        for tag in soup.find_all("script", {"type": "application/ld+json"}):
            data = tag.string or ""
            if not data.strip():
                continue
            # 页面里有时是数组
            loaded = json.loads(data)
            candidates = loaded if isinstance(loaded, list) else [loaded]
            for obj in candidates:
                if not isinstance(obj, dict):
                    continue
                avail = (_norm(obj.get("availability", "")) or
                         _norm(obj.get("offers", {}).get("availability", "")))
                if "instock" in avail:
                    print("[MERCARI DETECT] JSON-LD availability=InStock -> IN_STOCK")
                    return "IN_STOCK"
                if "outofstock" in avail or "sold" in avail:
                    print("[MERCARI DETECT] JSON-LD availability=OutOfStock/Sold -> OUT_OF_STOCK")
                    return "OUT_OF_STOCK"
    except Exception as e:
        print(f"[MERCARI DETECT] json-ld parse error: {e}")

    # ---------- 2) <meta> availability ----------
    meta = (soup.find("meta", {"itemprop": "availability"}) or
            soup.find("link", {"itemprop": "availability"}) or
            soup.find("meta", {"property": "product:availability"}))
    if meta:
        val = (_norm(meta.get("content") or meta.get("href") or "")).lower()
        if "instock" in val:
            print("[MERCARI DETECT] meta availability=InStock -> IN_STOCK")
            return "IN_STOCK"
        if "outofstock" in val or "sold" in val:
            print("[MERCARI DETECT] meta availability=OutOfStock/Sold -> OUT_OF_STOCK")
            return "OUT_OF_STOCK"

    # ---------- 3) 购买按钮/售罄按钮 ----------
    # 3.1 购买按钮（红色）：購入手続きへ（未禁用） -> IN_STOCK
    for btn in soup.find_all(["button", "a"]):
        text = (btn.get_text(strip=True) or "")
        ntext = _norm(text)
        if "購入手続きへ" in text or "購入に進む" in text:
            disabled = btn.has_attr("disabled") or btn.get("aria-disabled") in ("true", "1")
            # 一些 A/B 文案的按钮可能放在 <a>，再兜底看父容器是否 disabled
            parent_disabled = btn.find_parent(attrs={"aria-disabled": "true"}) is not None
            if not (disabled or parent_disabled):
                print("[MERCARI DETECT] found purchase button enabled -> IN_STOCK")
                return "IN_STOCK"

    # 3.2 售罄灰按钮：売り切れました / 按钮被禁用 -> OUT_OF_STOCK
    # 文字命中
    if "売り切れました" in page_text or "売り切れのため購入できません" in page_text:
        print("[MERCARI DETECT] grey sold-out button text -> OUT_OF_STOCK")
        return "OUT_OF_STOCK"

    # 明确检测禁用的按钮且文本包含“購入手続きへ”或“売り切れ”
    for btn in soup.find_all("button"):
        txt = btn.get_text(strip=True)
        if not txt:
            continue
        if ("購入手続きへ" in txt or "売り切れ" in txt) and (
            btn.has_attr("disabled") or btn.get("aria-disabled") in ("true", "1")
        ):
            print("[MERCARI DETECT] purchase button disabled / sold -> OUT_OF_STOCK")
            return "OUT_OF_STOCK"

    # ---------- 4) SOLD 丝带（仅作为弱信号） ----------
    # 仅当页面上找不到可购买按钮时，且出现明显 SOLD 丝带，再判为 OUT_OF_STOCK
    has_buy = any("購入手続きへ" in b.get_text(strip=True) for b in soup.find_all(["button", "a"]))
    ribbon = soup.find(string=re.compile(r"^\s*SOLD\s*$"))
    if (not has_buy) and ribbon:
        print("[MERCARI DETECT] only SOLD ribbon shown and no buy button -> OUT_OF_STOCK")
        return "OUT_OF_STOCK"

    # ---------- 5) 仍无法判断 ----------
    print("[MERCARI DETECT] no rule matched -> UNKNOWN")
    return "UNKNOWN"










