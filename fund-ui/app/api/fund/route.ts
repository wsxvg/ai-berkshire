import { NextResponse } from 'next/server'
import path from 'path'
import fs from 'fs'
import { cachedJson } from '../_cache'

const ROOT = path.resolve(process.cwd(), '..')
const CACHE_FILE = path.join(ROOT, 'data', 'fund_cache', 'watchlist_mine.json')

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

export const GET = cachedJson('fund.json', 30 * 60 * 1000, () => {
  const cached = readWatchlistCache()
  if (cached) return cached
  // 缓存缺失时仍返回空数组, 而不是 error 对象, 避免前端 funds.map 崩溃
  return []
})
