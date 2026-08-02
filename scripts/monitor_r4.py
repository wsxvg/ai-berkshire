#!/usr/bin/env python3
"""Monitor R4 OOS results — checks both git and raw.githubusercontent.com."""
import subprocess, time, os, urllib.request, urllib.error

os.chdir(r"C:\fund")

def check_raw_url():
    url = "https://raw.githubusercontent.com/wsxvg/ai-berkshire/master/v9-results/strict_oos_r4_eval.json"
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = resp.read().decode()
            return data
    except Exception as e:
        return None

def check_git():
    subprocess.run(["git", "fetch", "origin", "master", "--quiet"], capture_output=True)
    r = subprocess.run(["git", "log", "origin/master", "--oneline", "-1", "--",
                       "v9-results/strict_oos_r4_eval.json"], capture_output=True, text=True)
    if r.stdout.strip():
        subprocess.run(["git", "pull", "origin", "master", "--quiet"])
        if os.path.exists("v9-results/strict_oos_r4_eval.json"):
            with open("v9-results/strict_oos_r4_eval.json") as f:
                return f.read()
    return None

print("[MONITOR] Watching for R4 results (strict_oos_r4_eval.json)...")
for i in range(1, 91):  # 90 attempts × 2 min = 3 hours max
    # Try raw URL first (faster)
    data = check_raw_url()
    if data:
        print(f"\n[MONITOR] R4 FOUND via raw URL at attempt {i}!")
        # Save to file for analysis
        with open("v9-results/strict_oos_r4_eval.json", "w") as f:
            f.write(data)
        print(data)
        break
    # Try git
    data = check_git()
    if data:
        print(f"\n[MONITOR] R4 FOUND via git at attempt {i}!")
        print(data)
        break
    if i % 5 == 0:
        print(f"[MONITOR attempt {i}] no R4 yet ({i*2}min elapsed)")
    time.sleep(120)
else:
    print("[MONITOR] timed out after 3 hours")
