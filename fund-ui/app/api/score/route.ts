import { NextRequest, NextResponse } from 'next/server'
import path from 'path'
import fs from 'fs'

const ROOT = path.resolve(process.cwd(), '..')
const SCORES_CACHE = path.join(ROOT, 'data', 'cache', 'scores.json')
const CACHE_MAX_AGE = 24 * 60 * 60 * 1000  // 24h

export async function GET(req: NextRequest) {
  const codes = (req.nextUrl.searchParams.get('codes') || '').split(',').map(s => s.trim()).filter(Boolean)
  if (!codes.length) return NextResponse.json({ error: 'missing codes' }, { status: 400 })

  // 读预计算
  if (fs.existsSync(SCORES_CACHE)) {
    const stat = fs.statSync(SCORES_CACHE)
    if (Date.now() - stat.mtimeMs < CACHE_MAX_AGE) {
      try {
        const all = JSON.parse(fs.readFileSync(SCORES_CACHE, 'utf-8'))
        const byCode: Record<string, any> = {}
        for (const it of (all.items || [])) byCode[it.code] = it
        const out = codes.map(c => byCode[c]).filter(Boolean)
        if (out.length) {
          return NextResponse.json(out, {
            headers: { 'X-Cache': 'hit', 'X-Cache-Age': Math.round((Date.now() - stat.mtimeMs) / 1000).toString() },
          })
        }
        // 都不在缓存里 (可能自选里有新基金)
      } catch (e) { /* fall through */ }
    }
  }
  return NextResponse.json({
    error: 'score cache missing or stale, run: py -3.10 tools/build_score_cache.py',
    path: SCORES_CACHE,
  }, { status: 503 })
}
