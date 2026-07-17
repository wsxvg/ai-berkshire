import { NextRequest, NextResponse } from 'next/server'
import path from 'path'
import fs from 'fs'

const ROOT = path.resolve(process.cwd(), '..')
const SIM_DIR = path.join(ROOT, 'reports', 'sim')

const MAX_HISTORY = 180  // 历史快照最多取 6 个月

function safeReadJson(p: string): any | null {
  try { return JSON.parse(fs.readFileSync(p, 'utf-8')) } catch { return null }
}

/**
 * 模拟实盘日报
 * GET /api/report
 *   ?days=N   (历史快照天数, 默认 60, 最大 180)
 *   ?file=XXX (指定返回哪份日报, 默认最新)
 */
export async function GET(req: NextRequest) {
  const days = Math.max(1, Math.min(parseInt(req.nextUrl.searchParams.get('days') || '60', 10) || 60, MAX_HISTORY))
  const file = req.nextUrl.searchParams.get('file') || ''

  try {
    if (!fs.existsSync(SIM_DIR)) {
      return NextResponse.json({
        error: 'no reports yet',
        hint: 'run: py -3.10 scripts/daily_simulation.py',
      }, { status: 404 })
    }

    let allFiles = fs.readdirSync(SIM_DIR)
      .filter(f => f.endsWith('.json') && f.startsWith('202'))
      .sort()
      .reverse()

    if (file) {
      if (!allFiles.includes(file)) {
        return NextResponse.json({
          error: 'file not found',
          file,
          available: allFiles.slice(0, 10),
        }, { status: 404 })
      }
      allFiles = [file]
    }

    // 最新日报
    const latest = allFiles.length > 0 ? safeReadJson(path.join(SIM_DIR, allFiles[0])) : null

    // 历史快照
    const snapshots: Array<{ date: string; total_value: number }> = []
    for (const f of allFiles.slice(0, days)) {
      const d = safeReadJson(path.join(SIM_DIR, f))
      if (!d) continue
      const snaps = d.snapshots || []
      for (const s of snaps) {
        if (s.date != null && s.total_value != null) {
          snapshots.push({ date: s.date, total_value: s.total_value })
        }
      }
    }
    snapshots.sort((a, b) => a.date.localeCompare(b.date))

    return NextResponse.json({
      latest,
      snapshots,
      meta: {
        total_files: allFiles.length,
        requested_file: file || 'latest',
        history_days: snapshots.length,
      },
    }, {
      headers: { 'Cache-Control': 'no-store' }  // 日报实时
    })
  } catch (e: any) {
    return NextResponse.json({ error: e.message }, { status: 500 })
  }
}
