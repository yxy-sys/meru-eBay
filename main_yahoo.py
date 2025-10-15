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
        if not url or ("yahoo.co.jp" not in url.lower() and "auctions.yahoo.co.jp" not in url.lower()):
            continue

        matched += 1
        item_id = str(row.get("ebay_item_id", "")).strip()
        sku = str(row.get("sku", "")).strip()
        trigger = norm_trigger(row.get("trigger", ""))

        ident = sku if sku else item_id

        code, html = fetch(url)
        if code in (404, 410):
            print(f"[YAHOO] {url} HTTP={code} status=DELETED trigger={trigger} sku={sku or '∅'}")
            res = update_qty_with_fallback(item_id=item_id, sku=sku, quantity=0)
            if res.get("ok"):
                notify(f"🗑️ [YAHOO] 链接失效 → eBay 已清零：{ident}\n{url}")
            else:
                notify(f"❌ [YAHOO] 链接失效但 eBay 清零失败：{ident}\n{url}")
            continue

        status = "UNKNOWN" if code != 200 else yahoo.detect(html)
        print(f"[YAHOO] {url} HTTP={code} status={status} trigger={trigger} sku={sku or '∅'}")

        if not should_zero(trigger, status):
            continue

        notify(f"⚠️ [YAHOO] 检测到售罄：{ident}\n{url}")
        res = update_qty_with_fallback(item_id=item_id, sku=sku, quantity=0)
        if res.get("ok"):
            notify(f"✅ [YAHOO] eBay 已清零：{ident}")
        else:
            notify(f"❌ [YAHOO] eBay 清零失败：{ident}")

    if matched == 0:
        print("No Yahoo rows matched. Check headers/domains.")


if __name__ == "__main__":
    run_once()
