import { NextRequest, NextResponse } from 'next/server'
import path from 'path'
import fs from 'fs'

const ROOT = path.resolve(process.cwd(), '..')
const CHARTS_DIR = path.join(ROOT, 'data', 'fund_charts')

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
  const codes = (req.nextUrl.searchParams.get('codes') || '').split(',').map(s => s.trim()).filter(Boolean)
  if (!codes.length) return NextResponse.json([])

  const allDates = new Set<string>()
  const codeData: Record<string, Record<string, number>> = {}
  for (const code of codes) {
    const pts = readChart(code)
    if (!pts) continue
    // 取最近 90 条
    const last90 = pts.slice(-90)
    codeData[code] = {}
    for (const p of last90) {
      codeData[code][p.date] = p.val
      allDates.add(p.date)
    }
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
  return NextResponse.json(result)
}
