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
    if (files.length === 0) return NextResponse.json({ error: 'no reports yet' }, { status: 404 })
    const latest = JSON.parse(fs.readFileSync(path.join(simDir, files[0]), 'utf-8'))
    return NextResponse.json(latest)
  } catch (e: any) {
    return NextResponse.json({ error: e.message }, { status: 500 })
  }
}
