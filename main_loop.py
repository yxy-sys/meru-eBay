
import time, os
from main_gsheets import run_once

if __name__ == "__main__":
    interval = int(os.getenv("LOOP_INTERVAL", "600"))
    while True:
        run_once()
        time.sleep(interval)
