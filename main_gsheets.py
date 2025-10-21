# main_gsheets.py
# -*- coding: utf-8 -*-

import os
from dotenv import load_dotenv

from sheet_reader import read_ledger
from fetcher import fetch
from detectors import mercari
from ebay_updater import update_qty_with_fallback
from notify import notify

from playwright.sync_api import sync_playwright

load_dotenv()


# -------------------- 辅助函数 --------------------

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
    """组合本次清零所用的路径说明（SKU / ItemID / 回退情况）。"""
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


# -------------------- 主流程 --------------------

def run_once():
    # 读取清单（你的 sheet_reader 已做了重试/超时）
    df = read_ledger()

    matched = 0
    UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")

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
                # 只处理 Mercari
                continue

            matched += 1

            item_id_raw = row.get("ebay_item_id", "")
            sku_raw = row.get("sku", "")
            rule_trigger_raw = row.get("trigger", "")  # 表格里的“规则触发词”

            item_id = "" if _is_blank(item_id_raw) else str(item_id_raw).strip()
            sku = "" if _is_blank(sku_raw) else str(sku_raw).strip()
            rule_trigger = norm_trigger(rule_trigger_raw)

            if (not sku) and (not item_id):
                print(f"[MERCARI] {url} both SKU & ItemID missing, skip.\n")
                continue

            # —— 先 Playwright 导航（主路径）——
            det_status, det_trigger = "UNKNOWN", "navigate-fail"
            http_code = 0
            try:
                resp = page.goto(url, wait_until="domcontentloaded", timeout=35000)
                http_code = resp.status if resp else 0

                # 强判定：可点击“購入手続きへ”才判在售
                det_status, det_trigger = mercari.detect(page)

                # 极少数水合异常：再用当前 DOM 的 HTML 做一次兜底
                if det_status == "UNKNOWN":
                    html_now = page.content()
                    _s, _t = mercari.detect(html_now)
                    if _s != "UNKNOWN":
                        det_status, det_trigger = _s, f"fallback:{_t}"

            except Exception as e:
                # Playwright 导航失败：最后尝试 requests 兜底（也把 HTTP 码带上）
                try:
                    http_code, html2 = fetch(url)
                    _s, _t = mercari.detect(html2)
                    det_status = _s
                    det_trigger = f"html:{_t}"
                except Exception:
                    det_status, det_trigger = "UNKNOWN", f"exception:{type(e).__name__}"

            # 明确的 404/410（不常见，Playwright也能拿到）
            if http_code in (404, 410):
                print(f"[MERCARI] {url} HTTP-{http_code} status=DELETED trigger={rule_trigger} sku={sku or '∅'}")
                res = update_qty_with_fallback(item_id=item_id, sku=sku, quantity=0)
                print("eBay update (deleted link):", res)
                used_path = _format_used(res)
                if res.get("ok"):
                    notify(
                        f"🗑️ [MERCARI] 链接失效（HTTP {http_code}）→ eBay 已清零\n"
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
                # 删除型处理完就进入下一条
                continue

            print(f"[MERCARI] {url} HTTP-{http_code} status={det_status} trigger={det_trigger} sku={sku}")

            # —— 根据“表格里的规则触发词”决定是否清 0 —— #
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
