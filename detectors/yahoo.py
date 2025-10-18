# main_yahoo.py
import os
from dotenv import load_dotenv

from sheet_reader import read_ledger
from fetcher import fetch
from detectors import yahoo
from ebay_updater import update_qty_with_fallback
from notify import notify

load_dotenv()


# ---------- 小工具 ----------
def _is_blank(value) -> bool:
    if value is None:
        return True
    s = str(value).strip().lower()
    return s in ("", "nan", "none", "null", "")


def _norm(v) -> str:
    return "" if _is_blank(v) else str(v).strip()


def _norm_trigger(v: str) -> str:
    """触发原因：空值默认 'soldout'；其他转小写。"""
    s = str(v or "").strip().lower()
    return "soldout" if s in ("", "nan", "none", "null", "") else s


def _read_qty_from_row(row) -> int:
    """
    从表格行里取目前 eBay 数量，用于避免重复清零/重复通知。
    依次尝试：quantity、qty、ebay_qty；没有就返回 999 代表未知（不阻止清零）。
    """
    for key in ("quantity", "qty", "ebay_qty"):
        if key in row:
            v = row.get(key)
            try:
                return int(float(str(v).strip()))
            except Exception:
                pass
    return 999  # 未提供数量列时，不阻止动作


def _should_zero(trigger: str, status: str) -> bool:
    """
    清零判断：
      - trigger = soldout  -> 仅当 status in {"OUT_OF_STOCK", "SOLD", "ENDED"}
      - trigger = lowstock -> 当 status in {"OUT_OF_STOCK", "LOW_STOCK", "SOLD", "ENDED"}
      - status = UNKNOWN   -> 不清
    """
    if status == "UNKNOWN":
        return False
    t = _norm_trigger(trigger)
    if t == "soldout":
        return status in ("OUT_OF_STOCK", "SOLD", "ENDED")
    if t == "lowstock":
        return status in ("OUT_OF_STOCK", "LOW_STOCK", "SOLD", "ENDED")
    return False


def _looks_yahoo(url: str) -> bool:
    u = (url or "").lower()
    return ("yahoo.co.jp" in u) or ("yahoo.jp" in u)


# ---------- 主流程 ----------
def run_once():
    df = read_ledger()
    matched = 0

    for _, row in df.iterrows():
        url = _norm(row.get("source_url"))
        if not url or not _looks_yahoo(url):
            continue

        matched += 1

        item_id = _norm(row.get("ebay_item_id"))
        sku     = _norm(row.get("sku"))
        trigger = _norm_trigger(row.get("trigger", ""))

        ident = sku if sku else (item_id if item_id else "(no-id)")

        # 拉页面
        code, html = fetch(url)

        # 链接失效：404/410 -> 强制清零 + 通知（带 SKU + 链接）
        if code in (404, 410):
            print(f"[YAHOO] {url} HTTP={code} status=DELETED trigger={trigger} sku={sku or '∅'}")
            # 避免重复清零：如果表格数量列已经是 0，则跳过
            qty_now = _read_qty_from_row(row)
            if qty_now == 0:
                print(f"[YAHOO] {ident} already 0 (deleted link), skip notify/clear.")
                continue

            res = update_qty_with_fallback(item_id=item_id, sku=sku, quantity=0)
            if res.get("ok"):
                notify(f"🗑️ [YAHOO] 链接失效 → eBay 已清零\nSKU: {sku or '(no-sku)'}\n{url}")
            else:
                notify(f"❌ [YAHOO] 链接失效但 eBay 清零失败：{ident}\n{url}")
            continue

        # 判状态
        status = "UNKNOWN" if code != 200 else yahoo.detect(html)
        print(f"[YAHOO] {url} HTTP={code} status={status} trigger={trigger} sku={sku or '∅'}")

        # 状态不明 -> 跳过
        if status == "UNKNOWN":
            print(f"[YAHOO] SKIP: {ident} status UNKNOWN, no action.\n")
            continue

        # 不符合触发条件 -> 跳过
        if not _should_zero(trigger, status):
            continue

        # 避免重复清零：若表格里数量已经是 0，就不再发通知/清零
        qty_now = _read_qty_from_row(row)
        if qty_now == 0:
            print(f"[YAHOO] {ident} already 0, skip notify/clear.")
            continue

        # 走清零流程（并带 SKU、链接到通知中）
        notify(f"⚠️ [YAHOO] 检测到售罄：{ident}\nSKU: {sku or '(no-sku)'}\n{url}")
        res = update_qty_with_fallback(item_id=item_id, sku=sku, quantity=0)
        if res.get("ok"):
            notify(f"✅ [YAHOO] eBay 已清零\nSKU: {sku or '(no-sku)'}\n{url}")
        else:
            notify(f"❌ [YAHOO] eBay 清零失败：{ident}\n{url}")

    if matched == 0:
        print("No Yahoo rows matched. Check headers/domains.")


if __name__ == "__main__":
    run_once()

