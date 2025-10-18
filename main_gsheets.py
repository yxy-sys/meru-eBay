# main_gsheets.py
import os
from dotenv import load_dotenv

from sheet_reader import read_ledger
from fetcher import fetch
from detectors import mercari
from ebay_updater import revise_inventory_status
from notify import notify

load_dotenv()


def _is_blank(value) -> bool:
    """将 None / 空串 / 'nan' / 'none' / 'null' 统一当作空"""
    if value is None:
        return True
    s = str(value).strip().lower()
    return s in ("", "nan", "none", "null")


def norm_trigger(v: str) -> str:
    """把 trigger 标准化：空/无效 视作 'soldout'；其它统一转小写"""
    s = str(v or "").strip().lower()
    return "soldout" if s in ("", "nan", "none", "null") else s


def should_zero(trigger: str, status: str) -> bool:
    """
    清零规则（最小改动版）：
    - 链接被删除/结束/移除（DELETED/REMOVED/ENDED）→ 无条件清 0（与 trigger 无关）
    - trigger = soldout  -> 仅当 status == OUT_OF_STOCK
    - trigger = lowstock -> 当 status ∈ {OUT_OF_STOCK, LOW_STOCK}
    - 其它/未知           -> 不清 0
    """
    # ✅ 新增：删除/结束统一当作需要清 0
    if status in ("DELETED", "REMOVED", "ENDED"):
        return True

    # 原有逻辑
    if status == "UNKNOWN":
        return False

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
        url = str(row.get("source_url", "") or "").strip()
        if not url:
            continue
        low_url = url.lower()
        if ("mercari.com" not in low_url) and ("jp.mercari.com" not in low_url):
            # 只处理煤炉链接
            continue

        matched += 1

        item_id_raw = row.get("ebay_item_id", "")
        sku_raw = row.get("sku", "")
        trigger_raw = row.get("trigger", "")

        item_id = "" if _is_blank(item_id_raw) else str(item_id_raw).strip()
        sku = "" if _is_blank(sku_raw) else str(sku_raw).strip()
        trigger = norm_trigger(trigger_raw)

        ident = sku if sku else (item_id if item_id else "(no-id)")

        # 抓页面
        code, html = fetch(url)

        # === 链接被删除(404/410) → 直接清 0 并通知（沿用你原逻辑） ===
        if code in (404, 410):
            print(f"[MERCARI] {url} HTTP={code} status=DELETED trigger={trigger} sku={sku or '∅'}")
            res = revise_inventory_status(item_id=item_id, sku=sku, quantity=0)
            print("eBay update (deleted link):", res)
            if res.get("ok"):
                notify(f"🗑️ [MERCARI] 链接失效（HTTP {code}）→ eBay 已清零：{ident}\n{url}")
            else:
                status_code = res.get("status")
                body = res.get("body") or res.get("error") or ""
                snippet = str(body)[:500]
                notify(f"❌ 链接失效但 eBay 清零失败：{ident}\nHTTP={status_code}\n{snippet}\n{url}")
            continue
        # === 结束 ===

        # 判状态
        status = "UNKNOWN" if code != 200 else mercari.detect(html)

        print(f"[MERCARI] {url} HTTP={code} status={status} trigger={trigger} sku={sku or '∅'}")

        # 按规则决定是否清 0（此处的 should_zero 已把 DELETED/ENDED 视为需要清 0）
        if not should_zero(trigger, status):
            # 同步成功但没清 0：不通知
            continue

        # ① 售罄/删除提示
        notify(f"⚠️ 检测到煤炉售罄或链接失效：{ident}\n{url}")

        # ② 调用 eBay 清 0
        res = revise_inventory_status(item_id=item_id, sku=sku, quantity=0)
        print("eBay update:", res)

        # ③ 根据 eBay 结果发通知
        if res.get("ok"):
            notify(f"✅ eBay 库存已清零：{ident}")
        else:
            status_code = res.get("status")
            body = res.get("body") or res.get("error") or ""
            snippet = str(body)[:500]
            notify(f"❌ eBay 清零失败：{ident}\nHTTP={status_code}\n{snippet}")

    if matched == 0:
        print("No Mercari rows matched. Check headers/domains.")


if __name__ == "__main__":
    run_once()

