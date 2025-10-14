
import os
from dotenv import load_dotenv
from sheet_reader import read_ledger
from fetcher import fetch
from detectors import mercari
from ebay_updater import revise_inventory_status
from notify import notify

load_dotenv()

def norm_trigger(v):
    s = str(v or "").strip().lower()
    return "soldout" if s in ("", "nan", "none") else s

def should_zero(trigger: str, status: str) -> bool:
    t = norm_trigger(trigger)
    if t == "soldout":
        return status == "OUT_OF_STOCK"
    if t == "lowstock":
        return status in ("OUT_OF_STOCK", "LOW_STOCK")
    return False

def run_once():
    df = read_ledger()
    matched = 0
    for _, row in df.iterrows():
        url = str(row.get("source_url", "") or "").strip().lower()
        if not url or ("mercari.com" not in url and "jp.mercari.com" not in url):
            continue
        matched += 1
        item_id = str(row.get("ebay_item_id", "") or "").strip()
        sku = str(row.get("sku", "") or "").strip()
        trig = norm_trigger(row.get("trigger", ""))
        code, html = fetch(url)
        status = "UNKNOWN" if code != 200 else mercari.detect(html)
        print(f"[MERCARI] {url} HTTP={code} status={status} trigger={trig} sku={sku}")
        if should_zero(trig, status):
            res = revise_inventory_status(item_id=item_id, sku=sku, quantity=0)
            print("eBay update:", res)
            ident = sku if sku else item_id
            notify(f"[MERCARI] {ident} -> Qty 0 ({status})")
    if matched == 0:
        print("No Mercari rows matched. Check headers/domains.")

if __name__ == "__main__":
    run_once()
