import os
from dotenv import load_dotenv

from sheet_reader import read_ledger
from fetcher import fetch
from detectors import dorasuta
from ebay_updater import update_qty_with_fallback
from notify import notify

load_dotenv()


def _is_blank(v) -> bool:
    if v is None:
        return True
    s = str(v).strip().lower()
    return s in ("", "nan", "none", "null", "")


def norm_trigger(v: str) -> str:
    s = str(v or "").strip().lower()
    return "soldout" if s in ("", "nan", "none", "null", "") else s


def should_zero(trigger: str, status: str) -> bool:
    """售罄逻辑与 Yahoo 版保持一致"""
    if status == "UNKNOWN":
        return False
    t = norm_trigger(trigger)
    if t == "soldout":
        return status in ("OUT_OF_STOCK", "SOLD", "ENDED")
    if t == "lowstock":
        return status in ("OUT_OF_STOCK", "LOW_STOCK", "SOLD", "ENDED")
    return False


def _looks_dorasuta(url: str) -> bool:
    u = (url or "").lower()
    return "dorasuta.jp" in u


def run_once():
    df = read_ledger()
    matched = 0

    for _, row in df.iterrows():
        url = str(row.get("source_url", "") or "").strip()
        if not url or not _looks_dorasuta(url):
            continue
        matched += 1

        item_id = "" if _is_blank(row.get("ebay_item_id")) else str(row.get("ebay_item_id")).strip()
        sku     = "" if _is_blank(row.get("sku")) else str(row.get("sku")).strip()
        trigger = norm_trigger(row.get("trigger", ""))

        ident = sku if sku else (item_id if item_id else "(no-id)")

        code, html = fetch(url)
        if code in (404, 410):
            print(f"[DORASUTA] {url} HTTP={code} status=DELETED trigger={trigger} sku={sku or '∅'}")
            res = update_qty_with_fallback(item_id=item_id, sku=sku, quantity=0)
            if res.get("ok"):
                notify(f"🗑️ [DORASUTA] 链接失效 → eBay 已清零：{ident}\nSKU: {sku or '-'}\n{url}")
            else:
                notify(f"❌ [DORASUTA] 链接失效但 eBay 清零失败：{ident}\n{url}")
            continue

        status = "UNKNOWN" if code != 200 else dorasuta.detect(html)
        print(f"[DORASUTA] {url} HTTP={code} status={status} trigger={trigger} sku={sku or '∅'}")

        if not should_zero(trigger, status):
            continue

        notify(f"⚠️ [DORASUTA] 检测到售罄：{ident}\nSKU: {sku or '-'}\n{url}")
        res = update_qty_with_fallback(item_id=item_id, sku=sku, quantity=0)
        if res.get("ok"):
            notify(f"✅ [DORASUTA] eBay 已清零：{ident}\nSKU: {sku or '-'}\n{url}")
        else:
            notify(f"❌ [DORASUTA] eBay 清零失败：{ident}\n{url}")

    if matched == 0:
        print("No Dorasuta rows matched. Check source_url/domain.")


if __name__ == "__main__":
    run_once()
