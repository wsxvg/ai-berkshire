#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""轮询 R21 SMART_MOD 重跑 workflow (run 31313216507) 状态，直到全部 job 结束。"""
import json, subprocess, sys, time, base64, os, urllib.request

RUN_ID = "31313216507"
REPO = "wsxvg/ai-berkshire"

def get_token():
    # 从 git-credentials 提取
    cred_file = os.path.expanduser("~/.git-credentials")
    if os.path.exists(cred_file):
        for line in open(cred_file):
            if "github.com" in line:
                rest = line.split("://")[1]
                user = rest.split(":")[0]
                tok = rest.split(":")[1].split("@")[0]
                return user, tok
    return None, None

def api_get(path):
    user, tok = get_token()
    b64 = base64.b64encode(f"{user}:{tok}".encode()).decode()
    proxy = "http://127.0.0.1:7890"
    proxy_handler = urllib.request.ProxyHandler({"http": proxy, "https": proxy})
    opener = urllib.request.build_opener(proxy_handler)
    req = urllib.request.Request(
        f"https://api.github.com{path}",
        headers={"Authorization": f"Basic {b64}", "User-Agent": "catpaw", "Accept": "application/vnd.github+json"},
    )
    with opener.open(req, timeout=30) as resp:
        return json.loads(resp.read().decode())

def main():
    if len(sys.argv) > 1:
        run_id = sys.argv[1]
    else:
        run_id = RUN_ID
    print(f"轮询 run {run_id} ...", flush=True)
    while True:
        try:
            run = api_get(f"/repos/{REPO}/actions/runs/{run_id}")
            jobs = api_get(f"/repos/{REPO}/actions/runs/{run_id}/jobs")
            status = run["status"]
            conclusion = run.get("conclusion")
            counts = {"in_progress": 0, "completed": 0}
            for j in jobs["jobs"]:
                counts[j["status"]] = counts.get(j["status"], 0) + 1
            done = counts.get("completed", 0)
            total = len(jobs["jobs"])
            print(f"[{time.strftime('%H:%M:%S')}] run={status}/{conclusion} jobs: {done}/{total} done | "
                  + ", ".join(f"{k}={v}" for k, v in counts.items()), flush=True)
            if status in ("completed", "cancelled", "failure", "timed_out"):
                print("RUN FINISHED. Conclusion:", conclusion, flush=True)
                # 打印每个 job 详情
                for j in jobs["jobs"]:
                    print(f"  job [{j['name']}] {j['status']}/{j['conclusion']}", flush=True)
                return
        except Exception as e:
            print(f"[{time.strftime('%H:%M:%S')}] poll error: {e}", flush=True)
        time.sleep(120)

if __name__ == "__main__":
    main()