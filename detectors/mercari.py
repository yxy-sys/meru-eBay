# detectors/mercari.py
# -*- coding: utf-8 -*-
"""
Mercari 商品状态检测（兼容 Page 与 HTML 字符串）
- detect(obj, wait_ms=8000) -> (status, trigger)
- obj 可以是 playwright.sync_api.Page 或 str(HTML)
状态：IN_STOCK / SOLD_OUT / UNAVAILABLE / UNKNOWN
"""

from __future__ import annotations
import re, time
from typing import Tuple, Any

try:
    # 在 Actions 环境没有安装 Playwright 时，给个哑类型
    from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError  # type: ignore
except Exception:  # pragma: no cover
    Page = Any  # type: ignore
    class PlaywrightTimeoutError(Exception):  # type: ignore
        pass

# ---- 文案/正则特征 ----
BUY_BTN_RE     = re.compile(r"(購入手続きへ|Buy now|Proceed to purchase)", re.I)
SOLD_BTN_RE    = re.compile(r"(売り切れました|SOLD OUT|販売停止中|取引中|公開停止中)", re.I)
SOLD_TXT_RE    = re.compile(r"(売り切れました|この商品は.*で配送されました|取引が終了しました|この商品は削除されました)", re.S)
SOLD_BADGE_RE  = re.compile(r"\bSOLD\b", re.I)

STATUS_IN_STOCK = "IN_STOCK"
STATUS_SOLD_OUT = "SOLD_OUT"
STATUS_UNAVAIL  = "UNAVAILABLE"
STATUS_UNKNOWN  = "UNKNOWN"


# ===================== HTML 兜底版 =====================

def _detect_from_html(html: str) -> Tuple[str, str]:
    """在 HTTP!=200 或者拿到的是静态 HTML 时的兜底判定"""
    if not html:
        return STATUS_UNKNOWN, "html:empty"

    # ---- 更严格 404 判定 ----
    # 真正的 Mercari 404 页面会包含这两个条件：
    # 1. “このページは存在しません” 或 “ページが見つかりません”
    # 2. 同时 <title> 中也包含 “404” 或 “メルカリ”
    if ("このページは存在しません" in html or "ページが見つかりません" in html) and "<title" in html:
        return STATUS_UNAVAIL, "html:404"

    # ---- JSON-LD availability ----
    if '"availability"' in html:
        if "InStock" in html:
            return STATUS_IN_STOCK, "html:ldjson-InStock"
        if any(k in html for k in ("SoldOut", "OutOfStock", "Discontinued")):
            return STATUS_SOLD_OUT, "html:ldjson-SoldOut"

    # ---- 购买按钮/文案 ----
    if BUY_BTN_RE.search(html):
        return STATUS_IN_STOCK, "html:text:購入手続きへ"

    # ---- 售罄文案 ----
    if SOLD_BTN_RE.search(html) or SOLD_TXT_RE.search(html) or SOLD_BADGE_RE.search(html):
        return STATUS_SOLD_OUT, "html:text:soldout"

    return STATUS_UNKNOWN, "html:no-signal"


# ===================== Page 强判定版 =====================

def _wait_dom(page: "Page"):
    try:
        page.wait_for_load_state("domcontentloaded", timeout=10000)
        try:
            page.wait_for_load_state("networkidle", timeout=5000)
        except PlaywrightTimeoutError:
            pass
    except PlaywrightTimeoutError:
        pass

def _detect_from_page(page: "Page", wait_ms: int = 8000) -> Tuple[str, str]:
    _wait_dom(page)

    # 1) 多轮等待“購入手続きへ”
    for i in range(4):  # 约 20 秒
        try:
            buy_btn = page.get_by_role("button", name=BUY_BTN_RE).first
            buy_btn.wait_for(state="visible", timeout=wait_ms)
            if buy_btn.is_enabled():
                return STATUS_IN_STOCK, f"button:購入手続きへ[{i}]"
        except PlaywrightTimeoutError:
            pass
        except Exception:
            pass

        # 备选：data-testid/文本
        try:
            locator = page.locator('button[data-testid="buy-button"], text=購入手続きへ')
            if locator.count() > 0 and locator.first.is_visible():
                return STATUS_IN_STOCK, f"locator:buy-button[{i}]"
        except Exception:
            pass

        time.sleep(5)

    # 2) 售罄按钮
    try:
        sold_btn = page.get_by_role("button", name=SOLD_BTN_RE).first
        sold_btn.wait_for(state="visible", timeout=2000)
        label = sold_btn.inner_text().strip()[:32] if sold_btn else "売り切れ"
        return STATUS_SOLD_OUT, f"button:{label}"
    except PlaywrightTimeoutError:
        pass
    except Exception:
        pass

    # 3) 售罄/已配送完成等文案
    body_text = ""
    try:
        body_text = page.locator("body").inner_text(timeout=2000)
    except Exception:
        body_text = ""
    if SOLD_TXT_RE.search(body_text or ""):
        return STATUS_SOLD_OUT, "text:売り切れ/配送/終了"

    # 4) SOLD 缎带（aria-label）
    try:
        aria_concat = " ".join(page.locator("//*").evaluate_all(
            "els => els.map(e => e.getAttribute('aria-label')||'').join(' ')"
        ) or [])
        if SOLD_BADGE_RE.search(aria_concat):
            return STATUS_SOLD_OUT, "aria-label:SOLD"
    except Exception:
        pass

    # 5) 结构化数据
    try:
        ld_json_list = page.locator('script[type="application/ld+json"]').all_inner_texts()
        if any('"availability"' in s for s in ld_json_list):
            joined = " ".join(ld_json_list)
            if "InStock" in joined:
                return STATUS_IN_STOCK, "ldjson:InStock"
            if any(k in joined for k in ("SoldOut", "OutOfStock", "Discontinued")):
                return STATUS_SOLD_OUT, "ldjson:SoldOut"
    except Exception:
        pass

    # 6) 404
    if "ページが見つかりません" in (body_text or ""):
        return STATUS_UNAVAIL, "text:ページが見つかりません"

    # 7) 兜底（保守）
    return STATUS_SOLD_OUT, "fallback:no-buy-button"


# ===================== 统一入口 =====================

def detect(obj: Any, wait_ms: int = 8000) -> Tuple[str, str]:
    """
    obj: playwright Page 或 str(HTML)
    """
    # Page 路径
    try:
        from playwright.sync_api import Page as _P  # 防止类型比较失败
        if isinstance(obj, _P):
            return _detect_from_page(obj, wait_ms=wait_ms)
    except Exception:
        pass

    # HTML 路径
    if isinstance(obj, str):
        return _detect_from_html(obj)

    # 未知类型
    return STATUS_UNKNOWN, "bad-arg"


NAME = "mercari"
__all__ = ["detect", "NAME",
           "STATUS_IN_STOCK", "STATUS_SOLD_OUT", "STATUS_UNAVAIL", "STATUS_UNKNOWN"]

