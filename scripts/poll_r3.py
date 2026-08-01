#!/usr/bin/env python3
"""Poll GitHub for R3 results — checks if strict_oos_r3_eval.json appeared on origin/master."""
import subprocess, time, sys, os

POLL_INTERVAL = 30
MAX_POLLS = 120

def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r.stdout.strip()

local_head = run(["git", "rev-parse", "HEAD"])
print(f"[POLL] Local HEAD: {local_head}")
print(f"[POLL] Polling every {POLL_INTERVAL}s, max {MAX_POLLS} attempts...")

for i in range(MAX_POLLS):
    run(["git", "fetch", "origin", "master", "--quiet"])
    remote_head = run(["git", "rev-parse", "origin/master"])
    
    if remote_head != local_head:
        # Check if R3 results file is in the new commits
        new_commits = run(["git", "log", f"{local_head}..origin/master", "--oneline"])
        files_changed = run(["git", "diff", "--name-only", f"{local_head}..origin/master"])
        print(f"[POLL {i+1}] Remote HEAD changed! New commits:")
        print(new_commits)
        if "strict_oos_r3_eval.json" in files_changed:
            run(["git", "pull", "origin", "master", "--quiet"])
            print("=" * 60)
            print("R3 RESULTS FILE DETECTED!")
            print("=" * 60)
            if os.path.exists("v9-results/strict_oos_r3_eval.json"):
                with open("v9-results/strict_oos_r3_eval.json") as f:
                    print(f.read()[:4000])
            sys.exit(0)
    
    if (i + 1) % 5 == 0:
        print(f"[POLL {i+1}] Still waiting... ({(i+1)*POLL_INTERVAL}s elapsed)")
    time.sleep(POLL_INTERVAL)

print("[POLL] Timeout - did not detect R3 results file")
