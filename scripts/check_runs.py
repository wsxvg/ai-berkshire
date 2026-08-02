import urllib.request, json, sys
req = urllib.request.Request("https://api.github.com/repos/wsxvg/ai-berkshire/actions/runs?per_page=3")
resp = urllib.request.urlopen(req, timeout=15)
data = json.loads(resp.read())
for r in data.get("workflow_runs", []):
    sha = r["head_sha"][:8]
    msg = r["head_commit"]["message"][:50]
    print(f'{r["id"]} {r["status"]} {r["conclusion"]} {sha} {msg}')
