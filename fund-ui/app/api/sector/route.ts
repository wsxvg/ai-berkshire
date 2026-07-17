import { NextRequest, NextResponse } from 'next/server'
import fs from 'fs'
import path from 'path'

const ROOT = path.resolve(process.cwd(), '..')

/**
 * 行业估值
 * GET /api/sector                  - 全部行业概览
 * GET /api/sector?code=XXX         - 单行业详情
 * GET /api/sector?status=low|mid|high  - 按估值状态过滤
 */
export async function GET(req: NextRequest) {
  const code = req.nextUrl.searchParams.get('code')
  const status = req.nextUrl.searchParams.get('status')
  const file = path.join(ROOT, 'data', 'industry_valuation.json')

  if (!fs.existsSync(file)) {
    return NextResponse.json({
      error: 'no industry data',
      hint: 'run: py -3.10 tools/sector_valuator.py (or any sector data builder)',
    }, { status: 404 })
  }

  try {
    const data = JSON.parse(fs.readFileSync(file, 'utf-8'))

    // 状态过滤
    const validStatuses = ['low', 'mid', 'high', '低估', '中性', '高估']
    if (status && !validStatuses.includes(status)) {
      return NextResponse.json({ error: `invalid status (use: ${validStatuses.join(',')})` }, { status: 400 })
    }

    if (code) {
      const sector = data[code]
      if (!sector) {
        return NextResponse.json({
          error: 'sector not found',
          code,
          available: Object.keys(data).slice(0, 20),
        }, { status: 404 })
      }
      const history = sector.pe_history || []
      const latest = history[history.length - 1]
      return NextResponse.json({
        code,
        name: sector.description || code,
        latest: latest || null,
        history_days: history.length,
        history: history.slice(-180),  // 最近 6 个月
        signal_score: sector.signal_score ?? null,
      })
    }

    // 列表
    const summary: any = {}
    for (const [k, v] of Object.entries(data) as any) {
      const history = v.pe_history || []
      const latest = history[history.length - 1]
      const st = latest?.pe_pct != null
        ? (latest.pe_pct > 70 ? 'high' : latest.pe_pct < 30 ? 'low' : 'mid')
        : 'unknown'
      summary[k] = {
        name: v.description || k,
        pe_pct: latest?.pe_pct ?? null,
        pb_pct: latest?.pb_pct ?? null,
        valuation_status: latest?.pe_pct != null
          ? (latest.pe_pct > 70 ? '高估' : latest.pe_pct < 30 ? '低估' : '中性')
          : '未知',
        valuation_code: st,
        signal_score: v.signal_score ?? null,
      }
    }

    // 状态过滤
    let filtered = summary
    if (status) {
      const stMap: Record<string, string[]> = {
        low: ['low', '低估'], mid: ['mid', '中性'], high: ['high', '高估'],
      }
      const match = stMap[status] || [status]
      filtered = Object.fromEntries(
        Object.entries(summary).filter(([_, v]) => match.includes(v.valuation_code) || match.includes(v.valuation_status))
      )
    }

    return NextResponse.json({
      items: filtered,
      total: Object.keys(filtered).length,
      filters: { status: status || 'all' },
    })
  } catch (e: any) {
    return NextResponse.json({ error: e.message }, { status: 500 })
  }
}
