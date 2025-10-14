# fetcher.py  —— 回退到稳定最小版本
import os
import asyncio
import random
import requests

UA_POOL = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36",
]

def fetch_requests(url: str, timeout: int = 25):
    headers = {
        "User-Agent": random.choice(UA_POOL),
        "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Connection": "close",
    }
    try:
        resp = requests.get(url, headers=headers, timeout=timeout)
        return resp.status_code, resp.text
    except Exception as e:
        return 0, f"requests error: {e}"

# 替换 fetcher.py 中的这个函数
async def fetch_playwright_async(url: str):
    try:
        from playwright.async_api import async_playwright
    except Exception as e:
        return 0, f"Playwright not installed: {e}"

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
            context = await browser.new_context(locale="ja-JP")
            page = await context.new_page()

            # 关键：不要等 networkidle；先等 domcontentloaded，超时30s
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            except Exception:
                # 即便超时，也继续尝试取内容
                pass

            # 尝试等待“売り切れ/売り切れました”标签出现（不出现也不报错）
            try:
                await page.wait_for_selector("text=売り切れ", timeout=1500)
            except Exception:
                try:
                    await page.wait_for_selector("text=売り切れました", timeout=1500)
                except Exception:
                    pass

            # 再给一点空闲时间；若依然有长连，最多等 3s 就放行
            try:
                await page.wait_for_load_state("networkidle", timeout=3000)
            except Exception:
                pass

            # 兜底再等 600ms，确保 DOM 稳定
            await page.wait_for_timeout(600)

            html = await page.content()
            await browser.close()
            return 200, html
    except Exception as e:
        return 0, f"playwright error: {e}"

def fetch(url: str):
    mode = os.getenv("FETCH_MODE", "REQUESTS").strip().upper()
    timeout = int(os.getenv("REQUESTS_TIMEOUT", "25"))

    if mode == "PLAYWRIGHT":
        code, html = asyncio.run(fetch_playwright_async(url))
        print(f"FETCH[PLAYWRIGHT] code={code}")
        if code != 200:                       # <<< 新增：把错误文本打出来
            try: print("[PLAYWRIGHT ERROR]", str(html)[:400])
            except: pass
        return code, html

    code, html = fetch_requests(url, timeout=timeout)
    print(f"FETCH[REQUESTS] code={code}")
    return code, html
