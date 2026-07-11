import { NextResponse } from 'next/server'
import { exec } from 'child_process'
import path from 'path'
import fs from 'fs'

const ROOT = path.resolve(process.cwd(), '..')

function runPy(file: string): Promise<string> {
  return new Promise((resolve, reject) => {
    exec(`python "${file}"`, {
      cwd: ROOT, timeout: 30000, encoding: 'buffer',
      env: { ...process.env, PYTHONIOENCODING: 'utf-8' }
    }, (err, stdout, stderr) => {
      if (err) reject(new Error(stderr?.toString('utf-8') || err.message))
      else resolve(stdout.toString('utf-8'))
    })
  })
}

export async function GET() {
  const tmp = path.join(ROOT, '_api_feed.py')
  try {
    fs.writeFileSync(tmp, `import json, sys; sys.path.insert(0, '.')
from tools.jd_finance_api import get_trading_records, _ensure_cookies, FOLLOWED_USERS

c = _ensure_cookies(offline=True) or {}
from pathlib import Path as P
cp = P('data/jd_auth/cookies.json')
if not c and cp.exists(): c = json.loads(cp.read_text('utf-8'))

results = []
for uid, name in list(FOLLOWED_USERS.items())[:8]:
    full = f'jimu_user_info-{uid}'
    try:
        r = get_trading_records(full, cookies=c, max_pages=1)
        for rec in r.get('records', []):
            results.append({
                'user': name,
                'fund': rec.get('fund_name',''),
                'action': rec.get('action',''),
                'amount': rec.get('amount',''),
                'detail': rec.get('detail','')[:10] if rec.get('detail') else '',
            })
    except: pass
print(json.dumps(results, ensure_ascii=False))`, 'utf-8')
    const stdout = await runPy(tmp)
    fs.unlinkSync(tmp)
    return NextResponse.json(JSON.parse(stdout.trim()).slice(0, 20))
  } catch (e: any) {
    try { fs.unlinkSync(tmp) } catch {}
    return NextResponse.json([])
  }
}
