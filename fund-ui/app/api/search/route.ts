import { NextRequest, NextResponse } from 'next/server'
import { exec } from 'child_process'
import path from 'path'
import fs from 'fs'

const ROOT = path.resolve(process.cwd(), '..')
const NAME_MAP = path.join(ROOT, 'data', 'fund_name_map.json')

function runPy(file: string): Promise<string> {
  return new Promise((resolve, reject) => {
    exec(`python "${file}"`, {
      cwd: ROOT, timeout: 15000, encoding: 'buffer',
      env: { ...process.env, PYTHONIOENCODING: 'utf-8' }
    }, (err, stdout, stderr) => {
      if (err) reject(new Error(stderr?.toString('utf-8') || err.message))
      else resolve(stdout.toString('utf-8'))
    })
  })
}

// 进程内缓存: q -> 结果 (5min)
const memCache = new Map<string, { ts: number; data: any[] }>()
const CACHE_TTL = 5 * 60 * 1000

function searchLocal(q: string): any[] {
  if (!fs.existsSync(NAME_MAP)) return []
  try {
    const nm: Record<string, string> = JSON.parse(fs.readFileSync(NAME_MAP, 'utf-8'))
    const ql = q.toLowerCase()
    const out: any[] = []
    for (const [name, code] of Object.entries(nm)) {
      if (name.toLowerCase().includes(ql) || code.includes(ql)) {
        out.push({ code, name, source: 'local' })
        if (out.length >= 10) break
      }
    }
    return out
  } catch { return [] }
}

/**
 * 基金搜索联想
 * GET /api/search?q=XXX
 *   ?localOnly=true  (跳过 JD API, 用本地 name_map)
 */
export async function GET(req: NextRequest) {
  const q = (req.nextUrl.searchParams.get('q') || '').trim()
  const localOnly = req.nextUrl.searchParams.get('localOnly') === 'true'

  if (!q) return NextResponse.json({ error: 'missing q', hint: '?q=005660' }, { status: 400 })
  if (q.length < 2) return NextResponse.json({ error: 'q too short (min 2 chars)' }, { status: 400 })
  if (q.length > 50) return NextResponse.json({ error: 'q too long (max 50 chars)' }, { status: 400 })

  // 缓存命中
  const cacheKey = `${localOnly ? 'L' : 'F'}|${q}`
  const mem = memCache.get(cacheKey)
  if (mem && Date.now() - mem.ts < CACHE_TTL) {
    return NextResponse.json({ items: mem.data, source: 'cache' })
  }

  if (localOnly) {
    const local = searchLocal(q)
    memCache.set(cacheKey, { ts: Date.now(), data: local })
    return NextResponse.json({ items: local, source: 'local', q })
  }

  // 远程搜索
  const tmp = path.join(ROOT, '_api_search.py')
  try {
    fs.writeFileSync(tmp, `import json, sys; sys.path.insert(0, '.')
from tools.jd_finance_api import _api_form, _ensure_cookies
c = _ensure_cookies(offline=True) or {}
import urllib.parse
data = _api_form('gw/generic/base/h5/m/getSearchResultCompletionWord',
    {'keyword': '${q.replace(/'/g, "\\'")}'}, cookies=c)
rd = data.get('resultData', {}).get('datas', {})
items = rd.get('fundItemList', []) or rd.get('wordList', [])
results = []
for item in items[:10]:
    results.append({
        'code': item.get('code', item.get('fundCode', '')),
        'name': item.get('name', item.get('fundName', item.get('word', ''))),
        'type': item.get('fundType', ''),
    })
# 合并本地 (本地有的优先)
local = json.loads(open('data/fund_name_map.json', 'r', encoding='utf-8').read())
local_codes = {c: n for n, c in local.items() if c}
local_names_lower = {n.lower(): c for n, c in local.items()}
for r in results:
    if not r.get('name') and r['code'] in local_codes:
        r['name'] = local_codes[r['code']]
print(json.dumps(results, ensure_ascii=False))`, 'utf-8')
    const stdout = await runPy(tmp)
    fs.unlinkSync(tmp)
    const items = JSON.parse(stdout.trim())
    memCache.set(cacheKey, { ts: Date.now(), data: items })
    return NextResponse.json({ items, source: 'remote', q })
  } catch (e: any) {
    try { fs.unlinkSync(tmp) } catch {}
    // 远程失败, 退化到本地
    const local = searchLocal(q)
    if (local.length > 0) {
      return NextResponse.json({
        items: local,
        source: 'local_fallback',
        q,
        warning: 'remote search failed, used local: ' + e.message,
      })
    }
    return NextResponse.json({
      error: 'search failed: ' + e.message,
      hint: 'check data/jd_auth/cookies.json or retry with ?localOnly=true',
      items: [],
    }, { status: 500 })
  }
}
