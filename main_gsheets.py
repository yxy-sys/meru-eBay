# main_gsheets.py
import os
from dotenv import load_dotenv

from sheet_reader import read_ledger
from fetcher import fetch
from detectors import mercari
from ebay_updater import update_qty_with_fallback   # ✅ 改：用带回退的方法
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
    # ✅ 删除/结束统一当作需要清 0
    if status in ("DELETED", "REMOVED", "ENDED"):
        return True

    if status == "UNKNOWN":
        return False

    t = norm_trigger(trigger)
    if t == "soldout":
        return status == "OUT_OF_STOCK"
    if t == "lowstock":
        return status in ("OUT_OF_STOCK", "LOW_STOCK")
    return False


def _format_used(res: dict) -> str:
    """
    组合本次清零所用的路径说明（SKU / ItemID / 回退情况）。
    """
    if not isinstance(res, dict):
        return ""
    fb = res.get("fallback")
    first = res.get("first") or {}
    second = res.get("second") or {}
    # used 字段在 revise_inventory_status 返回里
    u1 = first.get("used")
    u2 = second.get("used")
    if fb == "item_id":
        # 先 SKU 失败，后用 ItemID 成功/失败
        return "SKU → ItemID"
    # 无回退，直接使用 first.used
    return u1 or u2 or ""


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

        # 若既无 SKU 又无 ItemID，无法清零，直接跳过但打印一行日志
        if (not sku) and (not item_id):
            print(f"[MERCARI] {url} both SKU & ItemID missing, skip.\n")
            continue

        # 抓页面
        code, html = fetch(url)

        # === 链接被删除(404/410) → 直接清 0 并通知 ===
        if code in (404, 410):
            print(f"[MERCARI] {url} HTTP={code} status=DELETED trigger={trigger} sku={sku or '∅'}")
            res = update_qty_with_fallback(item_id=item_id, sku=sku, quantity=0)
            print("eBay update (deleted link):", res)

            used_path = _format_used(res)
            if res.get("ok"):
                notify(
                    f"🗑️ [MERCARI] 链接失效（HTTP {code}）→ eBay 已清零\n"
                    f"SKU={sku or '∅'}  ItemID={item_id or '∅'}  方式={used_path}\n{url}"
                )
            else:
                last = res.get("second") or res.get("first") or {}
                status_code = last.get("status")
                body = last.get("body") or last.get("error") or res.get("error") or ""
                snippet = str(body)[:500]
                used = last.get("used") or used_path
                notify(
                    f"❌ [MERCARI] 链接失效但 eBay 清零失败\n"
                    f"SKU={sku or '∅'}  ItemID={item_id or '∅'}  方式={used}\n"
                    f"HTTP={status_code}\n{snippet}\n{url}"
                )
            continue
        # === 结束 ===

        # 判状态
        status, trigger = ("UNKNOWN", "no-http") if code != 200 else mercari.detect(page)
        print(f"[MERCARI] {url} HTTP-{code} status={status} trigger={trigger} sku={sku}")


        # 按规则决定是否清 0（should_zero 已包含 DELETED/ENDED）
        if not should_zero(trigger, status):
            # 不符合清零条件：不通知
            continue

        # ① 售罄/删除提示（前置提示）
        notify(
            f"⚠️ [MERCARI] 检测到售罄或链接失效，准备清零\n"
            f"SKU={sku or '∅'}  ItemID={item_id or '∅'}\n{url}"
        )

        # ② eBay 清 0（SKU 优先，必要时回退 ItemID）
        res = update_qty_with_fallback(item_id=item_id, sku=sku, quantity=0)
        print("eBay update:", res)

        # ③ 根据结果发通知（带 SKU 与链接）
        used_path = _format_used(res)
        if res.get("ok"):
            notify(
                f"✅ eBay 库存已清零\n"
                f"SKU={sku or '∅'}  ItemID={item_id or '∅'}  方式={used_path}\n{url}"
            )
        else:
            last = res.get("second") or res.get("first") or {}
            status_code = last.get("status")
            body = last.get("body") or last.get("error") or res.get("error") or ""
            snippet = str(body)[:500]
            used = last.get("used") or used_path
            notify(
                f"❌ eBay 清零失败\n"
                f"SKU={sku or '∅'}  ItemID={item_id or '∅'}  方式={used}\n"
                f"HTTP={status_code}\n{snippet}\n{url}"
            )

    if matched == 0:
        print("No Mercari rows matched. Check headers/domains.")


if __name__ == "__main__":
    run_once()

