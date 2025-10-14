import os
from dotenv import load_dotenv
from sheet_reader import read_ledger
from fetcher import fetch
from detectors import mercari
from ebay_updater import revise_inventory_status
from notify import notify

load_dotenv()


def norm_trigger(v):
    s = str(v or "").strip().lower()
    return "soldout" if s in ("", "nan", "none") else s


def should_zero(trigger: str, status: str) -> bool:
    """
    触发规则：
    - soldout: 只有 OUT_OF_STOCK 才清 0
    - lowstock: OUT_OF_STOCK 或 LOW_STOCK 都清 0
    """
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
        # 读取一行
        url = str(row.get("source_url", "") or "").strip()
        url_l = url.lower()
        if not url_l or ("mercari.com" not in url_l and "jp.mercari.com" not in url_l):
            continue

        matched += 1
        item_id = str(row.get("ebay_item_id", "") or "").strip()
        sku = str(row.get("sku", "") or "").strip()
        trig = norm_trigger(row.get("trigger", ""))

        # 抓取煤炉页面
        code, html = fetch(url)
        status = "UNKNOWN" if code != 200 else mercari.detect(html)

        # 基础观测日志
        print(f"[MERCARI] {url} HTTP={code} status={status} trigger={trig} sku={sku}")

        # 是否需要清 0
        if should_zero(trig, status):
            # 售罄信号（一定发送）
            ident = sku if sku else item_id
            print(f"[MERCARI_SOLDOUT] url={url} sku={sku} item_id={item_id} status={status}")
            notify(f"🟡 检测到煤炉售罄：{ident}（{status}）")

            # 调用 eBay 清 0
            res = revise_inventory_status(item_id=item_id, sku=sku, quantity=0)
            # 打印原始返回（便于溯源）
            print("eBay update:", res)

            ok = bool(res.get("ok"))
            dry = bool(res.get("dry_run", False))

            if ok:
                # 成功（无论真实或 dry-run 都打标；通知正文区分）
                print(f"[EBAY_ZERO_OK] item_id={item_id} sku={sku} quantity=0 dry_run={dry}")
                if dry:
                    notify(f"✅（演练）eBay 已准备清零：{ident}（Qty=0）")
                else:
                    notify(f"✅ eBay 清零成功：{ident}（Qty=0）")
            else:
                # 失败
                print(f"[EBAY_ZERO_FAIL] item_id={item_id} sku={sku} reason={res}")
                # 尽量给出更友好的失败原因
                reason = res.get("error") or res.get("status") or "unknown"
                notify(f"❌ eBay 清零失败：{ident}，原因：{reason}")

        # 没触发 should_zero：不发通知，不打标——满足“不清0时不发”的要求

    if matched == 0:
        print("No Mercari rows matched. Check headers/domains.")


if __name__ == "__main__":
    run_once()

