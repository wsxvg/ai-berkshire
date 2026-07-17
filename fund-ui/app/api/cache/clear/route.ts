import { NextRequest, NextResponse } from 'next/server'
import path from 'path'
import fs from 'fs'

const ROOT = path.resolve(process.cwd(), '..')
const API_CACHE_DIR = path.join(ROOT, 'data', 'api_cache')
const CACHE_FILES = ['fund.json', 'news.json', 'feed.json', 'compare.json', 'detail.json', 'status.json', 'ranking.json']

/**
 * 缓存管理
 * GET  /api/cache/clear           - 列出所有缓存
 * POST /api/cache/clear           - 清空 (body: {name?: string, all?: bool})
 * DELETE /api/cache/clear?name=X  - 删指定缓存
 */
export async function GET() {
  try {
    if (!fs.existsSync(API_CACHE_DIR)) {
      return NextResponse.json({ files: [], total_size_kb: 0 })
    }
    const files = fs.readdirSync(API_CACHE_DIR)
      .filter(f => f.endsWith('.json'))
      .map(f => {
        const p = path.join(API_CACHE_DIR, f)
        const s = fs.statSync(p)
        return {
          name: f,
          size_kb: Math.round(s.size / 1024),
          age_sec: Math.round((Date.now() - s.mtimeMs) / 1000),
          mtime: new Date(s.mtimeMs).toISOString(),
        }
      })
    const total = files.reduce((s, f) => s + f.size_kb, 0)
    return NextResponse.json({ files, total_size_kb: total })
  } catch (e: any) {
    return NextResponse.json({ error: e.message }, { status: 500 })
  }
}

export async function POST(req: NextRequest) {
  try {
    const body = await req.json().catch(() => ({}))
    const name = body.name
    const all = body.all === true

    if (!fs.existsSync(API_CACHE_DIR)) {
      return NextResponse.json({ ok: true, deleted: [] })
    }

    let deleted: string[] = []
    if (all) {
      for (const f of fs.readdirSync(API_CACHE_DIR).filter(f => f.endsWith('.json'))) {
        fs.unlinkSync(path.join(API_CACHE_DIR, f))
        deleted.push(f)
      }
    } else if (name) {
      // 允许清除预设白名单
      const target = CACHE_FILES.includes(name) ? name : name
      const p = path.join(API_CACHE_DIR, target)
      if (fs.existsSync(p)) {
        fs.unlinkSync(p)
        deleted.push(target)
      } else {
        return NextResponse.json({ ok: false, error: `cache file not found: ${name}` }, { status: 404 })
      }
    } else {
      return NextResponse.json({ ok: false, error: 'missing name or all=true' }, { status: 400 })
    }

    return NextResponse.json({ ok: true, deleted, ts: Date.now() })
  } catch (e: any) {
    return NextResponse.json({ ok: false, error: e.message }, { status: 500 })
  }
}

export async function DELETE(req: NextRequest) {
  const name = req.nextUrl.searchParams.get('name')
  if (!name) return NextResponse.json({ ok: false, error: 'missing ?name=' }, { status: 400 })
  const p = path.join(API_CACHE_DIR, name)
  if (!fs.existsSync(p)) return NextResponse.json({ ok: false, error: 'not found' }, { status: 404 })
  fs.unlinkSync(p)
  return NextResponse.json({ ok: true, deleted: name, ts: Date.now() })
}
