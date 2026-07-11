import { NextRequest, NextResponse } from 'next/server'
import { execFile } from 'child_process'
import { promisify } from 'util'
import fs from 'fs'
import path from 'path'

const exec = promisify(execFile)
const PY = 'py'
const ROOT = path.resolve(process.cwd(), '..')

export async function GET(req: NextRequest) {
  const codes = req.nextUrl.searchParams.get('codes') || ''
  if (!codes) return NextResponse.json({ error: 'missing codes' }, { status: 400 })

  try {
    const script = `
import json, sys; sys.path.insert(0, '${ROOT.replace(/\\/g, '\\\\')}')
from backtest.engine.backtest import score_fund_backtest
from backtest.engine.backtest import score_4433, detect_market_state
from tools.technical_indicators import compute_entry_timing_score
import glob

# 加载数据
fc = json.loads(open('${ROOT.replace(/\\/g, '\\\\')}/data/fund_charts.json', encoding='utf-8').read())
trades = json.loads(open('${ROOT.replace(/\\/g, '\\\\')}/backtest/data/trading_by_date_fixed.json', encoding='utf-8').read())

CACHE = pathlib.Path('${ROOT.replace(/\\/g, '\\\\')}/data/fund_cache')
def load(prefix):
    d = {}
    for f in glob.glob(str(CACHE / f'{prefix}_*.json')):
        c = pathlib.Path(f).stem.replace(f'{prefix}_', '', 1)
        try: d[c] = json.loads(open(f, encoding='utf-8').read())
        except: pass
    return d

fr = load('trade_rules'); fm = load('fund_manager'); fp = load('fund_profile')

from datetime import datetime
TODAY = datetime.now().strftime('%Y-%m-%d')
market = detect_market_state(TODAY, fc)

results = []
for code in '${codes}'.split(','):
    code = code.strip()
    if code not in fr: continue
    name = fp.get(code, {}).get('full_name', code)
    
    # RSI check
    pts = fc.get(code, [])
    blocked = False; block_reason = ''
    if len(pts) >= 60:
        timing = compute_entry_timing_score(pts, TODAY)
        if timing.get('should_warn'):
            blocked = True; block_reason = 'RSI超买'
    
    # 五维评分
    try:
        fs = score_fund_backtest(code, name, fc, None, fr.get(code), fm.get(code),
                                 TODAY, trades, fp.get(code))
        s = { 'total': round(fs.total, 1) }
        for d in ['quality','cost','manager','momentum','smart_money']:
            dim = getattr(fs, d, None)
            s[d] = round(dim.score, 1) if dim else 0
    except:
        s = { 'total': 3.0, 'quality': 3.0, 'cost': 3.0, 'manager': 3.0, 'momentum': 3.0, 'smart_money': 0 }
    
    # 4433
    p4433 = score_4433(code, TODAY, fc)[1]
    
    # RSI
    rsi = None
    if len(pts) >= 60:
        try:
            from tools.technical_indicators import compute_rsi
            navs = [(100+float(p['yAxis']))/100 for p in pts if p['xAxis']<=TODAY]
            rsi = round(compute_rsi(navs), 1)
        except: pass
    
    results.append({ 'code': code, 'name': name, **s, 'pass4433': p4433,
                     'rsi': rsi, 'blocked': blocked, 'blockReason': block_reason })

results.sort(key=lambda x: -x['total'])
print(json.dumps(results, ensure_ascii=False))
`
    const { stdout } = await exec(PY, ['-W', 'ignore', '-c', script], { timeout: 60000, maxBuffer: 10*1024*1024 })
    return NextResponse.json(JSON.parse(stdout))
  } catch (e: any) {
    return NextResponse.json({ error: String(e.stderr || e.message) }, { status: 500 })
  }
}
