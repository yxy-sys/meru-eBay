# notify.py
import os
import time
import json
import html
import requests
from typing import Optional

TG_API = "https://api.telegram.org/bot{token}/{method}"
MAX_LEN = 4096  # Telegram 文本消息上限

def _build_run_url() -> Optional[str]:
    """
    在 GitHub Actions 环境中自动拼 run 链接，否则返回 None
    """
    repo = os.getenv("GITHUB_REPOSITORY")
    run_id = os.getenv("GITHUB_RUN_ID")
    server = os.getenv("GITHUB_SERVER_URL", "https://github.com")
    if repo and run_id:
        return f"{server}/{repo}/actions/runs/{run_id}"
    return None

def _post_json(url: str, payload: dict, tries: int = 3, timeout: int = 15) -> bool:
    """
    简单重试：遇到网络错误/5xx/429 时退避重试
    """
    backoff = 2
    for i in range(tries):
        try:
            resp = requests.post(url, json=payload, timeout=timeout)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("ok"):
                    return True
                # 例如 {ok:false, description:"..."}
                # 打印一下方便排查，但不抛异常
                print(f"[TELEGRAM_WARN] api ok=false: {data}")
            else:
                print(f"[TELEGRAM_WARN] http {resp.status_code}: {resp.text[:200]}")
        except Exception as e:
            print(f"[TELEGRAM_WARN] request error: {e}")

        # 退避
        time.sleep(backoff)
        backoff *= 2
    return False

def _send_telegram(token: str, chat_id: str, text: str,
                   parse_mode: Optional[str] = None,
                   disable_preview: bool = True) -> bool:
    """
    将 text 按 4096 长度切片发送；任意一片失败返回 False
    """
    url = TG_API.format(token=token, method="sendMessage")

    # 追加 GitHub Actions 运行链接（如有）
    run_url = _build_run_url()
    if run_url:
        text = f"{text}\n\n🔗 {run_url}"

    parts = []
    s = str(text or "")
    while s:
        parts.append(s[:MAX_LEN])
        s = s[MAX_LEN:]

    ok_all = True
    for part in parts:
        payload = {
            "chat_id": chat_id,
            "text": part,
            "disable_web_page_preview": disable_preview,
        }
        if parse_mode:
            payload["parse_mode"] = parse_mode

        ok = _post_json(url, payload)
        ok_all = ok_all and ok
    return ok_all

def notify(text: str,
           parse_mode: Optional[str] = None,
           disable_preview: bool = True) -> bool:
    """
    外部调用的统一入口。
    - 如果没有 TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID，会“静默返回 True”，不打断主流程。
    - 返回值 True 表示（要么未配置、要么已成功发送）；False 表示尝试发送但失败。
    """
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()

    if not token or not chat_id:
        # 未配置，静默通过
        print("[TELEGRAM_DISABLED] no token or chat_id, skip sending")
        return True

    # 保险起见，防止意外传入非字符串类型
    txt = str(text or "")
    return _send_telegram(token, chat_id, txt, parse_mode=parse_mode, disable_preview=disable_preview)
