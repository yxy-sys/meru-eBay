# main_gsheets.py
import os
from dotenv import load_dotenv

from sheet_reader import read_ledger
from fetcher import fetch
from detectors import mercari
from ebay_updater import update_qty_with_fallback
from notify import notify

# ✨ 新增：用 Page 做强判定，性能考虑整段复用一个浏览器/上下文
from playwright.sync_api import sync_playwright

load_dotenv()


def _is_blank(value) -> bool:
    if value is None:
        return True
    s = str(value).strip().lower()
    return s in ("", "nan", "none", "null")


def norm_trigger(v: str) -> str:
    s = str(v or "").strip().lower()
    return "soldout" if s in ("", "nan", "none", "null") else s


def should_zero(rule_trigger: str, status: str) -> bool:
    """
    清零规则（按表格里的规则触发词）：
    - 链接被删除/结束/移除（DELETED/REMOVED/ENDED）→ 无条件清 0
    - rule_trigger = soldout  -> 仅当 status == OUT_OF_STOCK
    - rule_trigger = lowstock -> 当 status ∈ {OUT_OF_STOCK, LOW_STOCK}
    """
    if status in ("DELETED", "REMOVED", "ENDED"):
        return True
    if status == "UNKNOWN":
        return False

    t = norm_trigger(rule_trigger)
    if t == "soldout":
        return status == "OUT_OF_STOCK"
    if t == "lowstock":
        return status in ("OUT_OF_STOCK", "LOW_STOCK")
    return False


def _format_used(res: dict) -> str:
    if not isinstance(res, dict):
        return ""
    fb = res.get("fallback")
    first = res.get("first") or {}
    second = res.get("second") or {}
    u1 = first.get("used")
    u2 = second.get("used")
    if fb == "item_id":
        return "SKU → ItemID"
    return u1 or u2 or ""


def run_once():
    df = read_ledger()
    matched = 0

    UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")

    # —— 打开一次浏览器，循环内复用 —— #
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(
            locale="ja-JP",
            user_agent=UA,
            viewport={"width": 1280, "height": 900},
            java_script_enabled=True,
        )
        page = ctx.new_page()

        for _, row in df.iterrows():
            url = str(row.get("source_url", "") or "").strip()
            if not url:
                continue
            low_url = url.lower()
            if ("mercari.com" not in low_url) and ("jp.mercari.com" not in low_url):
                continue

            matched += 1

            item_id_raw = row.get("ebay_item_id", "")
            sku_raw = row.get("sku", "")
            rule_trigger_raw = row.get("trigger", "")  # 表里的规则触发词

            item_id = "" if _is_blank(item_id_raw) else str(item_id_raw).strip()
            sku = "" if _is_blank(sku_raw) else str(sku_raw).strip()
            rule_trigger = norm_trigger(rule_trigger_raw)

            if (not sku) and (not item_id):
                print(f"[MERCARI] {url} both SKU & ItemID missing, skip.\n")
                continue

            # 抓页面（requests）用于拿 HTTP 码 & HTML 兜底
            code, html = fetch(url)

            # === 404/410：直接按删除处理 ===
            if code in (404, 410):
                print(f"[MERCARI] {url} HTTP={code} status=DELETED trigger={rule_trigger} sku={sku or '∅'}")
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
            # === end ===

            # —— 判状态（优先 Page；失败回退 HTML）——
            det_status, det_trigger = "UNKNOWN", "no-http"
            if code == 200:
                try:
                    resp = page.goto(url, wait_until="domcontentloaded", timeout=30000)
                    _ = resp.status if resp else 0  # 以防 None
                    det_status, det_trigger = mercari.detect(page)
                except Exception:
                    # Playwright 导航失败：回退用 HTML 兜底
                    det_status, det_trigger = mercari.detect(html)
            else:
                det_status, det_trigger = mercari.detect(html)

            print(f"[MERCARI] {url} HTTP-{code} status={det_status} trigger={det_trigger} sku={sku}")

            # —— 根据表内“规则触发词”决定是否清 0 —— #
            if not should_zero(rule_trigger, det_status):
                continue

            # ① 提示
            notify(
                f"⚠️ [MERCARI] 检测到售罄/失效，准备清零\n"
                f"SKU={sku or '∅'}  ItemID={item_id or '∅'}\n"
                f"检测={det_status}/{det_trigger}\n{url}"
            )

            # ② eBay 清 0（SKU 优先，必要时回退 ItemID）
            res = update_qty_with_fallback(item_id=item_id, sku=sku, quantity=0)
            print("eBay update:", res)

            # ③ 根据结果通知
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

        ctx.close()
        browser.close()

    if matched == 0:
        print("No Mercari rows matched. Check headers/domains.")


if __name__ == "__main__":
    run_once()

