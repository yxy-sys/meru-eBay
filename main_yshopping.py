# main_yshopping.py
import os
from dotenv import load_dotenv

from sheet_reader import read_ledger
from fetcher import fetch
from detectors import yshopping
from ebay_updater import revise_inventory_status  # 也可换成 update_qty_with_fallback
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
    if status == "UNKNOWN":
        return False
    t = norm_trigger(trigger)
    if t == "soldout":
        return status == "OUT_OF_STOCK"
    if t == "lowstock":
        return status in ("OUT_OF_STOCK", "LOW_STOCK")
    return False

def _looks_yshopping(url: str) -> bool:
    u = (url or "").lower()
    return ("shopping.yahoo.co.jp" in u) or ("store.shopping.yahoo.co.jp" in u)

def run_once():
    df = read_ledger()
    matched = 0

    for _, row in df.iterrows():
        url = str(row.get("source_url", "") or "").strip()
        if not url or not _looks_yshopping(url):
            continue
        matched += 1

        item_id = "" if _is_blank(row.get("ebay_item_id")) else str(row.get("ebay_item_id")).strip()
        sku     = "" if _is_blank(row.get("sku")) else str(row.get("sku")).strip()
        trigger = norm_trigger(row.get("trigger", ""))

        ident = sku if sku else (item_id if item_id else "(no-id)")

        code, html = fetch(url)

        # 链接失效：404/410 -> 必清零 + 通知
        if code in (404, 410):
            print(f"[Y!SHOP] {url} HTTP={code} status=DELETED trigger={trigger} sku={sku or '∅'}")
            res = revise_inventory_status(item_id=item_id, sku=sku, quantity=0)
            print("eBay update (deleted link):", res)
            if res.get("ok"):
                notify(f"🗑️ [Y!Shopping] 链接失效（HTTP {code}）→ eBay 已清零：{ident}\n{url}")
            else:
                status_code = res.get("status")
                body = res.get("body") or res.get("error") or ""
                snippet = str(body)[:500]
                notify(f"❌ [Y!Shopping] 链接失效但 eBay 清零失败：{ident}\nHTTP={status_code}\n{snippet}\n{url}")
            continue

        status = "UNKNOWN" if code != 200 else yshopping.detect(html)
        price  = None if code != 200 else yshopping.extract_price(html)

        print(f"[Y!SHOP] {url} HTTP={code} status={status} price={price} trigger={trigger} sku={sku or '∅'}")

        # 状态未知：跳过（不动作，不通知）
        if status == "UNKNOWN":
            print(f"SKIP: {ident} status UNKNOWN, no action.\n")
            continue

        # 一、售罄/无货规则 → 清 0 + 通知
        if should_zero(trigger, status):
            notify(f"⚠️ [Y!Shopping] 检测到售罄：{ident}\n{url}")
            res = revise_inventory_status(item_id=item_id, sku=sku, quantity=0)
            print("eBay update (zero):", res)
            if res.get("ok"):
                notify(f"✅ eBay 库存已清零：{ident}")
            else:
                status_code = res.get("status")
                body = res.get("body") or res.get("error") or ""
                snippet = str(body)[:500]
                notify(f"❌ eBay 清零失败：{ident}\nHTTP={status_code}\n{snippet}")
            continue

        # 二、价格联动（仅当能取到 current_price 才处理）
        # 你的表里建议再加一列：y_price_last（上次记录的 Yahoo 价），也可简单用 eBay 现价去对比。
        # 这里先示例：和上一轮记录相比（若你存到 Google Sheet，可扩展读写逻辑）
        # ——为了不改你现有表结构，这里用“仅涨价时涨差×1.3”思路，但需要你提供 eBay 当前价取得方式。
        # 如果你还没有 eBay 当前价接口，就先仅通知（下面保留通知代码），等你提供 eBay 现价再补调价。

        if price is not None:
            # TODO: 若需要自动涨价：需要拿到 eBay 当前价格（例如你在表里有一列 ebay_price 或 API 拉当前价格）
            # 假设我们暂时没有 eBay 现价，就做“降价/涨价通知”——不改价
            # 你可以后续把逻辑换成：若 price > last_price => 计算差额×1.3 调整 eBay
            notify(f"ℹ️ [Y!Shopping] 当前价 ¥{price}：{ident}\n（如需自动联动涨价，请提供 eBay 当前售价来源）\n{url}")

    if matched == 0:
        print("No Yahoo Shopping rows matched. Check headers/domains.")


if __name__ == "__main__":
    run_once()
