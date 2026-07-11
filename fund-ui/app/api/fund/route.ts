import { NextResponse } from 'next/server'
import { spawn } from 'child_process'
import path from 'path'

const PY = 'py'
const ROOT = path.resolve(process.cwd(), '..')
const ROOT_PY = ROOT.replace(/\\/g, '\\\\')

function runPython(script: string): Promise<string> {
  return new Promise((resolve, reject) => {
    const proc = spawn(PY, ['-W', 'ignore', '-c', script], { timeout: 30000 })
    let stdout = ''
    let stderr = ''
    proc.stdout.on('data', (d) => { stdout += d })
    proc.stderr.on('data', (d) => { stderr += d })
    proc.on('close', (code) => {
      if (code === 0) resolve(stdout)
      else reject(new Error(stderr || `exit ${code}`))
    })
    proc.on('error', reject)
  })
}

export async function GET() {
  try {
    const script = `import json, sys; sys.path.insert(0, r'${ROOT_PY}')
from tools.jd_finance_api import get_watchlist, _ensure_cookies
c = _ensure_cookies(offline=True)
if not c:
    import pathlib
    cp = pathlib.Path(r'${ROOT_PY}') / 'data' / 'jd_auth' / 'cookies.json'
    c = json.loads(cp.read_text('utf-8')) if cp.exists() else {}
wl = get_watchlist(cookies=c)
funds = wl.get('funds', [])
import json as _json
print(_json.dumps([{
    'code': f.get('fund_code',''), 'name': f.get('fund_name',''),
    'nav': f.get('latest_nav',''), 'dayReturn': f.get('day_return'),
    'weekReturn': f.get('week_return'), 'monthReturn': f.get('month_return'),
    'yearReturn': f.get('year_return'), 'totalPnl': f.get('total_pnl_pct'),
    'fundType': f.get('fund_type','')
} for f in funds], ensure_ascii=False))`
    const stdout = await runPython(script)
    return NextResponse.json(JSON.parse(stdout))
  } catch (e: any) {
    return NextResponse.json({ error: e.message }, { status: 500 })
  }
}
