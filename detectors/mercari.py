# detectors/mercari.py
# -*- coding: utf-8 -*-
"""
Mercari 商品状态检测（增强版，解决 bootstrap-failed）
"""

from __future__ import annotations
import re, time
from typing import Tuple
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError

BUY_BTN_RE     = re.compile(r"(購入手続きへ|Buy now|Proceed to purchase)", re.I)
SOLD_BTN_RE    = re.compile(r"(売り切れました|SOLD OUT|販売停止中|取引中|公開停止中)", re.I)
SOLD_TXT_RE    = re.compile(r"(売り切れました|この商品は.*で配送されました|取引が終了しました|この商品は削除されました)", re.S)
SOLD_BADGE_RE  = re.compile(r"\bSOLD\b", re.I)

STATUS_IN_STOCK = "IN_STOCK"
STATUS_SOLD_OUT = "SOLD_OUT"
STATUS_UNAVAIL  = "UNAVAILABLE"
STATUS_UNKNOWN  = "UNKNOWN"


def _wait_dom(page: Page):
    """等待 DOM 稳定"""
    try:
        page.wait_for_load_state("domcontentloaded", timeout=10000)
        try:
            page.wait_for_load_state("networkidle", timeout=5000)
        except PlaywrightTimeoutError:
            pass
    except PlaywrightTimeoutError:
        pass


def detect(page: Page, wait_ms: int = 8000) -> Tuple[str, str]:
    """返回 (status, trigger)"""
    _wait_dom(page)

    # ---- 1) 主动轮询「購入手続きへ」按钮 ----
    for i in range(4):  # 共轮询 4 次 * 5s ≈ 20s
        try:
            buy_btn = page.get_by_role("button", name=BUY_BTN_RE).first
            buy_btn.wait_for(state="visible", timeout=wait_ms)
            if buy_btn.is_enabled():
                return STATUS_IN_STOCK, f"button:購入手続きへ[{i}]"
        except PlaywrightTimeoutError:
            pass
        except Exception:
            pass

        # Plan B：按 data-testid / 文本节点查找
        try:
            locator = page.locator('button[data-testid="buy-button"], text=購入手続きへ')
            if locator.count() > 0 and locator.first.is_visible():
                return STATUS_IN_STOCK, f"locator:data-testid/buy-button[{i}]"
        except Exception:
            pass
        time.sleep(5)

    # ---- 2) 售罄按钮 ----
    try:
        sold_btn = page.get_by_role("button", name=SOLD_BTN_RE).first
        sold_btn.wait_for(state="visible", timeout=2000)
        label = sold_btn.inner_text().strip()[:32] if sold_btn else "売り切れ"
        return STATUS_SOLD_OUT, f"button:{label}"
    except PlaywrightTimeoutError:
        pass
    except Exception:
        pass

    # ---- 3) 文案兜底 ----
    body_text = ""
    try:
        body_text = page.locator("body").inner_text(timeout=2000)
    except Exception:
        body_text = ""
    if SOLD_TXT_RE.search(body_text or ""):
        return STATUS_SOLD_OUT, "text:売り切れ/配送/終了"

    # ---- 4) SOLD 缎带 ----
    try:
        aria_concat = " ".join(page.locator("//*").evaluate_all(
            "els => els.map(e => e.getAttribute('aria-label')||'').join(' ')"
        ) or [])
        if SOLD_BADGE_RE.search(aria_concat):
            return STATUS_SOLD_OUT, "aria-label:SOLD"
    except Exception:
        pass

    # ---- 5) 结构化数据 ----
    try:
        ld_json_list = page.locator('script[type=\"application/ld+json\"]').all_inner_texts()
        if any('"availability"' in s for s in ld_json_list):
            joined = " ".join(ld_json_list)
            if "InStock" in joined:
                return STATUS_IN_STOCK, "ldjson:InStock"
            if any(k in joined for k in ("SoldOut", "OutOfStock", "Discontinued")):
                return STATUS_SOLD_OUT, "ldjson:SoldOut"
    except Exception:
        pass

    # ---- 6) 404 ----
    if "ページが見つかりません" in (body_text or ""):
        return STATUS_UNAVAIL, "text:ページが見つかりません"

    # ---- 7) 兜底 ----
    return STATUS_SOLD_OUT, "fallback:no-buy-button"


NAME = "mercari"
__all__ = ["detect", "NAME"]






