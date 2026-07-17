import { NextRequest, NextResponse } from 'next/server'
import path from 'path'
import fs from 'fs'

const ROOT = path.resolve(process.cwd(), '..')
const SCORES_CACHE = path.join(ROOT, 'data', 'cache', 'scores.json')
const CACHE_MAX_AGE = 24 * 60 * 60 * 1000  // 24h

const MAX_CODES = 100

/**
 * 基金评分
 * GET /api/score
 *   ?codes=005660,016416  (max 100)
 *   ?includeBlocked=true  (默认隐藏 blocked 基金)
 *   ?min=NN  (过滤最低 total 分)
 */
export async function GET(req: NextRequest) {
  const codesParam = req.nextUrl.searchParams.get('codes') || ''
  const codes = codesParam.split(',').map(s => s.trim()).filter(Boolean)

  if (!codes.length) {
    return NextResponse.json({ error: 'missing codes', hint: '?codes=005660,016416' }, { status: 400 })
  }
  if (codes.length > MAX_CODES) {
    return NextResponse.json({
      error: `too many codes (${codes.length} > ${MAX_CODES})`,
      hint: `split into multiple requests`,
    }, { status: 400 })
  }
  const invalid = codes.filter(c => !/^\d{6}$/.test(c))
  if (invalid.length) {
    return NextResponse.json({ error: `invalid codes: ${invalid.join(',')}` }, { status: 400 })
  }

  const includeBlocked = req.nextUrl.searchParams.get('includeBlocked') === 'true'
  const minStr = req.nextUrl.searchParams.get('min') || ''
  const minVal = minStr ? parseFloat(minStr) : null
  if (minVal !== null && (isNaN(minVal) || minVal < 0 || minVal > 5)) {
    return NextResponse.json({ error: 'invalid min (expected 0..5)' }, { status: 400 })
  }

  if (!fs.existsSync(SCORES_CACHE)) {
    return NextResponse.json({
      error: 'score cache missing',
      path: SCORES_CACHE,
      hint: 'run: py -3.10 tools/build_score_cache.py',
    }, { status: 503 })
  }

  const stat = fs.statSync(SCORES_CACHE)
  const age = Date.now() - stat.mtimeMs
  if (age >= CACHE_MAX_AGE) {
    return NextResponse.json({
      error: 'score cache expired (>24h)',
      age_hours: Math.round(age / 3600 / 1000),
      hint: 'run: py -3.10 tools/build_score_cache.py',
    }, { status: 503 })
  }

  try {
    const all = JSON.parse(fs.readFileSync(SCORES_CACHE, 'utf-8'))
    const byCode: Record<string, any> = {}
    for (const it of (all.items || [])) byCode[it.code] = it

    const out: any[] = []
    const missing: string[] = []
    for (const c of codes) {
      const item = byCode[c]
      if (item) {
        if (!includeBlocked && item.blocked) continue
        if (minVal !== null && (item.total ?? 0) < minVal) continue
        out.push(item)
      } else {
        missing.push(c)
      }
    }

    return NextResponse.json({
      items: out,
      total: out.length,
      missing,
      filters: { includeBlocked, min: minVal },
      cache: { age_sec: Math.round(age / 1000), max_age_sec: CACHE_MAX_AGE / 1000 },
    }, {
      headers: {
        'X-Cache': 'hit',
        'X-Cache-Age': Math.round(age / 1000).toString(),
      },
    })
  } catch (e: any) {
    return NextResponse.json({ error: 'parse failed: ' + e.message }, { status: 500 })
  }
}
