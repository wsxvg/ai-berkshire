import { NextRequest, NextResponse } from 'next/server'
import path from 'path'
import fs from 'fs'
import { cachedJson } from '../_cache'

const ROOT = path.resolve(process.cwd(), '..')
const CACHE_FILE = path.join(ROOT, 'data', 'fund_cache', 'watchlist_mine.json')
const NAME_MAP = path.join(ROOT, 'data', 'fund_name_map.json')

function readWatchlistCache() {
  if (!fs.existsSync(CACHE_FILE)) return null
  const stat = fs.statSync(CACHE_FILE)
  if (Date.now() - stat.mtimeMs > 24 * 60 * 60 * 1000) return null  // 24h 过期
  try {
    const raw = JSON.parse(fs.readFileSync(CACHE_FILE, 'utf-8'))
    const funds = raw.funds || []
    return funds.map((f: any) => ({
      code: f.fund_code || '',
      name: f.fund_name || '',
      nav: f.latest_nav || '',
      dayReturn: f.day_return,
      weekReturn: f.week_return,
      monthReturn: f.month_return,
      yearReturn: f.year_return,
      totalPnl: f.total_pnl_pct,
      fundType: f.fund_type || '',
    }))
  } catch { return null }
}

// 通用 GET (返回自选列表)
export const GET = cachedJson('fund.json', 30 * 60 * 1000, () => {
  const cached = readWatchlistCache()
  if (cached) return cached
  return []
})

/**
 * 自选基金 CRUD
 * POST /api/fund  body: { code, name? }  - 添加到自选
 * DELETE /api/fund  body: { code } | ?code=XXX  - 从自选移除
 */
export async function POST(req: NextRequest) {
  try {
    const body = await req.json().catch(() => ({}))
    const code = (body.code || '').toString().trim()
    const name = (body.name || '').toString().trim()

    if (!code) return NextResponse.json({ ok: false, error: 'missing code' }, { status: 400 })
    if (!/^\d{6}$/.test(code)) return NextResponse.json({ ok: false, error: 'invalid code (expect 6 digits)' }, { status: 400 })

    // 读现有自选
    if (!fs.existsSync(CACHE_FILE)) {
      // 初始化空
      fs.writeFileSync(CACHE_FILE, JSON.stringify({ funds: [] }, null, 2), 'utf-8')
    }
    const raw = JSON.parse(fs.readFileSync(CACHE_FILE, 'utf-8'))
    const funds: any[] = raw.funds || []
    if (funds.find((f: any) => f.fund_code === code)) {
      return NextResponse.json({ ok: true, already: true, code, total: funds.length })
    }

    // 自动补 name (从 name_map)
    let finalName = name
    if (!finalName && fs.existsSync(NAME_MAP)) {
      try {
        const nm = JSON.parse(fs.readFileSync(NAME_MAP, 'utf-8'))
        // 反向: code -> name
        for (const [n, c] of Object.entries(nm)) {
          if (c === code) { finalName = n; break }
        }
      } catch {}
    }

    funds.push({
      fund_code: code,
      fund_name: finalName || code,
      latest_nav: '0.0',
      day_return: 0, week_return: 0, month_return: 0, year_return: 0,
      total_pnl_pct: 0,
      fund_type: '',
      _added_at: new Date().toISOString(),
    })

    // 原子写入
    const tmp = CACHE_FILE + '.tmp'
    fs.writeFileSync(tmp, JSON.stringify({ funds }, null, 2), 'utf-8')
    fs.renameSync(tmp, CACHE_FILE)

    // 清除 API 缓存
    try { fs.unlinkSync(path.join(ROOT, 'data', 'api_cache', 'fund.json')) } catch {}

    return NextResponse.json({ ok: true, code, name: finalName, total: funds.length })
  } catch (e: any) {
    return NextResponse.json({ ok: false, error: e.message }, { status: 500 })
  }
}

export async function DELETE(req: NextRequest) {
  try {
    const url = new URL(req.url)
    let code = url.searchParams.get('code') || ''
    if (!code) {
      const body = await req.json().catch(() => ({}))
      code = (body.code || '').toString().trim()
    }
    if (!code) return NextResponse.json({ ok: false, error: 'missing code (use ?code=XXX or body)' }, { status: 400 })

    if (!fs.existsSync(CACHE_FILE)) {
      return NextResponse.json({ ok: true, removed: 0 })
    }
    const raw = JSON.parse(fs.readFileSync(CACHE_FILE, 'utf-8'))
    const funds: any[] = raw.funds || []
    const before = funds.length
    const filtered = funds.filter((f: any) => f.fund_code !== code)
    const removed = before - filtered.length

    if (removed === 0) {
      return NextResponse.json({ ok: true, removed: 0, code, hint: 'not in watchlist' })
    }

    const tmp = CACHE_FILE + '.tmp'
    fs.writeFileSync(tmp, JSON.stringify({ funds: filtered }, null, 2), 'utf-8')
    fs.renameSync(tmp, CACHE_FILE)

    // 清除 API 缓存
    try { fs.unlinkSync(path.join(ROOT, 'data', 'api_cache', 'fund.json')) } catch {}

    return NextResponse.json({ ok: true, removed, code, remaining: filtered.length })
  } catch (e: any) {
    return NextResponse.json({ ok: false, error: e.message }, { status: 500 })
  }
}
