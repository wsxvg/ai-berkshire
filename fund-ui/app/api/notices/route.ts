import { NextRequest, NextResponse } from 'next/server'
import path from 'path'
import fs from 'fs'

const ROOT = path.resolve(process.cwd(), '..')
const CACHE = path.join(ROOT, 'data', 'fund_cache')

const DEFAULT_KEYWORDS = ['限购', '分红', '清盘', '转换', '合并', '份额', '费率']
const MAX_CODES = 100

/**
 * 关键公告
 * GET /api/notices?codes=005660,016416
 *   ?criticalOnly=true  (默认 false, 返回所有公告)
 *   ?keywords=限购,清盘  (自定义关键词, 逗号分隔)
 *   ?limit=N            (每只基金最多取几条, 默认 5, 最大 20)
 *   ?days=N             (只看最近 N 天, 默认 90, 最大 365)
 */
export async function GET(req: NextRequest) {
  const codesParam = req.nextUrl.searchParams.get('codes') || ''
  const codes = codesParam.split(',').map(s => s.trim()).filter(Boolean)

  if (!codes.length) {
    return NextResponse.json([], { status: 200 })  // 没传 code 是合法状态, 返空数组
  }
  if (codes.length > MAX_CODES) {
    return NextResponse.json({ error: `too many codes (${codes.length} > ${MAX_CODES})` }, { status: 400 })
  }

  const criticalOnly = req.nextUrl.searchParams.get('criticalOnly') === 'true'
  const customKeywords = (req.nextUrl.searchParams.get('keywords') || '').split(',').map(s => s.trim()).filter(Boolean)
  const keywords = customKeywords.length ? customKeywords : DEFAULT_KEYWORDS
  const limit = Math.max(1, Math.min(parseInt(req.nextUrl.searchParams.get('limit') || '5', 10) || 5, 20))
  const days = Math.max(1, Math.min(parseInt(req.nextUrl.searchParams.get('days') || '90', 10) || 90, 365))

  const cutoff = Date.now() - days * 24 * 3600 * 1000

  const results: any[] = []
  const missing: string[] = []

  for (const code of codes) {
    const file = path.join(CACHE, `fund_notices_${code}.json`)
    if (!fs.existsSync(file)) { missing.push(code); continue }
    try {
      const n = JSON.parse(fs.readFileSync(file, 'utf-8'))
      const notices = n.notices || []
      for (const nb of notices) {
        const title = nb.title || ''
        const is_critical = keywords.some(kw => title.includes(kw))
        if (criticalOnly && !is_critical) continue

        // 日期过滤
        let nbDate: number = 0
        if (nb.date) {
          const d = new Date(nb.date.replace(/\./g, '-').replace(/\//g, '-'))
          if (!isNaN(d.getTime())) nbDate = d.getTime()
        }
        if (days < 365 && nbDate && nbDate < cutoff) continue

        results.push({
          code,
          date: nb.date || '',
          title,
          url: nb.url || '',
          type: nb.type || '',
          is_critical,
        })
        if (results.filter(r => r.code === code).length >= limit) break
      }
    } catch { /* skip */ }
  }

  // 排序: 关键公告优先, 然后按日期降序
  results.sort((a, b) => {
    if (a.is_critical !== b.is_critical) return a.is_critical ? -1 : 1
    return (b.date || '').localeCompare(a.date || '')
  })

  return NextResponse.json({
    items: results,
    total: results.length,
    missing: missing.length ? missing : undefined,
    filters: { criticalOnly, keywords, days, limit },
  }, {
    headers: { 'X-Cache': 'bypass' }
  })
}
