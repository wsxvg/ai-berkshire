import { NextRequest, NextResponse } from 'next/server'
import { exec } from 'child_process'
import path from 'path'
import fs from 'fs'

const ROOT = path.resolve(process.cwd(), '..')

function runPy(file: string): Promise<string> {
  return new Promise((resolve, reject) => {
    exec(`python "${file}"`, {
      cwd: ROOT, timeout: 40000, encoding: 'buffer',
      env: { ...process.env, PYTHONIOENCODING: 'utf-8' }
    }, (err, stdout, stderr) => {
      if (err) reject(new Error(stderr?.toString('utf-8') || err.message))
      else resolve(stdout.toString('utf-8'))
    })
  })
}

export async function GET(req: NextRequest) {
  const tmp = path.join(ROOT, '_api_ranking.py')
  try {
    fs.writeFileSync(tmp, `import json, sys, glob; sys.path.insert(0, '.')
from pathlib import Path
from datetime import datetime

# 加载名称映射
nm = json.loads(Path('data/fund_name_map.json').read_text('utf-8'))
code_to_name = {}  # code -> name
name_to_code = nm  # name -> code
for n, c in nm.items():
    if c not in code_to_name: code_to_name[c] = n

# 从 fund_charts 拿所有基金，算近1年收益率
fc = json.loads(Path('data/fund_charts.json').read_text('utf-8'))
TODAY = datetime.now().strftime('%Y-%m-%d')

results = []
for code, pts in fc.items():
    valid = [p for p in pts if p['xAxis'] <= TODAY]
    if len(valid) < 126: continue  # 至少半年
    navs = [(100 + float(p['yAxis'])) / 100 for p in valid]
    cur = navs[-1]
    # 近1月(21), 近3月(63), 近1年(252)
    r1m = None; r3m = None; r6m = None; r1y = None
    if len(navs) > 21: r1m = (cur - navs[-21]) / navs[-21] * 100
    if len(navs) > 63: r3m = (cur - navs[-63]) / navs[-63] * 100
    if len(navs) > 126: r6m = (cur - navs[-126]) / navs[-126] * 100
    if len(navs) > 252: r1y = (cur - navs[-252]) / navs[-252] * 100

    # 夏普(近1年)
    sharpe = 0
    if len(navs) >= 252:
        daily = [navs[i+1] / navs[i] - 1 for i in range(len(navs)-252, len(navs)-1)]
        if daily:
            import statistics
            avg = statistics.mean(daily)
            std = statistics.stdev(daily) if len(daily) > 1 else 0.0001
            sharpe = (avg / std) * (252 ** 0.5) if std > 0 else 0

    # 最大回撤(近1年)
    maxdd = 0
    peak = navs[-min(252,len(navs))]
    for v in navs[-min(252,len(navs)):]:
        if v > peak: peak = v
        dd = (peak - v) / peak * 100
        if dd > maxdd: maxdd = dd

    name = code_to_name.get(code, '')
    results.append({
        'code': code, 'name': name,
        'r1m': round(r1m, 1) if r1m else None,
        'r3m': round(r3m, 1) if r3m else None,
        'r6m': round(r6m, 1) if r6m else None,
        'r1y': round(r1y, 1) if r1y else None,
        'sharpe': round(sharpe, 2),
        'maxdd': round(maxdd, 1),
    })

results.sort(key=lambda x: -(x['r1y'] or 0))
print(json.dumps(results[:50], ensure_ascii=False))`, 'utf-8')
    const stdout = await runPy(tmp)
    fs.unlinkSync(tmp)
    return NextResponse.json(JSON.parse(stdout.trim()))
  } catch (e: any) {
    try { fs.unlinkSync(tmp) } catch {}
    return NextResponse.json([])
  }
}
