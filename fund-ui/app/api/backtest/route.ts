import { NextRequest, NextResponse } from 'next/server'
import path from 'path'
import fs from 'fs'

const ROOT = path.resolve(process.cwd(), '..')
const EVO_PATH = path.join(ROOT, 'data', 'evolution', 'best_config.json')
const EVO_DIR = path.join(ROOT, 'data', 'evolution')

/**
 * 进化最优配置
 * GET /api/backtest            - 最新最优配置
 * GET /api/backtest?list=true  - 列出所有历史最优 (含时间戳)
 */
export async function GET(req: NextRequest) {
  const list = req.nextUrl.searchParams.get('list') === 'true'

  try {
    if (list) {
      // 列出所有 best_config_* 历史
      if (!fs.existsSync(EVO_DIR)) {
        return NextResponse.json({ items: [], error: 'evolution dir not found' }, { status: 404 })
      }
      const files = fs.readdirSync(EVO_DIR)
        .filter(f => f.startsWith('best_config'))
        .sort()
        .reverse()
      const items = files.map(f => {
        const p = path.join(EVO_DIR, f)
        const stat = fs.statSync(p)
        let data: any = null
        try { data = JSON.parse(fs.readFileSync(p, 'utf-8')) } catch {}
        return {
          file: f,
          mtime: stat.mtimeMs,
          age_sec: Math.round((Date.now() - stat.mtimeMs) / 1000),
          annualized: data?.annualized_return ?? data?.annualized,
          sharpe: data?.sharpe_ratio ?? data?.sharpe,
          total_return: data?.total_return,
        }
      })
      return NextResponse.json({ items, total: items.length })
    }

    if (!fs.existsSync(EVO_PATH)) {
      // 没历史, 返 null 让前端处理
      return NextResponse.json(null, { status: 200 })
    }
    const data = JSON.parse(fs.readFileSync(EVO_PATH, 'utf-8'))
    return NextResponse.json(data)
  } catch (e: any) {
    return NextResponse.json({ error: e.message }, { status: 500 })
  }
}
