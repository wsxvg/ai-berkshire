import { NextRequest, NextResponse } from 'next/server'
import path from 'path'
import fs from 'fs'

const ROOT = path.resolve(process.cwd(), '..')
const CACHE = path.join(ROOT, 'data', 'cache', 'ranking.json')
const CACHE_MAX_AGE = 24 * 60 * 60 * 1000  // 24h

/**
 * 全量基金排行
 * GET /api/ranking
 *   ?limit=N     (default 300, max 2000)
 *   ?sortBy=key  (r1y|r6m|r3m|r1m|sharpe|maxdd|... 或 +key/-key 显式升降序)
 *   ?type=XX     (基金类型过滤: 股票型/混合型/...)
 *   ?search=XX   (代码或名称模糊匹配)
 *   ?min=NN      (最低收益率阈值, %)
 */
export async function GET(req: NextRequest) {
  const limit = Math.max(1, Math.min(parseInt(req.nextUrl.searchParams.get('limit') || '300', 10) || 300, 2000))
  const sortBy = (req.nextUrl.searchParams.get('sortBy') || '').replace(/^[+-]/, '')
  const type = req.nextUrl.searchParams.get('type') || ''
  const search = (req.nextUrl.searchParams.get('search') || '').toLowerCase().trim()
  const minStr = req.nextUrl.searchParams.get('min') || ''
  const minVal = minStr ? parseFloat(minStr) : null

  if (minVal !== null && (isNaN(minVal) || minVal < -100 || minVal > 100)) {
    return NextResponse.json({ error: 'invalid min (expected -100..100)' }, { status: 400 })
  }

  // 读缓存
  if (!fs.existsSync(CACHE)) {
    return NextResponse.json({
      error: 'ranking cache missing or stale, run: py -3.10 tools/build_ranking_cache.py',
      path: CACHE,
    }, { status: 503 })
  }

  const stat = fs.statSync(CACHE)
  const age = Date.now() - stat.mtimeMs
  if (age >= CACHE_MAX_AGE) {
    return NextResponse.json({
      error: 'ranking cache expired (>24h), run: py -3.10 tools/build_ranking_cache.py',
      age_hours: Math.round(age / 3600 / 1000),
    }, { status: 503 })
  }

  let raw: any
  try {
    raw = JSON.parse(fs.readFileSync(CACHE, 'utf-8'))
  } catch (e: any) {
    return NextResponse.json({ error: 'parse cache failed: ' + e.message }, { status: 500 })
  }

  let items: any[] = raw.items || []
  const total_all = items.length

  // 过滤
  if (type) items = items.filter((it: any) => it.type === type)
  if (search) items = items.filter((it: any) =>
    (it.name || '').toLowerCase().includes(search) || (it.code || '').includes(search))
  if (minVal !== null) items = items.filter((it: any) => {
    const v = it[sortBy || 'r1y'] ?? it.r1y ?? 0
    return typeof v === 'number' && v >= minVal
  })

  // 排序
  if (sortBy) {
    const desc = !(req.nextUrl.searchParams.get('sortBy') || '').startsWith('-')
    items = [...items].sort((a: any, b: any) => {
      const va = a[sortBy]
      const vb = b[sortBy]
      if (va == null && vb == null) return 0
      if (va == null) return 1
      if (vb == null) return -1
      return desc ? vb - va : va - vb
    })
  }

  // limit
  const sliced = items.slice(0, limit)

  return NextResponse.json({
    items: sliced,
    total: items.length,
    total_all,
    filters: { limit, sortBy, type, search, min: minVal },
    cache: { age_sec: Math.round(age / 1000), max_age_sec: CACHE_MAX_AGE / 1000 },
  }, {
    headers: {
      'X-Cache': 'hit',
      'X-Cache-Age': Math.round(age / 1000).toString(),
      'X-Total': String(items.length),
    },
  })
}
