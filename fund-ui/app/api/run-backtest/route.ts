import { NextRequest, NextResponse } from 'next/server'
import { exec } from 'child_process'
import path from 'path'
import fs from 'fs'

const ROOT = path.resolve(process.cwd(), '..')
const EVO_PATH = path.join(ROOT, 'data', 'evolution', 'best_config.json')

const MAX_TIMEOUT = 300 * 1000  // 5min

function runPy(file: string, timeoutMs: number): Promise<string> {
  return new Promise((resolve, reject) => {
    exec(`python "${file}"`, {
      cwd: ROOT, timeout: timeoutMs, maxBuffer: 10*1024*1024, encoding: 'buffer',
      env: { ...process.env, PYTHONIOENCODING: 'utf-8' }
    }, (err, stdout, stderr) => {
      if (err) reject(new Error(stderr?.toString('utf-8') || err.message))
      else resolve(stdout.toString('utf-8'))
    })
  })
}

function isValidDate(s: string): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(s)) return false
  const d = new Date(s)
  return !isNaN(d.getTime())
}

/**
 * 自定义回测
 * POST /api/run-backtest
 * body: {
 *   start?: 'YYYY-MM-DD' (default: 2024-03-11)
 *   end?: 'YYYY-MM-DD' (default: 2026-07-01)
 *   cash?: number (default: 100000, min 10000, max 10000000)
 *   timeout?: number (秒, 默认 120, 最大 300)
 *   config?: object (覆盖 best_config)
 * }
 */
export async function POST(req: NextRequest) {
  const startedAt = Date.now()
  try {
    const body = await req.json().catch(() => ({}))
    const start = body.start || '2024-03-11'
    const end = body.end || '2026-07-01'
    const cash = body.cash || 100000
    const timeoutSec = Math.max(10, Math.min(parseInt(body.timeout || '120', 10) || 120, MAX_TIMEOUT / 1000))
    const customConfig = body.config || null

    // 校验
    if (!isValidDate(start)) return NextResponse.json({ error: 'invalid start (expect YYYY-MM-DD)' }, { status: 400 })
    if (!isValidDate(end)) return NextResponse.json({ error: 'invalid end (expect YYYY-MM-DD)' }, { status: 400 })
    if (new Date(start) >= new Date(end)) return NextResponse.json({ error: 'start must be < end' }, { status: 400 })
    if (typeof cash !== 'number' || cash < 10000 || cash > 10000000) {
      return NextResponse.json({ error: 'invalid cash (10000..10000000)' }, { status: 400 })
    }
    if (customConfig && typeof customConfig !== 'object') {
      return NextResponse.json({ error: 'config must be object' }, { status: 400 })
    }

    if (!fs.existsSync(EVO_PATH)) {
      return NextResponse.json({
        error: 'best_config.json not found',
        hint: 'run: py -3.10 tools/evolution_loop.py (生成进化最优参数)',
      }, { status: 404 })
    }

    const tmp = path.join(ROOT, '_api_runbt.py')
    const configOverride = customConfig ? `\ncfg.update(${JSON.stringify(customConfig)})` : ''

    fs.writeFileSync(tmp, `import json, sys; sys.path.insert(0, '.')
from backtest.engine.backtest import run_backtest
evo = json.loads(open('data/evolution/best_config.json', 'r', encoding='utf-8').read())
cfg = evo['config']
cfg['start_date'] = '${start}'
cfg['end_date'] = '${end}'
cfg['initial_cash'] = ${cash}${configOverride}
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
    const stdout = await runPy(tmp, timeoutSec * 1000)
    fs.unlinkSync(tmp)
    const result = JSON.parse(stdout.trim())
    return NextResponse.json({
      ...result,
      meta: {
        elapsed_ms: Date.now() - startedAt,
        start, end, cash,
        config_overridden: !!customConfig,
      },
    })
  } catch (e: any) {
    try { fs.unlinkSync(path.join(ROOT, '_api_runbt.py')) } catch {}
    const isTimeout = e.message?.includes('TIMEOUT') || e.signal === 'SIGTERM'
    return NextResponse.json({
      error: isTimeout ? `回测超时 (>${MAX_TIMEOUT/1000}s)` : e.message,
      hint: isTimeout ? '尝试缩小区间或降低 initial_cash' : undefined,
    }, { status: isTimeout ? 504 : 500 })
  }
}
