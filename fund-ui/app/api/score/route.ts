import { NextRequest, NextResponse } from 'next/server'
import { spawn } from 'child_process'
import path from 'path'

const PY = 'py'
const ROOT = path.resolve(process.cwd(), '..')
const ROOT_PY = ROOT.replace(/\\/g, '\\\\')

function runPython(script: string): Promise<string> {
  return new Promise((resolve, reject) => {
    const proc = spawn(PY, ['-W', 'ignore', '-c', script], { timeout: 60000, maxBuffer: 10*1024*1024 })
    let stdout = ''
    let stderr = ''
    proc.stdout.on('data', (d) => { stdout += d })
    proc.stderr.on('data', (d) => { stderr += d })
    proc.on('close', (code) => {
      if (code === 0) resolve(stdout)
      else reject(new Error(stderr || `exit ${code}`))
    })
    proc.on('error', reject)
  })
}

export async function GET(req: NextRequest) {
  const codes = req.nextUrl.searchParams.get('codes') || ''
  if (!codes) return NextResponse.json({ error: 'missing codes' }, { status: 400 })

  try {
    const script = `import json as _json, sys, glob
from pathlib import Path
sys.path.insert(0, r'${ROOT_PY}')
from backtest.engine.backtest import score_fund_backtest, score_4433, detect_market_state
from tools.technical_indicators import compute_entry_timing_score, compute_rsi
from datetime import datetime

ROOT = Path(r'${ROOT_PY}')
fc = _json.loads((ROOT / 'data' / 'fund_charts.json').read_text('utf-8'))
trades = _json.loads((ROOT / 'backtest' / 'data' / 'trading_by_date_fixed.json').read_text('utf-8'))

CACHE = ROOT / 'data' / 'fund_cache'
def load(prefix):
    d = {}
    for f in glob.glob(str(CACHE / f'{prefix}_*.json')):
        c = Path(f).stem.replace(f'{prefix}_', '', 1)
        try: d[c] = _json.loads(open(f, encoding='utf-8').read())
        except: pass
    return d

fr = load('trade_rules'); fm = load('fund_manager'); fp = load('fund_profile')
TODAY = datetime.now().strftime('%Y-%m-%d')
market = detect_market_state(TODAY, fc)

results = []
for code in '${codes}'.split(','):
    code = code.strip()
    if code not in fr: continue
    name = fp.get(code, {}).get('full_name', code)
    blocked = False; block_reason = ''
    pts = fc.get(code, [])
    if len(pts) >= 60:
        timing = compute_entry_timing_score(pts, TODAY)
        if timing.get('should_warn'): blocked = True; block_reason = 'RSI超买'
    try:
        fs = score_fund_backtest(code, name, fc, None, fr.get(code), fm.get(code), TODAY, trades, fp.get(code))
        s = {'total': round(fs.total, 1)}
        for d in ['quality','cost','manager','momentum','smart_money']:
            dim = getattr(fs, d, None)
            s[d] = round(dim.score, 1) if dim else 0
    except:
        s = {'total': 3.0, 'quality': 3.0, 'cost': 3.0, 'manager': 3.0, 'momentum': 3.0, 'smart_money': 0}
    p4433 = score_4433(code, TODAY, fc)[1]
    rsi_val = None
    if len(pts) >= 60:
        try:
            valid = [p for p in pts if p['xAxis'] <= TODAY]
            navs = [(100 + float(p['yAxis'])) / 100 for p in valid]
            rsi_val = round(compute_rsi(navs), 1)
        except: pass
    results.append({'code': code, 'name': name, **s, 'pass4433': p4433, 'rsi': rsi_val, 'blocked': blocked, 'blockReason': block_reason})
results.sort(key=lambda x: -x['total'])
print(_json.dumps(results, ensure_ascii=False))`
    const stdout = await runPython(script)
    return NextResponse.json(JSON.parse(stdout))
  } catch (e: any) {
    return NextResponse.json({ error: e.message }, { status: 500 })
  }
}
