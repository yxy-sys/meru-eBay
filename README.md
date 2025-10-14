
# Mercari → eBay Qty=0 (Google Sheets) — Playwright Rendering Ready

**What’s new**
- `FETCH_MODE`:
  - `REQUESTS` (default): fast HTML fetch via requests
  - `PLAYWRIGHT`: render page in headless Chromium to capture dynamic SOLD badges
  - `AUTO`: try `REQUESTS` first; if status is UNKNOWN, retry with Playwright once

**Install**
```bash
pip install -r requirements.txt
# If you will use Playwright:
pip install playwright
playwright install chromium
```

**.env**
```ini
# --- eBay Trading API ---
EBAY_DEV_ID=YOUR_DEV_ID
EBAY_APP_ID=YOUR_APP_ID
EBAY_CERT_ID=YOUR_CERT_ID
EBAY_AUTH_TOKEN=YOUR_LONG_AUTH_TOKEN

# --- Google Sheets (pick one mode) ---
SHEETS_MODE=PUBLIC_CSV
SHEET_CSV_URL=PASTE_YOUR_PUBLISHED_CSV_URL

# SHEETS_MODE=SERVICE_API
# GOOGLE_SERVICE_ACCOUNT_JSON=service_account.json
# SHEET_ID=YOUR_SHEET_ID
# SHEET_RANGE=Sheet1!A:D

# Fetching
FETCH_MODE=AUTO          # REQUESTS | PLAYWRIGHT | AUTO
REQUESTS_TIMEOUT=25

# Dry run (no real eBay call)
DRY_RUN=true

# Optional Telegram
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
```

**Run**
```bash
python main_gsheets.py           # one-shot run
python main_loop.py              # loop (default 10 minutes)
```

**Notes**
- Only Mercari is handled in this package.
- For AUTO mode, Playwright is used only if initial detection is UNKNOWN.
