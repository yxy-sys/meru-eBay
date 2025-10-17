# main_yahoo.py
import os
from dotenv import load_dotenv

from sheet_reader import read_ledger
from fetcher import fetch
from detectors import yahoo
from ebay_updater import update_qty_with_fallback
from notify import notify

load_dotenv()


def _is_blank(value) -> bool:
    if value is None:
        return True
    s = str(value).strip().lower()
    return s in ("", "nan", "none", "null")


def norm_trigger(v: str) -> str:
    s = str(v or "").strip().lower()
    return "soldout" if s in ("", "nan", "none", "null") else s


def should_zero(trigger: str, status: str) -> bool:
    # 页面状态未知，一律不清 0
    if status == "UNKNOWN":
        return False
    t = norm_trigger(trigger)
    if t == "soldout":
        return status in ("OUT_OF_STOCK", "SOLD", "ENDED")
    if t == "lowstock":
        return status in ("OUT_OF_STOCK", "LOW_STOCK", "SOLD", "ENDED")
    return False


def run_once():
    df = read_ledger()
    matched = 0

    for _, row in df.iterrows():
        url = str(row.get("source_url", "") or "").strip()
        low = url.lower()
        if not url or ("yahoo.co.jp" not in low and "auctions.yahoo.co.jp" not in low):
            continue

        matched += 1
        item_id = str(row.get("ebay_item_id", "") or "").strip()
        sku     = str(row.get("sku", "") or "").strip()
        trigger = norm_trigger(row.get("trigger", ""))

        ident = sku if sku else item_id

        code, html = fetch(url)

        # ① 链接失效（404/410）→ 必清零 & 发通知（含 SKU + 链接）
        if code in (404, 410):
            print(f"[YAHOO] {url} HTTP={code} status=DELETED trigger={trigger} sku={sku or '∅'}")
            res = update_qty_with_fallback(item_id=item_id, sku=sku, quantity=0)
            if res.get("ok"):
                notify(f"🗑️ [YAHOO] 链接失效 → eBay 已清零：{ident}\nSKU: {sku or '(no-sku)'}\n{url}")
                # 机器可识别锚点，供工作流检出“真清零”
                print(f"EBAY_ZERO_OK sku={sku or ident} url={url}")
            else:
                notify(f"❌ [YAHOO] 链接失效但 eBay 清零失败：{ident}\nSKU: {sku or '(no-sku)'}\n{url}")
                print(f"EBAY_ZERO_FAIL sku={sku or ident} url={url}")
            continue

        # ② 正常页面：判定状态
        status = "UNKNOWN" if code != 200 else yahoo.detect(html)
        print(f"[YAHOO] {url} HTTP={code} status={status} trigger={trigger} sku={sku or '∅'}")

        # ③ 若不满足清零规则则跳过（不发通知）
        if not should_zero(trigger, status):
            continue

        # ④ 满足清零规则：直接尝试清 0，并在成功/失败时发通知（含 SKU + 链接）
        res = update_qty_with_fallback(item_id=item_id, sku=sku, quantity=0)
        if res.get("ok"):
            notify(f"✅ [YAHOO] eBay 已清零：{ident}\nSKU: {sku or '(no-sku)'}\n{url}")
            print(f"EBAY_ZERO_OK sku={sku or ident} url={url}")
        else:
            notify(f"❌ [YAHOO] eBay 清零失败：{ident}\nSKU: {sku or '(no-sku)'}\n{url}")
            print(f"EBAY_ZERO_FAIL sku={sku or ident} url={url}")

    if matched == 0:
        print("No Yahoo rows matched. Check headers/domains.")


if __name__ == "__main__":
    run_once()

