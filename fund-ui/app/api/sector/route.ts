import { NextRequest, NextResponse } from 'next/server'
import fs from 'fs'
import path from 'path'

const ROOT = path.resolve(process.cwd(), '..')

export async function GET(req: NextRequest) {
  const code = req.nextUrl.searchParams.get('code')
  const file = path.join(ROOT, 'data', 'industry_valuation.json')
  if (!fs.existsSync(file)) {
    return NextResponse.json({ error: 'no industry data' }, { status: 404 })
  }
  try {
    const data = JSON.parse(fs.readFileSync(file, 'utf-8'))
    if (code) {
      const sector = data[code]
      if (!sector) return NextResponse.json({ error: 'sector not found' }, { status: 404 })
      // 找最新点
      const history = sector.pe_history || []
      const latest = history[history.length - 1]
      return NextResponse.json({
        code,
        name: sector.description || code,
        latest: latest || null,
        history_days: history.length,
      })
    }
    // 列出所有行业
    const summary: any = {}
    for (const [k, v] of Object.entries(data) as any) {
      const history = v.pe_history || []
      const latest = history[history.length - 1]
      summary[k] = {
        name: v.description || k,
        pe_pct: latest?.pe_pct ?? null,
        pb_pct: latest?.pb_pct ?? null,
        valuation_status: latest?.pe_pct != null
          ? (latest.pe_pct > 70 ? '高估' : latest.pe_pct < 30 ? '低估' : '中性')
          : '未知',
        signal_score: v.signal_score ?? null,
      }
    }
    return NextResponse.json(summary)
  } catch (e: any) {
    return NextResponse.json({ error: e.message }, { status: 500 })
  }
}
