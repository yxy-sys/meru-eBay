# ebay_update.py
import os
import re
import requests
from xml.sax.saxutils import escape

EBAY_ENDPOINT = "https://api.ebay.com/ws/api.dll"


def _is_blank(value) -> bool:
    """判断空值：None、空串、'nan'、'none'、'null'、'na' 都视为空。"""
    if value is None:
        return True
    s = str(value).strip()
    if s == "":
        return True
    return s.lower() in ("nan", "none", "null", "na")


def _norm(value) -> str:
    """把空值标准化为 ''，否则返回去除首尾空格后的字符串。"""
    if _is_blank(value):
        return ""
    return str(value).strip()


def _build_headers() -> dict:
    dev_id = os.getenv("EBAY_DEV_ID")
    app_id = os.getenv("EBAY_APP_ID")
    cert_id = os.getenv("EBAY_CERT_ID")
    if not all([dev_id, app_id, cert_id]):
        raise RuntimeError("Missing eBay DEV/APP/CERT IDs in environment")

    return {
        "X-EBAY-API-SITEID": "0",
        "X-EBAY-API-CALL-NAME": "ReviseInventoryStatus",
        "X-EBAY-API-COMPATIBILITY-LEVEL": "1199",
        "X-EBAY-API-DEV-NAME": dev_id,
        "X-EBAY-API-APP-NAME": app_id,
        "X-EBAY-API-CERT-NAME": cert_id,
        "Content-Type": "text/xml",
    }


def _build_body(auth_token: str, inv_xml: str, quantity: int) -> str:
    return f"""<?xml version="1.0" encoding="utf-8"?>
<ReviseInventoryStatusRequest xmlns="urn:ebay:apis:eBLBaseComponents">
  <RequesterCredentials>
    <eBayAuthToken>{escape(auth_token)}</eBayAuthToken>
  </RequesterCredentials>
  <InventoryStatus>
    {inv_xml}
    <Quantity>{quantity}</Quantity>
  </InventoryStatus>
</ReviseInventoryStatusRequest>""".strip()


def _post(body: str, headers: dict) -> dict:
    """发送请求并返回基础结构。"""
    try:
        resp = requests.post(
            EBAY_ENDPOINT, data=body.encode("utf-8"), headers=headers, timeout=30
        )
        text = resp.text or ""
        ok = (resp.status_code == 200) and (
            "<Ack>Success</Ack>" in text or "<Ack>Warning</Ack>" in text
        )
        return {"ok": ok, "status": resp.status_code, "body": text}
    except Exception as e:
        return {"ok": False, "status": None, "error": str(e), "body": ""}


def _has_invalid_sku(body: str) -> bool:
    """检测 'Invalid SKU' 错误（错误码 21916255）。"""
    if not body:
        return False
    if "Invalid SKU" in body:
        return True
    if "21916255" in body:
        return True
    return False


def _has_token_expired(body: str) -> bool:
    """检测硬过期 token（错误码 932 / Auth token is hard expired）。"""
    if not body:
        return False
    return ("Auth token is hard expired" in body) or ("ErrorCode>932<" in body)


def revise_inventory_status(item_id: str = "", sku: str = "", quantity: int = 0) -> dict:
    """
    直接调用 Trading API ReviseInventoryStatus：
    - 若传 sku 则按 SKU 更新；否则按 item_id 更新。
    - 不做自动回退（自动回退请用 update_qty_with_fallback）。
    """
    auth_token = os.getenv("EBAY_AUTH_TOKEN")
    if _is_blank(auth_token):
        return {"ok": False, "error": "Missing EBAY_AUTH_TOKEN in environment"}

    headers = _build_headers()

    sku = _norm(sku)
    item_id = _norm(item_id)

    use_sku = (not _is_blank(sku))
    inv_xml = (
        f"<SKU>{escape(sku)}</SKU>"
        if use_sku
        else f"<ItemID>{escape(item_id)}</ItemID>"
    )

    body = _build_body(auth_token=auth_token, inv_xml=inv_xml, quantity=quantity)

    # Dry-run：只打印预期动作，不调用 eBay
    if os.getenv("DRY_RUN", "false").lower() == "true":
        return {
            "ok": True,
            "dry_run": True,
            "used": "sku" if use_sku else "item_id",
            "item_id": item_id,
            "sku": sku,
            "quantity": quantity,
        }

    res = _post(body, headers)
    # 附加一些有用信息
    res.update({"used": "sku" if use_sku else "item_id", "item_id": item_id, "sku": sku, "quantity": quantity})

    # 识别常见 token 过期
    if (not res.get("ok")) and _has_token_expired(res.get("body", "")):
        res.setdefault("error", "Auth token hard expired (code 932). Please refresh EBAY_AUTH_TOKEN.")
    return res


def update_qty_with_fallback(item_id: str, sku: str, quantity: int = 0) -> dict:
    """
    优先用 SKU 更新；若返回 Invalid SKU（21916255），自动回退到 ItemID。
    """
    item_id = _norm(item_id)
    sku = _norm(sku)

    # 优先 SKU
    if sku:
        first = revise_inventory_status(item_id=item_id, sku=sku, quantity=quantity)
        if (not first.get("ok")) and _has_invalid_sku(first.get("body", "")) and item_id:
            second = revise_inventory_status(item_id=item_id, sku="", quantity=quantity)
            return {
                "ok": second.get("ok"),
                "first": first,
                "second": second,
                "fallback": "item_id",
            }
        return {"ok": first.get("ok"), "first": first, "fallback": None}

    # 没有 SKU，直接用 ItemID
    only = revise_inventory_status(item_id=item_id, sku="", quantity=quantity)
    return {"ok": only.get("ok"), "first": only, "fallback": None}
