# detectors/mercari.py
# -*- coding: utf-8 -*-
"""
Mercari 商品状态检测（稳定版）
判定原则：
  - 仅当页面上出现并可点击的「購入手続きへ」按钮时，判定为 IN_STOCK
  - 否则依次检测售罄按钮/文案/SOLD 缎带/LD-JSON 结构化数据/404 文案
  - 都未命中时，出于保守策略按 SOLD_OUT（fallback）返回
对外接口：
  detect(page: Page, wait_ms: int = 8000) -> tuple[str, str]
"""

from __future__ import annotations
import re
from typing import Tuple
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError

# ---- 文案特征（尽量只用可见文本/ARIA，避免样式类名） ----
BUY_BTN_RE     = re.compile(r"(購入手続きへ|Buy now|Proceed to purchase)", re.I)
SOLD_BTN_RE    = re.compile(r"(売り切れました|SOLD OUT|販売停止中|取引中|公開停止中)", re.I)
SOLD_TXT_RE    = re.compile(r"(売り切れました|この商品は.*で配送されました|取引が終了しました|この商品は削除されました)", re.S)
SOLD_BADGE_RE  = re.compile(r"\bSOLD\b", re.I)

STATUS_IN_STOCK = "IN_STOCK"
STATUS_SOLD_OUT = "SOLD_OUT"
STATUS_UNAVAIL  = "UNAVAILABLE"
STATUS_UNKNOWN  = "UNKNOWN"

def detect(page: Page, wait_ms: int = 8000) -> Tuple[str, str]:
    """
    入口：返回 (status, trigger)
    status ∈ {"IN_STOCK","SOLD_OUT","UNAVAILABLE","UNKNOWN"}
    trigger 用于日志定位命中规则
    """
    # --- 等首屏和尽量网络静默（Mercari 为 Next.js，需等水合） ---
    try:
        page.wait_for_load_state("domcontentloaded")
        try:
            page.wait_for_load_state("networkidle", timeout=5000)
        except PlaywrightTimeoutError:
            # 某些资源长连，允许忽略
            pass
    except Exception:
        # 页面都没起好，给个保守结果
        return STATUS_SOLD_OUT, "bootstrap-failed"

    # 1) 唯一正向：可见且可点击的“購入手続きへ”
    try:
        buy_btn = page.get_by_role("button", name=BUY_BTN_RE).first
        buy_btn.wait_for(state="visible", timeout=wait_ms)
        if buy_btn.is_enabled():
            return STATUS_IN_STOCK, "button:購入手続きへ"
    except PlaywrightTimeoutError:
        pass
    except Exception:
        pass

    # 2) 售罄按钮（灰色/不可点击）
    try:
        sold_btn = page.get_by_role("button", name=SOLD_BTN_RE).first
        sold_btn.wait_for(state="visible", timeout=2000)
        try:
            label = sold_btn.inner_text().strip()
        except Exception:
            label = "売り切れ"
        return STATUS_SOLD_OUT, f"button:{label[:32]}"
    except PlaywrightTimeoutError:
        pass
    except Exception:
        pass

    # 3) 售罄/已配送完成等文案兜底
    body_text = ""
    try:
        body_text = page.locator("body").inner_text(timeout=2000)
    except Exception:
        body_text = ""
    if SOLD_TXT_RE.search(body_text or ""):
        return STATUS_SOLD_OUT, "text:売り切れ/配送/終了"

    # 4) SOLD 缎带（常出现在无障碍 aria-label）
    try:
        aria_concat = " ".join(page.locator("//*").evaluate_all(
            "els => els.map(e => e.getAttribute('aria-label')||'').join(' ')"
        ) or [])
        if SOLD_BADGE_RE.search(aria_concat):
            return STATUS_SOLD_OUT, "aria-label:SOLD"
    except Exception:
        pass

    # 5) 结构化数据 availability
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

    # 6) 404/已删除
    if "ページが見つかりません" in (body_text or ""):
        return STATUS_UNAVAIL, "text:ページが見つかりません"

    # 7) 最保守兜底：看不到购买按钮就视为不可购买
    return STATUS_SOLD_OUT, "fallback:no-buy-button"


# 便于外部统一导入
NAME = "mercari"
__all__ = ["detect", "NAME",
           "STATUS_IN_STOCK", "STATUS_SOLD_OUT", "STATUS_UNAVAIL", "STATUS_UNKNOWN"]







