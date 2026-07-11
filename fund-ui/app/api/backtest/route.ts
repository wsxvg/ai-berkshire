import { NextResponse } from 'next/server'
import fs from 'fs'
import path from 'path'

export async function GET() {
  const evoPath = path.resolve(process.cwd(), '..', 'data', 'evolution', 'best_config.json')
  try {
    if (!fs.existsSync(evoPath)) {
      return NextResponse.json(null)
    }
    const data = JSON.parse(fs.readFileSync(evoPath, 'utf-8'))
    return NextResponse.json(data)
  } catch (e: any) {
    return NextResponse.json({ error: e.message }, { status: 500 })
  }
}
