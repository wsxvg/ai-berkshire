import { NextRequest, NextResponse } from 'next/server'
import { exec } from 'child_process'
import path from 'path'
import fs from 'fs'

const ROOT = path.resolve(process.cwd(), '..')

function runPy(file: string, timeoutMs = 60000): Promise<string> {
  return new Promise((resolve, reject) => {
    exec(`python "${file}"`, {
      cwd: ROOT, timeout: timeoutMs, encoding: 'buffer',
      env: { ...process.env, PYTHONIOENCODING: 'utf-8' }
    }, (err, stdout, stderr) => {
      if (err) reject(new Error(stderr?.toString('utf-8') || err.message))
      else resolve(stdout.toString('utf-8'))
    })
  })
}

// 进程内缓存
let cache: { ts: number; data: any } | null = null
const CACHE_TTL = 30 * 60 * 1000  // 30min

export async function GET(req: NextRequest) {
  const forceRefresh = req.nextUrl.searchParams.get('refresh') === 'true'

  // 缓存命中 (非强制刷新)
  if (!forceRefresh && cache && Date.now() - cache.ts < CACHE_TTL) {
    return NextResponse.json(cache.data, { headers: { 'X-Cache': 'memory' } })
  }

  const tmp = path.join(ROOT, '_api_feat_rankings.py')
  try {
    fs.writeFileSync(tmp, `import json
from pathlib import Path
import sys
sys.path.insert(0, '.')
from tools.jd_finance_api import get_featured_rankings

fund_types = {}
import glob
for f in glob.glob('data/fund_cache/fund_profile_*.json'):
    code = Path(f).stem.replace('fund_profile_', '', 1)
    try:
        d = json.loads(Path(f).read_text('utf-8'))
        fund_types[code] = d.get('fund_type', '') or d.get('fund_type_name', '') or ''
    except: pass

nm = json.loads(Path('data/fund_name_map.json').read_text('utf-8'))
code_to_name = {}
for n, c in nm.items():
    if c not in code_to_name: code_to_name[c] = n

data = get_featured_rankings(use_cache=True, max_items=20)
for code, b in data.get('boards', {}).items():
    for f in b.get('top20', []):
        fc = f.get('code')
        if fc and not f.get('name'):
            f['name'] = code_to_name.get(fc, '')
        f['type'] = fund_types.get(fc, '')

print(json.dumps(data, ensure_ascii=False))
`, 'utf-8')
    const stdout = await runPy(tmp)
    fs.unlinkSync(tmp)
    const data = JSON.parse(stdout.trim())
    cache = { ts: Date.now(), data }
    return NextResponse.json(data, { headers: { 'X-Cache': 'fresh' } })
  } catch (e: any) {
    try { fs.unlinkSync(tmp) } catch {}
    // 缓存失败, 返上一次缓存
    if (cache) {
      return NextResponse.json({
        ...cache.data,
        _warning: e.message,
      }, { headers: { 'X-Cache': 'stale' } })
    }
    return NextResponse.json({
      error: e.message,
      hint: '检查 jd_finance_api.get_featured_rankings 是否正常, 跑一次 tools/build_ranking_cache.py 预热',
    }, { status: 500 })
  }
}
