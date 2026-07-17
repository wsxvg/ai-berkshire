import { NextRequest, NextResponse } from 'next/server'
import path from 'path'
import fs from 'fs'
import { cachedJson } from '../_cache'

const ROOT = path.resolve(process.cwd(), '..')
const CACHE = path.join(ROOT, 'data', 'fund_cache')
const CHARTS_DIR = path.join(ROOT, 'data', 'fund_charts')

function readJson(p: string): any {
  try { return JSON.parse(fs.readFileSync(p, 'utf-8')) } catch { return null }
}

function loadDetail(code: string) {
  const profile = readJson(path.join(CACHE, `fund_profile_${code}.json`))
  const perf = readJson(path.join(CACHE, `fund_perf_${code}.json`))
  const holdings = readJson(path.join(CACHE, `fund_holdings_${code}.json`))
  const rules = readJson(path.join(CACHE, `trade_rules_${code}.json`))
  const manager = readJson(path.join(CACHE, `fund_manager_${code}.json`))
  const notices = readJson(path.join(CACHE, `fund_notices_${code}.json`))

  // chart (最近 90 个) - 双源 fallback
  let chartPts: { date: string; value: number }[] = []
  const chartFile = path.join(CHARTS_DIR, `${code}.json`)
  const chartRaw = readJson(chartFile) || readJson(path.join(ROOT, 'data', 'fund_charts.json'))?.[code] || []
  if (Array.isArray(chartRaw)) {
    const recent = chartRaw.slice(-90)
    chartPts = recent.map((p: any) => ({ date: String(p.xAxis).slice(0, 10), value: Number(p.yAxis) }))
  }

  return {
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
}

// 缓存 30min (基金详情变更频次低)
const detailHandler = cachedJson('detail.json', 30 * 60 * 1000, async (req?: NextRequest) => {
  if (!req) throw new Error('no request')
  const code = req.nextUrl.searchParams.get('code') || ''
  if (!code) return { error: 'missing code' } as any
  if (!/^\d{6}$/.test(code)) return { error: 'invalid fund code (expect 6 digits)' } as any
  return loadDetail(code)
})

export async function GET(req: NextRequest) {
  const code = req.nextUrl.searchParams.get('code') || ''
  if (!code) return NextResponse.json({ error: 'missing code' }, { status: 400 })
  if (!/^\d{6}$/.test(code)) return NextResponse.json({ error: 'invalid fund code (expect 6 digits)' }, { status: 400 })

  try {
    // 调用 cachedJson handler 拿到 NextResponse, 读出 body 再加自定义校验
    const res = await detailHandler(req)
    const data = await res.json()
    if (data && data.error) {
      return NextResponse.json(data, { status: 400 })
    }
    if (!data.name && (!data.chart || data.chart.length === 0)) {
      return NextResponse.json({ error: `fund ${code} not found in cache`, code }, { status: 404 })
    }
    // 透传原响应 (含 X-Cache 头)
    return NextResponse.json(data, { headers: Object.fromEntries(res.headers.entries()) })
  } catch (e: any) {
    return NextResponse.json({ error: e.message }, { status: 500 })
  }
}
