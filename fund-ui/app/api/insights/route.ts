import { NextResponse } from 'next/server'
import path from 'path'
import fs from 'fs'

const ROOT = path.resolve(process.cwd(), '..')
const MEMORY_DIR = path.join(ROOT, 'data', 'memory')

/**
 * 跨基金 insights + 长期记忆查询
 * GET /api/insights            - 最新 N 条 insight
 * GET /api/insights?code=XXX   - 单只基金的分析历史/信号历史
 * GET /api/insights?code=XXX&type=signals
 * GET /api/insights?code=XXX&type=analysis
 * GET /api/insights?code=XXX&type=manager_changes
 */
export async function GET(req: import('next/server').NextRequest) {
  const code = req.nextUrl.searchParams.get('code')
  const type = req.nextUrl.searchParams.get('type') || 'insights'
  const limit = Math.min(parseInt(req.nextUrl.searchParams.get('limit') || '10', 10), 100)

  if (!fs.existsSync(MEMORY_DIR)) {
    return NextResponse.json({ items: [], error: 'memory dir not initialized' }, { status: 404 })
  }

  // 全局 insights
  if (!code && type === 'insights') {
    const p = path.join(MEMORY_DIR, 'insights.json')
    if (!fs.existsSync(p)) return NextResponse.json({ items: [] })
    try {
      const items = JSON.parse(fs.readFileSync(p, 'utf-8'))
      return NextResponse.json({ items: items.slice(-limit).reverse() })
    } catch (e: any) {
      return NextResponse.json({ error: e.message }, { status: 500 })
    }
  }

  if (!code) {
    return NextResponse.json({ error: 'missing code' }, { status: 400 })
  }

  // 单只基金
  const fileMap: Record<string, string> = {
    signals: `signals_${code}.json`,
    analysis: `analysis_${code}.json`,
    manager_changes: `manager_changes_${code}.json`,
  }

  const fname = fileMap[type]
  if (!fname) {
    return NextResponse.json({ error: `unknown type: ${type}` }, { status: 400 })
  }
  const p = path.join(MEMORY_DIR, fname)
  if (!fs.existsSync(p)) {
    return NextResponse.json({ code, type, items: [] })
  }
  try {
    const items = JSON.parse(fs.readFileSync(p, 'utf-8'))
    return NextResponse.json({ code, type, items: items.slice(-limit).reverse() })
  } catch (e: any) {
    return NextResponse.json({ error: e.message }, { status: 500 })
  }
}
