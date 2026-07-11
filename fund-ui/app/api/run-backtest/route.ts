import { NextRequest, NextResponse } from 'next/server'
import { exec } from 'child_process'
import path from 'path'
import fs from 'fs'

const ROOT = path.resolve(process.cwd(), '..')

function runPy(file: string): Promise<string> {
  return new Promise((resolve, reject) => {
    exec(`python "${file}"`, {
      cwd: ROOT, timeout: 120000, maxBuffer: 10*1024*1024, encoding: 'buffer',
      env: { ...process.env, PYTHONIOENCODING: 'utf-8' }
    }, (err, stdout, stderr) => {
      if (err) reject(new Error(stderr?.toString('utf-8') || err.message))
      else resolve(stdout.toString('utf-8'))
    })
  })
}

export async function POST(req: NextRequest) {
  try {
    const body = await req.json()
    const start = body.start || '2024-03-11'
    const end = body.end || '2026-07-01'
    const cash = body.cash || 100000

    const tmp = path.join(ROOT, '_api_runbt.py')
    fs.writeFileSync(tmp, `import json, sys; sys.path.insert(0, '.')
from backtest.engine.backtest import run_backtest
evo = json.loads(open('data/evolution/best_config.json', 'r', encoding='utf-8').read())
cfg = evo['config']
cfg['start_date'] = '${start}'
cfg['end_date'] = '${end}'
cfg['initial_cash'] = ${cash}
import io
stdout = io.StringIO()
import sys as _sys
old = _sys.stdout; _sys.stdout = stdout
r = run_backtest(cfg)
_sys.stdout = old
result = {
    'annualized': r.get('annualized_return', 0),
    'total_return': r.get('total_return', 0),
    'sharpe': r.get('sharpe_ratio', 0),
    'max_drawdown': r.get('max_drawdown', 0),
    'calmar': r.get('calmar_ratio', 0),
    'trade_count': r.get('trade_count', 0),
    'benchmark': r.get('benchmark_return', 0),
    'final_value': r.get('final_value', 0),
    'fees': r.get('total_fees', 0),
}
print(json.dumps(result, ensure_ascii=False))`, 'utf-8')
    const stdout = await runPy(tmp)
    fs.unlinkSync(tmp)
    return NextResponse.json(JSON.parse(stdout.trim()))
  } catch (e: any) {
    return NextResponse.json({ error: e.message }, { status: 500 })
  }
}
