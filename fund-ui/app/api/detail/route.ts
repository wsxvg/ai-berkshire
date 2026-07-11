import { NextRequest, NextResponse } from 'next/server'
import path from 'path'
import fs from 'fs'

const ROOT = path.resolve(process.cwd(), '..')
const CACHE = path.join(ROOT, 'data', 'fund_cache')
const CHARTS_DIR = path.join(ROOT, 'data', 'fund_charts')

function readJson(path: string): any {
  try { return JSON.parse(fs.readFileSync(path, 'utf-8')) } catch { return null }
}

export async function GET(req: NextRequest) {
  const code = req.nextUrl.searchParams.get('code') || ''
  if (!code) return NextResponse.json({ error: 'missing code' }, { status: 400 })

  // 各缓存拼装
  const profile = readJson(path.join(CACHE, `fund_profile_${code}.json`))
  const perf = readJson(path.join(CACHE, `fund_perf_${code}.json`))
  const holdings = readJson(path.join(CACHE, `fund_holdings_${code}.json`))
  const rules = readJson(path.join(CACHE, `trade_rules_${code}.json`))
  const manager = readJson(path.join(CACHE, `fund_manager_${code}.json`))
  const notices = readJson(path.join(CACHE, `fund_notices_${code}.json`))

  // chart (最近 90 个)
  let chartPts: { date: string; value: number }[] = []
  const chartFile = path.join(CHARTS_DIR, `${code}.json`)
  const chartRaw = readJson(chartFile) || readJson(path.join(ROOT, 'data', 'fund_charts.json'))?.[code] || []
  if (Array.isArray(chartRaw)) {
    const recent = chartRaw.slice(-90)
    chartPts = recent.map((p: any) => ({ date: String(p.xAxis).slice(0, 10), value: Number(p.yAxis) }))
  }

  const result = {
    code,
    name: profile?.full_name || '',
    type: profile?.fund_type || '',
    scale: profile?.scale || '',
    risk: profile?.risk_level || '',
    company: profile?.manager_company || '',
    rating: profile?.morningstar_rating || '',
    established: profile?.established || '',
    chart: chartPts,
    performance: perf?.performance || [],
    allocation: holdings?.allocation || {},
    topStocks: holdings?.top_stocks || [],
    rules: rules || null,
    manager: manager || null,
    notices: notices || null,
  }
  return NextResponse.json(result)
}
