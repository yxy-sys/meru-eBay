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
    只有在状态可识别时才判断清 0 规则：
    - trigger = soldout  -> 仅当 status == OUT_OF_STOCK
    - trigger = lowstock -> 当 status ∈ {OUT_OF_STOCK, LOW_STOCK}
    - 其它/未知           -> 不清 0
    """
    # 关键信号：状态未知一律不动作、不通知，避免误报
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

        # 判状态
        status = "UNKNOWN" if code != 200 else mercari.detect(html)

        print(f"[MERCARI] {url} HTTP={code} status={status} trigger={trigger} sku={sku or '∅'}")

        # 状态未知：跳过（既不清 0 也不发通知），避免误报
        if status == "UNKNOWN":
            print(f"SKIP: {ident} status UNKNOWN, no action.\n")
            continue

        # 只有需要清 0 时才继续
        if not should_zero(trigger, status):
            # 同步成功但没清 0：不通知
            continue

        # ① 煤炉售罄（已被识别为 OUT_OF_STOCK / 或符合规则） -> 发送“售罄”提示
        #   注意：如果你不想提前发售罄提示，可以注释掉下一行。
        notify(f"⚠️ 检测到煤炉售罄：{ident}\n{url}")

        # ② 调用 eBay 清 0
        res = revise_inventory_status(item_id=item_id, sku=sku, quantity=0)
        print("eBay update:", res)

        # ③ 根据 eBay 结果发通知
        if res.get("ok"):
            notify(f"✅ eBay 库存已清零：{ident}")
        else:
            # 带一点错误信息（短截），便于排查
            status_code = res.get("status")
            body = res.get("body") or res.get("error") or ""
            snippet = str(body)[:500]
            notify(f"❌ eBay 清零失败：{ident}\nHTTP={status_code}\n{snippet}")

    if matched == 0:
        print("No Mercari rows matched. Check headers/domains.")


if __name__ == "__main__":
    run_once()

