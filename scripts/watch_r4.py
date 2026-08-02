import sys, os, time, urllib.request, urllib.error

url = "https://raw.githubusercontent.com/wsxvg/ai-berkshire/master/v9-results/strict_oos_r4_eval.json"
for i in range(1, 90):
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            data = r.read().decode()
            out_path = os.path.join(os.path.dirname(__file__), "..", "v9-results", "strict_oos_r4_eval.json")
            out_path = os.path.normpath(out_path)
            with open(out_path, "w") as f:
                f.write(data)
            print(f"[FOUND] R4 at wave {i}! ({i*2}min)", flush=True)
            print(data)
            break
    except Exception as e:
        if i % 3 == 0:
            print(f"[WAIT {i}] no R4 yet ({i*2}min elapsed) - {str(e)[:80]}", flush=True)
        time.sleep(120)
else:
    print("[DONE] Timed out", flush=True)
