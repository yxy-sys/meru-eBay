# main_amazon.py
# 规则：
# - 链接被删除(HTTP 404/410) -> 一定清0并通知
# - 根据 trigger(你手工填写) 与 页面状态(status) 是否匹配来决定清0：
#     trigger = "manual"      -> 任意状态清0
#     trigger = "soldout"     -> 仅当 status == OUT_OF_STOCK 清0
#     trigger = "lowstock"    -> 当 status ∈ {OUT_OF_STOCK, LOW_STOCK} 清0
#     trigger 为空/none       -> 仅当 status == OUT_OF_STOCK 清0
#     其他值                  -> 不清0
# - 清0成功/失败都会通知；不清0不通知

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
    return s in ("", "nan", "none", "null")


def norm_trigger(v: str) -> str:
    s = str(v or "").strip().lower()
    if s in ("nan", "none", "null"):
        return ""
    return s


def _looks_amazon(url: str) -> bool:
    return "amazon.co.jp" in (url or "").lower()


def should_zero(trigger: str, status: str, http_code: int) -> bool:
    """根据 trigger + 页面状态 + HTTP 码综合判断是否清 0"""
    # ① 链接被删除：优先清零
    if http_code in (404, 410):
        return True

    # ② 依据 trigger 与页面状态匹配
    t = norm_trigger(trigger)
    if status == "UNKNOWN":
        return False

    if t == "manual":
        return True
    if t == "soldout":
        return status == "OUT_OF_STOCK"
    if t == "lowstock":
        return status in ("OUT_OF_STOCK", "LOW_STOCK")
    if t in ("", "none"):
        return status == "OUT_OF_STOCK"

    # 其他自定义值 -> 不清零
    return False


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
        trigger = norm_trigger(row.get("trigger", ""))  # 你在表格里手工填写

        ident = sku if sku else (item_id if item_id else "(no-id)")

        # 抓页面
        code, html = fetch(url)

        # 解析状态/价格（价格仅供日志参考，不触发清零）
        status = "UNKNOWN" if code != 200 else amazon.detect(html)
        price  = None if code != 200 else amazon.extract_price(html)

        print(f"[AMAZON] {url} HTTP={code} status={status} price={price} trigger={trigger or '∅'} sku={sku or '∅'}")

        # 判断是否需要清 0
        if not should_zero(trigger, status, code):
            print(f"SKIP: {ident} (no clear). trigger={trigger or '∅'} status={status}\n")
            continue

        # 执行清 0（SKU 优先，SKU无效则自动回退到 ItemID）
        reason = "link_deleted" if code in (404, 410) else f"trigger_match:{trigger or 'auto'}"
        print(f"[AMAZON] CLEAR_ZERO attempt: {ident} reason={reason}")

        res = update_qty_with_fallback(item_id=item_id, sku=sku, quantity=0)
        print("eBay update:", res)

        # 通知结果（只在真正执行清 0 后才通知）
        if res.get("ok"):
            notify(f"✅ eBay 库存已清零：{ident}\n原因：{reason}\n{url}")
        else:
            status_code = res.get("status")
            body = res.get("body") or res.get("error") or ""
            snippet = str(body)[:500]
            notify(f"❌ eBay 清零失败：{ident}\n原因：{reason}\nHTTP={status_code}\n{snippet}\n{url}")

    if matched == 0:
        print("No Amazon rows matched. Check headers/domains.")


if __name__ == "__main__":
    run_once()
