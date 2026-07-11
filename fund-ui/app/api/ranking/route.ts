import { NextRequest, NextResponse } from 'next/server'
import path from 'path'
import fs from 'fs'

const ROOT = path.resolve(process.cwd(), '..')
const CACHE = path.join(ROOT, 'data', 'cache', 'ranking.json')
const CACHE_MAX_AGE = 24 * 60 * 60 * 1000  // 24h

export async function GET(req: NextRequest) {
  const limit = parseInt(req.nextUrl.searchParams.get('limit') || '300')
  // 检查预计算缓存 (1 天内有效)
  if (fs.existsSync(CACHE)) {
    const stat = fs.statSync(CACHE)
    const age = Date.now() - stat.mtimeMs
    if (age < CACHE_MAX_AGE) {
      try {
        const data = JSON.parse(fs.readFileSync(CACHE, 'utf-8'))
        return NextResponse.json((data.items || []).slice(0, limit), {
          headers: {
            'X-Cache': 'hit',
            'X-Cache-Age': Math.round(age / 1000).toString(),
          },
        })
      } catch (e) { /* fall through */ }
    }
  }
  // 缓存缺失/过期, 提示用户跑 daily_live
  return NextResponse.json({
    error: 'ranking cache missing or stale, run: py -3.10 tools/build_ranking_cache.py',
    path: CACHE,
  }, { status: 503 })
}
