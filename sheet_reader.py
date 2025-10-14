
import os, io, requests, pandas as pd
import gspread
from google.oauth2.service_account import Credentials

def read_ledger():
    mode = os.getenv("SHEETS_MODE", "PUBLIC_CSV").upper()
    if mode == "PUBLIC_CSV":
        url = os.getenv("SHEET_CSV_URL", "").strip()
        if not url:
            raise RuntimeError("SHEET_CSV_URL is empty for PUBLIC_CSV mode")
        resp = requests.get(url, timeout=25)
        resp.raise_for_status()
        df = pd.read_csv(io.StringIO(resp.text))
        df.columns = [c.strip() for c in df.columns]
        return df
    elif mode == "SERVICE_API":
        json_path = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
        sheet_id = os.getenv("SHEET_ID", "").strip()
        sheet_range = os.getenv("SHEET_RANGE", "Sheet1!A:D").strip()
        if not (json_path and sheet_id):
            raise RuntimeError("SERVICE_API mode requires GOOGLE_SERVICE_ACCOUNT_JSON and SHEET_ID")
        scopes = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
        creds = Credentials.from_service_account_file(json_path, scopes=scopes)
        gc = gspread.authorize(creds)
        sh = gc.open_by_key(sheet_id)
        ws = sh.worksheet(sheet_range.split("!")[0])
        data = ws.get(sheet_range.split("!")[1] if "!" in sheet_range else None)
        header, rows = data[0], data[1:]
        return pd.DataFrame(rows, columns=[h.strip() for h in header])
    else:
        raise RuntimeError("Unknown SHEETS_MODE")
