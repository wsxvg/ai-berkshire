import { NextRequest, NextResponse } from 'next/server'
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

// 进程内缓存
let cache: { data: any; time: number } | null = null
const CACHE_TTL = 5 * 60 * 1000

/**
 * 大佬交易动态 feed
 * GET /api/feed
 *   ?limit=N          单用户最大记录数 (默认 10, 最大 50)
 *   ?users=N          抓取多少个用户 (默认 12, 最大 50)
 *   ?action=buy|sell  仅返回指定方向
 *   ?page=N           分页 (页码从 1 开始, 每页 pageSize=20)
 *   ?pageSize=N       每页大小 (默认 20, 最大 100)
 */
export async function GET(req: NextRequest) {
  const limit = Math.max(1, Math.min(parseInt(req.nextUrl.searchParams.get('limit') || '10', 10) || 10, 50))
  const users = Math.max(1, Math.min(parseInt(req.nextUrl.searchParams.get('users') || '12', 10) || 12, 50))
  const action = req.nextUrl.searchParams.get('action') || ''  // buy / sell / ''
  const page = Math.max(1, parseInt(req.nextUrl.searchParams.get('page') || '1', 10) || 1)
  const pageSize = Math.max(1, Math.min(parseInt(req.nextUrl.searchParams.get('pageSize') || '20', 10) || 20, 100))

  // 5min 内复用相同 (limit, users) 的全量结果
  const cacheKey = `${limit}|${users}`
  if (cache && cache.data._key === cacheKey && Date.now() - cache.time < CACHE_TTL) {
    return applyFilter(cache.data.items, { action, page, pageSize })
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
for uid, name in list(FOLLOWED_USERS.items())[:${users}]:
    full = f'jimu_user_info-{uid}'
    try:
        r = get_trading_records(full, cookies=c, max_pages=2, size=${limit})
        for rec in r.get('records', []):
            fid = rec.get('_fund_id', '')
            code = fid_to_code.get(fid, '')
            action_str = rec.get('action', '')
            is_buy = '买入' in action_str
            amount = rec.get('amount', '')
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
            results.append({
                'user': name, 'uid': uid,
                'fund': rec.get('fund_name',''), 'code': code,
                'action': action_str, 'amount': amount, 'amt_num': amt_num,
                'time': time_str, 'isBuy': is_buy,
            })
    except: pass

results.sort(key=lambda x: x.get('time',''), reverse=True)
print(json.dumps(results, ensure_ascii=False))`, 'utf-8')
    const stdout = await runPy(tmp)
    fs.unlinkSync(tmp)
    const items = JSON.parse(stdout.trim())
    cache = { data: { _key: cacheKey, items }, time: Date.now() }
    return applyFilter(items, { action, page, pageSize })
  } catch (e: any) {
    try { fs.unlinkSync(tmp) } catch {}
    // 缓存失败, 返上一次缓存 (如有过期)
    if (cache) {
      return applyFilter(cache.data.items, { action, page, pageSize, warning: e.message })
    }
    return NextResponse.json({
      error: e.message || 'fetch feed failed',
      hint: '检查 data/jd_auth/cookies.json 或运行 scripts/auto-pipeline.py',
    }, { status: 500 })
  }
}

function applyFilter(items: any[], opts: { action: string; page: number; pageSize: number; warning?: string }) {
  let filtered = items
  if (opts.action === 'buy') filtered = filtered.filter(x => x.isBuy)
  else if (opts.action === 'sell') filtered = filtered.filter(x => !x.isBuy)

  const total = filtered.length
  const start = (opts.page - 1) * opts.pageSize
  const paged = filtered.slice(start, start + opts.pageSize)

  const body: any = {
    items: paged,
    pagination: {
      page: opts.page,
      page_size: opts.pageSize,
      total,
      total_pages: Math.ceil(total / opts.pageSize),
    },
    filters: { action: opts.action || 'all' },
  }
  if (opts.warning) body.warning = opts.warning

  return NextResponse.json(body, {
    headers: opts.warning ? { 'X-Cache': 'stale', 'X-Warning': opts.warning } : { 'X-Cache': 'fresh' }
  })
}
