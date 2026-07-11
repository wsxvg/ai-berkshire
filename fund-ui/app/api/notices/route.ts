import { NextRequest, NextResponse } from 'next/server'
import path from 'path'
import fs from 'fs'

const ROOT = path.resolve(process.cwd(), '..')
const CACHE = path.join(ROOT, 'data', 'fund_cache')

const KEYWORDS = ['限购', '分红', '清盘', '转换', '合并', '份额', '费率']

export async function GET(req: NextRequest) {
  const codes = (req.nextUrl.searchParams.get('codes') || '').split(',').map(s => s.trim()).filter(Boolean)
  if (!codes.length) return NextResponse.json([])

  const results: any[] = []
  for (const code of codes) {
    const file = path.join(CACHE, `fund_notices_${code}.json`)
    if (!fs.existsSync(file)) continue
    try {
      const n = JSON.parse(fs.readFileSync(file, 'utf-8'))
      const notices = n.notices || []
      for (const nb of notices.slice(0, 5)) {
        const title = nb.title || ''
        const is_critical = KEYWORDS.some(kw => title.includes(kw))
        results.push({
          code,
          date: nb.date || '',
          title,
          url: nb.url || '',
          type: nb.type || '',
          is_critical,
        })
      }
    } catch { /* skip */ }
  }
  return NextResponse.json(results)
}
