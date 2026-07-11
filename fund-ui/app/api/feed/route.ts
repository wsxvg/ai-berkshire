import { NextResponse } from 'next/server'
import { exec } from 'child_process'
import path from 'path'
import fs from 'fs'

const ROOT = path.resolve(process.cwd(), '..')

function runPy(file: string): Promise<string> {
  return new Promise((resolve, reject) => {
    exec(`python "${file}"`, {
      cwd: ROOT, timeout: 60000, encoding: 'buffer',
      env: { ...process.env, PYTHONIOENCODING: 'utf-8' }
    }, (err, stdout, stderr) => {
      if (err) reject(new Error(stderr?.toString('utf-8') || err.message))
      else resolve(stdout.toString('utf-8'))
    })
  })
}

// 缓存 5 分钟
let cache: { data: any; time: number } | null = null
const CACHE_TTL = 5 * 60 * 1000

export async function GET() {
  if (cache && Date.now() - cache.time < CACHE_TTL) {
    return NextResponse.json(cache.data, { headers: { 'X-Cache': 'HIT' } })
  }

  const tmp = path.join(ROOT, '_api_feed.py')
  try {
    fs.writeFileSync(tmp, `import json, sys
from pathlib import Path
sys.path.insert(0, '.')
from tools.jd_finance_api import get_trading_records, _ensure_cookies, FOLLOWED_USERS

c = _ensure_cookies(offline=True) or {}
cp = Path('data/jd_auth/cookies.json')
if not c and cp.exists():
    c = json.loads(cp.read_text('utf-8'))

# 反向映射：fund_id(数字) -> 6位code
import sqlite3
fid_to_code = {}
try:
    conn = sqlite3.connect('data/jd_auth/mapping.db')
    for row in conn.execute("SELECT jd_id, fund_code FROM fund_mapping"):
        fid_to_code[str(row[0])] = row[1]
    conn.close()
except: pass

results = []
for uid, name in list(FOLLOWED_USERS.items())[:12]:
    full = f'jimu_user_info-{uid}'
    try:
        r = get_trading_records(full, cookies=c, max_pages=2, size=10)
        for rec in r.get('records', []):
            fid = rec.get('_fund_id', '')
            code = fid_to_code.get(fid, '')
            action_str = rec.get('action', '')
            is_buy = '买入' in action_str
            amount = rec.get('amount', '')
            # 解析金额数字
            amt_num = 0
            try:
                s = str(amount).replace(',', '')
                if '万' in s:
                    amt_num = float(s.replace('万','').replace('元','')) * 10000
                elif '亿' in s:
                    amt_num = float(s.replace('亿','').replace('元','')) * 100000000
                else:
                    amt_num = float(s.replace('元','')) if s else 0
            except: pass

            time_str = rec.get('summary', '') or rec.get('detail', '')
            # time_str 格式: "MM-DD HH:MM" 或其他
            results.append({
                'user': name,
                'uid': uid,
                'fund': rec.get('fund_name',''),
                'code': code,
                'action': action_str,
                'amount': amount,
                'amt_num': amt_num,
                'time': time_str,
                'isBuy': is_buy,
            })
    except Exception as e:
        pass

# 按时间倒序
results.sort(key=lambda x: x.get('time',''), reverse=True)
print(json.dumps(results, ensure_ascii=False))`, 'utf-8')
    const stdout = await runPy(tmp)
    fs.unlinkSync(tmp)
    const data = JSON.parse(stdout.trim())
    cache = { data, time: Date.now() }
    return NextResponse.json(data)
  } catch (e: any) {
    try { fs.unlinkSync(tmp) } catch {}
    return NextResponse.json({ error: e.message }, { status: 500 })
  }
}
