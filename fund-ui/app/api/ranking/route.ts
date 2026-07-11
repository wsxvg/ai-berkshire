import { NextRequest, NextResponse } from 'next/server'
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

export async function GET(req: NextRequest) {
  const sort = req.nextUrl.searchParams.get('sort') || '1n' // 1n=近1年
  const type = req.nextUrl.searchParams.get('type') || 'all'

  const tmp = path.join(ROOT, '_api_ranking.py')
  try {
    fs.writeFileSync(tmp, `import json, sys; sys.path.insert(0, '.')
from tools.jd_finance_api import get_fund_ranking, _ensure_cookies
c = _ensure_cookies(offline=True) or {}
# 试京东排行API
r = get_fund_ranking(cookies=c, rank_sort_by='${sort}', time_cycle='401')
if not r or not r.get('rankings'):
    # fallback: 用缓存里的业绩排名数据自己排序
    import glob
    from pathlib import Path
    CACHE = Path('data/fund_cache')
    results = []
    for f in glob.glob(str(CACHE / 'fund_perf_*.json')):
        try:
            d = json.loads(open(f, encoding='utf-8').read())
            code = Path(f).stem.replace('fund_perf_', '', 1)
            name = ''
            perf = d.get('performance', [])
            y1 = 0
            for p in perf:
                if '近1年' in p.get('period', ''):
                    y1 = float(p.get('return', 0)) if p.get('return') else 0
            results.append({'code': code, 'name': name, 'y1': y1})
        except: pass
    results.sort(key=lambda x: -x['y1'])
    print(json.dumps([{'code': r['code'], 'name': r['name'], 'y1': round(r['y1'], 2)} for r in results[:20]], ensure_ascii=False))
else:
    items = r.get('rankings', [])[:20]
    print(json.dumps([{
        'code': i.get('code',''), 'name': i.get('name',''),
        'nav': i.get('nav',''), 'day': i.get('daily_return'),
        'week': i.get('week_return'), 'month': i.get('month_return'),
        'y1': i.get('year_return'), 'y3': i.get('three_year_return'),
        'sharpe': i.get('sharpe'), 'maxdd': i.get('max_drawdown'),
    } for i in items], ensure_ascii=False))`, 'utf-8')
    const stdout = await runPy(tmp)
    fs.unlinkSync(tmp)
    return NextResponse.json(JSON.parse(stdout.trim()))
  } catch (e: any) {
    try { fs.unlinkSync(tmp) } catch {}
    return NextResponse.json([])
  }
}
