# main_amazon.py
import os
from dotenv import load_dotenv

from sheet_reader import read_ledger
from fetcher import fetch
from detectors import amazon
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
    return "soldout" if s in ("", "nan", "none", "null") else s


def should_zero(trigger: str, status: str) -> bool:
    """
    清零规则：
      - trigger = soldout  -> 仅当 status == OUT_OF_STOCK
      - trigger = lowstock -> 当 status ∈ {OUT_OF_STOCK, LOW_STOCK}
    """
    if status == "UNKNOWN":
        return False
    t = norm_trigger(trigger)
    if t == "soldout":
        return status == "OUT_OF_STOCK"
    if t == "lowstock":
        return status in ("OUT_OF_STOCK", "LOW_STOCK")
    return False


def _looks_amazon(url: str) -> bool:
    u = (url or "").lower()
    return "amazon.co.jp" in u


def run_once():
    df = read_ledger()
    matched = 0

    for _, row in df.iterrows():
        url = str(row.get("source_url", "") or "").strip()
        if not url or not _looks_amazon(url):
            continue
        matched += 1

        item_id = "" if _is_blank(row.get("ebay_item_id")) else str(row.get("ebay_item_id")).strip()
        sku     = "" if _is_blank(row.get("sku")) else str(row.get("sku")).strip()
        trigger = norm_trigger(row.get("trigger", ""))

        ident = sku if sku else (item_id if item_id else "(no-id)")

        # 抓页面
        code, html = fetch(url)

        # 链接失效：404/410 -> 必清零 + 通知
        if code in (404, 410):
            print(f"[AMAZON] {url} HTTP={code} status=DELETED trigger={trigger} sku={sku or '∅'}")
            res = update_qty_with_fallback(item_id=item_id, sku=sku, quantity=0)
            print("eBay update (deleted link):", res)
            if res.get("ok"):
                notify(f"🗑️ [AMAZON] 链接失效（HTTP {code}）→ eBay 已清零：{ident}\n{url}")
            else:
                status_code = res.get("status")
                body = res.get("body") or res.get("error") or ""
                snippet = str(body)[:500]
                notify(f"❌ [AMAZON] 链接失效但 eBay 清零失败：{ident}\nHTTP={status_code}\n{snippet}\n{url}")
            continue

        status = "UNKNOWN" if code != 200 else amazon.detect(html)
        price  = None if code != 200 else amazon.extract_price(html)

        print(f"[AMAZON] {url} HTTP={code} status={status} price={price} trigger={trigger} sku={sku or '∅'}")

        # 状态未知：跳过（不动作，不通知）
        if status == "UNKNOWN":
            print(f"SKIP: {ident} status UNKNOWN, no action.\n")
            continue

        # 一、售罄/无货规则 → 清 0 + 通知
        if should_zero(trigger, status):
            notify(f"⚠️ [AMAZON] 检测到售罄：{ident}\n{url}")
            res = update_qty_with_fallback(item_id=item_id, sku=sku, quantity=0)
            print("eBay update (zero):", res)
            if res.get("ok"):
                notify(f"✅ eBay 库存已清零：{ident}")
            else:
                status_code = res.get("status")
                body = res.get("body") or res.get("error") or ""
                snippet = str(body)[:500]
                notify(f"❌ eBay 清零失败：{ident}\nHTTP={status_code}\n{snippet}")
            continue

        # 二、价格联动提示（不自动改价；等你提供 eBay 当前价/表格列后可接入自动提价逻辑）
        if price is not None:
            notify(f"ℹ️ [AMAZON] 当前价 ¥{price}：{ident}\n{url}")

    if matched == 0:
        print("No Amazon rows matched. Check headers/domains.")


if __name__ == "__main__":
    run_once()
