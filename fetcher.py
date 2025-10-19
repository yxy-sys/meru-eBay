# fetcher.py（Playwright 版本）
from playwright.sync_api import sync_playwright

def fetch(url: str):
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            ctx = browser.new_context(locale="ja-JP")
            page = ctx.new_page()
            resp = page.goto(url, wait_until="domcontentloaded", timeout=45000)

            # 等待任一交互元素出现（按钮/链接）。有些页面按钮是 hydration 后才插入。
            try:
                page.wait_for_selector("button, a", timeout=6000)
            except:
                pass
            # 再给前端 1.2s 让 aria/文本就位（经验值）
            page.wait_for_timeout(1200)

            html = page.content()
            # 额外抓一份“整页纯文本”，作为兜底通道
            try:
                text_dump = page.inner_text("body", timeout=3000)
            except:
                text_dump = ""

            browser.close()

            # 把纯文本塞进注释，传给 detector 作为兜底搜索区域
            if text_dump:
                html = (
                    html
                    + "\n<!--TEXT_DUMP_START-->\n"
                    + text_dump
                    + "\n<!--TEXT_DUMP_END-->\n"
                )

            code = resp.status if resp else 0
            return code, html
    except Exception as e:
        return 0, f"__FETCH_ERROR__::{e}"

