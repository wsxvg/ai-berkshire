import { NextRequest, NextResponse } from 'next/server'
import path from 'path'
import fs from 'fs'

const ROOT = path.resolve(process.cwd(), '..')
const CHARTS_DIR = path.join(ROOT, 'data', 'fund_charts')

// 限制: 防止一次请求处理过多基金拖垮内存
const MAX_CODES = 10
const DEFAULT_DAYS = 90
const MAX_DAYS = 365

// 进程内缓存: (codes, days) -> result
const memCache = new Map<string, { ts: number; data: any }>()
const MEM_TTL = 5 * 60 * 1000  // 5min

function readChart(code: string): { date: string; val: number }[] | null {
  // 优先读目录版
  const file = path.join(CHARTS_DIR, `${code}.json`)
  if (fs.existsSync(file)) {
    try {
      const pts = JSON.parse(fs.readFileSync(file, 'utf-8'))
      return pts.map((p: any) => ({ date: String(p.xAxis).slice(0, 10), val: Number(p.yAxis) }))
    } catch { /* fall through */ }
  }
  // 退化读聚合版
  const agg = path.join(ROOT, 'data', 'fund_charts.json')
  if (fs.existsSync(agg)) {
    try {
      const all = JSON.parse(fs.readFileSync(agg, 'utf-8'))
      const pts = all[code]
      if (Array.isArray(pts)) return pts.map((p: any) => ({ date: String(p.xAxis).slice(0, 10), val: Number(p.yAxis) }))
    } catch { /* fall through */ }
  }
  return null
}

export async function GET(req: NextRequest) {
  const codesParam = req.nextUrl.searchParams.get('codes') || ''
  const codes = codesParam.split(',').map(s => s.trim()).filter(Boolean)

  // 边界: 0 个 code
  if (!codes.length) {
    return NextResponse.json({ error: 'missing codes', hint: 'use ?codes=005660,016416' }, { status: 400 })
  }
  // 边界: 太多 code
  if (codes.length > MAX_CODES) {
    return NextResponse.json({
      error: `too many codes (${codes.length} > ${MAX_CODES})`,
      hint: `max ${MAX_CODES} funds at once`,
    }, { status: 400 })
  }
  // 边界: 非法格式
  const invalid = codes.filter(c => !/^\d{6}$/.test(c))
  if (invalid.length) {
    return NextResponse.json({ error: `invalid fund codes: ${invalid.join(',')}`, hint: 'expect 6 digits each' }, { status: 400 })
  }

  // 边界: days
  const days = Math.max(1, Math.min(parseInt(req.nextUrl.searchParams.get('days') || String(DEFAULT_DAYS), 10) || DEFAULT_DAYS, MAX_DAYS))

  // 缓存
  const cacheKey = [...codes].sort().join(',') + '|' + days
  const mem = memCache.get(cacheKey)
  if (mem && Date.now() - mem.ts < MEM_TTL) {
    return NextResponse.json(mem.data, { headers: { 'X-Cache': 'memory' } })
  }

  // 拉取
  const allDates = new Set<string>()
  const codeData: Record<string, Record<string, number>> = {}
  const missing: string[] = []

  for (const code of codes) {
    const pts = readChart(code)
    if (!pts) { missing.push(code); continue }
    const lastN = pts.slice(-days)
    codeData[code] = {}
    for (const p of lastN) {
      codeData[code][p.date] = p.val
      allDates.add(p.date)
    }
  }

  if (Object.keys(codeData).length === 0) {
    return NextResponse.json({
      error: 'no chart data for any code',
      missing,
      hint: '请先运行 daily_live.py 抓取净值',
    }, { status: 404 })
  }

  const dates = Array.from(allDates).sort()
  const result = dates.map(d => {
    const row: Record<string, number | string> = { date: d }
    for (const code of codes) {
      const v = codeData[code]?.[d]
      if (typeof v === 'number') row[code] = Math.round(v * 100) / 100
    }
    return row
  })

  const respBody = {
    codes,
    days,
    date_range: { start: dates[0], end: dates[dates.length - 1] },
    missing: missing.length ? missing : undefined,
    series: result,
  }

  memCache.set(cacheKey, { ts: Date.now(), data: respBody })
  return NextResponse.json(respBody)
}
