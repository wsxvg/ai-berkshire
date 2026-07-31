"""Check GitHub Actions status."""
import json, subprocess

result = subprocess.run(
    ['gh', 'run', 'view', '30601136525', '--json', 'status,jobs'],
    capture_output=True, text=True, cwd='.'
)
data = json.loads(result.stdout)
print(f'Workflow status: {data.get("status")}')
print()
for j in data.get('jobs', []):
    status = j.get('status', '?')
    name = j.get('name', '?')
    conclusion = j.get('conclusion', '')
    print(f'  {name:30s} {status:12s} {conclusion}')
