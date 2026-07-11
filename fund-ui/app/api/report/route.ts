import { NextResponse } from 'next/server'
import fs from 'fs'
import path from 'path'

export async function GET() {
  const simDir = path.resolve(process.cwd(), '..', 'reports', 'sim')
  if (!fs.existsSync(simDir)) {
    return NextResponse.json([])
  }
  const files = fs.readdirSync(simDir)
    .filter(f => f.endsWith('.json') && f.startsWith('2026'))
    .sort()
    .reverse()
  
  if (files.length === 0) return NextResponse.json([])
  
  const latest = JSON.parse(fs.readFileSync(path.join(simDir, files[0]), 'utf-8'))
  return NextResponse.json(latest)
}
