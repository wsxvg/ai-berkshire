import json, subprocess
result = subprocess.run(['gh', 'run', 'list', '--limit', '3', '--json', 'databaseId,status,startedAt,workflowName,conclusion'], capture_output=True, text=True)
data = json.loads(result.stdout)
for r in data:
    print(f"ID={r['databaseId']:12d} Status={r['status']:12s} Conclusion={str(r['conclusion']):10s} WF={r['workflowName'][:30]}")
