import { NextResponse } from 'next/server'
import fs from 'fs'
import path from 'path'

export async function GET() {
  const simDir = path.resolve(process.cwd(), '..', 'reports', 'sim')
  try {
    if (!fs.existsSync(simDir)) {
      return NextResponse.json({ error: 'no reports yet' }, { status: 404 })
    }
    const files = fs.readdirSync(simDir)
      .filter(f => f.endsWith('.json') && f.startsWith('2026'))
      .sort()
      .reverse()

    // 最新日报
    const latest = files.length > 0
      ? JSON.parse(fs.readFileSync(path.join(simDir, files[0]), 'utf-8'))
      : null

    // 历史快照数据（用于趋势图）
    const snapshots: Array<{ date: string; total_value: number }> = []
    for (const f of files.slice(0, 60)) {
      try {
        const d = JSON.parse(fs.readFileSync(path.join(simDir, f), 'utf-8'))
        const snaps = d.snapshots || []
        snapshots.push(...snaps.map((s: any) => ({ date: s.date, total_value: s.total_value })))
      } catch {}
    }
    snapshots.sort((a, b) => a.date.localeCompare(b.date))

    return NextResponse.json({ latest, snapshots })
  } catch (e: any) {
    return NextResponse.json({ error: e.message }, { status: 500 })
  }
}
