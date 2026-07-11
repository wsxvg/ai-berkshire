import { NextResponse } from 'next/server'
import { execFile } from 'child_process'
import { promisify } from 'util'

const exec = promisify(execFile)
const PY = 'py'
const ROOT = process.cwd() + '/..'

export async function GET() {
  try {
    const script = `
import json, sys; sys.path.insert(0, '${ROOT}')
from tools.jd_finance_api import get_watchlist, _ensure_cookies
c = _ensure_cookies(offline=True)
if not c:
    import pathlib
    p = pathlib.Path('${ROOT}') / 'data' / 'jd_auth' / 'cookies.json'
    c = json.loads(p.read_text('utf-8')) if p.exists() else {}
wl = get_watchlist(cookies=c)
funds = wl.get('funds', [])
print(json.dumps([
    {'code': f['fund_code'], 'name': f['fund_name'], 
     'nav': f.get('latest_nav', ''), 'dayReturn': f.get('day_return'),
     'weekReturn': f.get('week_return'), 'monthReturn': f.get('month_return'),
     'yearReturn': f.get('year_return'), 'totalPnl': f.get('total_pnl_pct'),
     'fundType': f.get('fund_type', '')} for f in funds
], ensure_ascii=False))
`
    const { stdout } = await exec(PY, ['-c', script], { timeout: 30000 })
    return NextResponse.json(JSON.parse(stdout))
  } catch (e: any) {
    return NextResponse.json({ error: String(e.stderr || e.message) }, { status: 500 })
  }
}
