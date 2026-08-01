#!/usr/bin/env python3
"""Monitor R5 workflow via raw.githubusercontent.com polling."""
import time, urllib.request, json, sys

url = "https://raw.githubusercontent.com/wsxvg/ai-berkshire/master/v9-results/strict_oos_r5_eval.json"
max_wait = 3600
poll_interval = 90
start = time.time()

def log(msg):
    print(msg, flush=True)

log(f"[R5 MONITOR] Polling every {poll_interval}s...")

while time.time() - start < max_wait:
    time.sleep(poll_interval)
    elapsed = int(time.time() - start)
    try:
        req = urllib.request.Request(url, headers={"Cache-Control": "no-cache"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
            if "summary" in data:
                log(f"\n[R5 FOUND at {elapsed}s!]")
                log(json.dumps(data, indent=2)[:5000])
                with open("C:/fund/v9-results/strict_oos_r5_eval.json", "w") as f:
                    json.dump(data, f, indent=2)
                log("[R5 SAVED]")
                sys.exit(0)
    except Exception as e:
        err = str(e)[:80]
        log(f"[{elapsed}s] waiting... ({err})")

log("[R5 TIMEOUT]")
sys.exit(1)
