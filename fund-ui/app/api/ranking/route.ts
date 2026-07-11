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

export async function GET(req: NextRequest) {
  const limit = parseInt(req.nextUrl.searchParams.get('limit') || '200')
  const tmp = path.join(ROOT, '_api_ranking.py')
  try {
    fs.writeFileSync(tmp, `import json, sys
from pathlib import Path
from datetime import datetime
sys.path.insert(0, '.')

nm = json.loads(Path('data/fund_name_map.json').read_text('utf-8'))
code_to_name = {}
for n, c in nm.items():
    if c not in code_to_name: code_to_name[c] = n

# 基金类型映射
fund_types = {}
try:
    import glob as _g
    for f in _g.glob('data/fund_cache/fund_profile_*.json'):
        code = Path(f).stem.replace('fund_profile_', '', 1)
        try:
            d = json.loads(Path(f).read_text('utf-8'))
            fund_types[code] = d.get('fund_type', '') or d.get('fund_type_name', '') or ''
        except: pass
except: pass

fc = json.loads(Path('data/fund_charts.json').read_text('utf-8'))
TODAY = datetime.now().strftime('%Y-%m-%d')

results = []
for code, pts in fc.items():
    valid = [p for p in pts if p['xAxis'] <= TODAY]
    if len(valid) < 63: continue
    navs = [(100 + float(p['yAxis'])) / 100 for p in valid]
    cur = navs[-1]

    r1m = r3m = r6m = r1y = r3y = rSince = None
    if len(navs) > 21: r1m = (cur - navs[-21]) / navs[-21] * 100
    if len(navs) > 63: r3m = (cur - navs[-63]) / navs[-63] * 100
    if len(navs) > 126: r6m = (cur - navs[-126]) / navs[-126] * 100
    if len(navs) > 252: r1y = (cur - navs[-252]) / navs[-252] * 100
    if len(navs) > 756: r3y = (cur - navs[-756]) / navs[-756] * 100
    # 成立以来(从首日开始)
    rSince = (cur - navs[0]) / navs[0] * 100

    # 夏普(近1年, 无风险利率 2%)
    sharpe = 0
    if len(navs) >= 252:
        import statistics
        daily = [navs[i+1] / navs[i] - 1 for i in range(len(navs)-252, len(navs)-1)]
        if daily and len(daily) > 1:
            avg = statistics.mean(daily) - 0.02/252
            std = statistics.stdev(daily)
            sharpe = (avg / std) * (252 ** 0.5) if std > 0 else 0

    # 最大回撤(成立以来)
    maxdd = 0
    peak = navs[0]
    for v in navs:
        if v > peak: peak = v
        dd = (peak - v) / peak * 100
        if dd > maxdd: maxdd = dd

    # 年化波动率(近1年)
    vol = 0
    if len(navs) >= 252:
        import statistics
        daily = [navs[i+1] / navs[i] - 1 for i in range(len(navs)-252, len(navs)-1)]
        if daily and len(daily) > 1:
            vol = statistics.stdev(daily) * (252 ** 0.5) * 100

    results.append({
        'code': code,
        'name': code_to_name.get(code, '') or code,
        'type': fund_types.get(code, ''),
        'r1m': round(r1m, 2) if r1m is not None else None,
        'r3m': round(r3m, 2) if r3m is not None else None,
        'r6m': round(r6m, 2) if r6m is not None else None,
        'r1y': round(r1y, 2) if r1y is not None else None,
        'r3y': round(r3y, 2) if r3y is not None else None,
        'rSince': round(rSince, 2),
        'sharpe': round(sharpe, 2),
        'maxdd': round(maxdd, 2),
        'vol': round(vol, 2),
    })

print(json.dumps(results, ensure_ascii=False))`, 'utf-8')
    const stdout = await runPy(tmp)
    fs.unlinkSync(tmp)
    const all = JSON.parse(stdout.trim())
    return NextResponse.json(all.slice(0, limit))
  } catch (e: any) {
    try { fs.unlinkSync(tmp) } catch {}
    return NextResponse.json({ error: e.message }, { status: 500 })
  }
}
