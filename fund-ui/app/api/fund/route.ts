import { NextResponse } from 'next/server'
import { exec } from 'child_process'
import path from 'path'
import fs from 'fs'

const ROOT = path.resolve(process.cwd(), '..')

function runPy(file: string): Promise<string> {
  return new Promise((resolve, reject) => {
    exec(`python "${file}"`, { cwd: ROOT, timeout: 30000 }, (err, stdout, stderr) => {
      if (err) reject(new Error(stderr || err.message))
      else resolve(stdout)
    })
  })
}

export async function GET() {
  const tmp = path.join(ROOT, '_api_fund.py')
  try {
    fs.writeFileSync(tmp, `import json, sys
sys.path.insert(0, '.')
from tools.jd_finance_api import get_watchlist, _ensure_cookies
c = _ensure_cookies(offline=True)
if not c:
    from pathlib import Path as P
    cp = P('data') / 'jd_auth' / 'cookies.json'
    c = json.loads(cp.read_text('utf-8')) if cp.exists() else {}
wl = get_watchlist(cookies=c)
funds = wl.get('funds', [])
print(json.dumps([{
    'code': f.get('fund_code',''), 'name': f.get('fund_name',''),
    'nav': f.get('latest_nav',''), 'dayReturn': f.get('day_return'),
    'weekReturn': f.get('week_return'), 'monthReturn': f.get('month_return'),
    'yearReturn': f.get('year_return'), 'totalPnl': f.get('total_pnl_pct'),
    'fundType': f.get('fund_type','')
} for f in funds], ensure_ascii=False))`, 'utf-8')
    const stdout = await runPy(tmp)
    fs.unlinkSync(tmp)
    return NextResponse.json(JSON.parse(stdout.trim()))
  } catch (e: any) {
    try { fs.unlinkSync(tmp) } catch {}
    return NextResponse.json({ error: e.message }, { status: 500 })
  }
}
