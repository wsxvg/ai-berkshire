import { NextResponse } from 'next/server'
import path from 'path'
import fs from 'fs'

const ROOT = path.resolve(process.cwd(), '..')

/**
 * 系统状态查询
 * GET /api/status
 *
 * 报告: 缓存新鲜度、数据完整性、API 端点健康度
 * 用途: 前端 "系统状态" 组件 + 运维调试
 */
interface StatusReport {
  ts: number
  uptime_hours: number
  data: {
    watchlist: { exists: boolean; funds: number; age_sec: number | null }
    ranking: { exists: boolean; items: number; age_sec: number | null }
    scores: { exists: boolean; items: number; age_sec: number | null }
    reports: { count: number; latest: string | null }
    memory: { count: number; size_kb: number }
    cache: { files: number; size_kb: number }
  }
  endpoints: Record<string, 'ok' | 'stale' | 'missing'>
  issues: string[]
}

const HOUR = 3600 * 1000
const START_TS = Date.now()

function statFile(p: string): { exists: boolean; mtime: number; size: number } {
  try {
    const s = fs.statSync(p)
    return { exists: true, mtime: s.mtimeMs, size: s.size }
  } catch {
    return { exists: false, mtime: 0, size: 0 }
  }
}

function listReports(): { count: number; latest: string | null } {
  try {
    const dir = path.join(ROOT, 'reports', 'sim')
    if (!fs.existsSync(dir)) return { count: 0, latest: null }
    const files = fs.readdirSync(dir).filter(f => f.endsWith('.json') && f.startsWith('2026')).sort().reverse()
    return { count: files.length, latest: files[0] || null }
  } catch {
    return { count: 0, latest: null }
  }
}

function listMemoryDir(): { count: number; size_kb: number } {
  try {
    const dir = path.join(ROOT, 'data', 'memory')
    if (!fs.existsSync(dir)) return { count: 0, size_kb: 0 }
    const files = fs.readdirSync(dir).filter(f => f.endsWith('.json'))
    const totalSize = files.reduce((s, f) => {
      try { return s + fs.statSync(path.join(dir, f)).size } catch { return s }
    }, 0)
    return { count: files.length, size_kb: Math.round(totalSize / 1024) }
  } catch {
    return { count: 0, size_kb: 0 }
  }
}

function listCacheDir(): { files: number; size_kb: number } {
  try {
    const dir = path.join(ROOT, 'data', 'api_cache')
    if (!fs.existsSync(dir)) return { files: 0, size_kb: 0 }
    const files = fs.readdirSync(dir).filter(f => f.endsWith('.json'))
    const totalSize = files.reduce((s, f) => {
      try { return s + fs.statSync(path.join(dir, f)).size } catch { return s }
    }, 0)
    return { files: files.length, size_kb: Math.round(totalSize / 1024) }
  } catch {
    return { files: 0, size_kb: 0 }
  }
}

export async function GET() {
  const issues: string[] = []

  // 数据文件状态
  const watchlist = statFile(path.join(ROOT, 'data', 'fund_cache', 'watchlist_mine.json'))
  const ranking = statFile(path.join(ROOT, 'data', 'cache', 'ranking.json'))
  const scores = statFile(path.join(ROOT, 'data', 'cache', 'scores.json'))
  const reports = listReports()
  const memory = listMemoryDir()
  const cache = listCacheDir()

  // 端点健康度判定
  const ONE_DAY = 24 * HOUR
  const endpoints: Record<string, 'ok' | 'stale' | 'missing'> = {
    fund: !watchlist.exists ? 'missing' : (Date.now() - watchlist.mtime < ONE_DAY ? 'ok' : 'stale'),
    ranking: !ranking.exists ? 'missing' : (Date.now() - ranking.mtime < ONE_DAY ? 'ok' : 'stale'),
    score: !scores.exists ? 'missing' : (Date.now() - scores.mtime < ONE_DAY ? 'ok' : 'stale'),
    report: reports.count === 0 ? 'missing' : 'ok',
    sector: statFile(path.join(ROOT, 'data', 'industry_valuation.json')).exists ? 'ok' : 'missing',
    news: (() => {
      const dir = path.join(ROOT, 'data', 'fund_cache', 'daily_news')
      return fs.existsSync(dir) && fs.readdirSync(dir).length > 0 ? 'ok' : 'missing'
    })(),
  }

  // 收集问题
  if (!watchlist.exists) issues.push('自选基金缓存缺失: data/fund_cache/watchlist_mine.json')
  if (!ranking.exists) issues.push('排行缓存缺失: data/cache/ranking.json (需运行 build_ranking_cache.py)')
  if (!scores.exists) issues.push('评分缓存缺失: data/cache/scores.json (需运行 build_score_cache.py)')
  if (watchlist.exists && Date.now() - watchlist.mtime > 7 * 24 * HOUR) {
    issues.push(`自选缓存过期 ${Math.round((Date.now() - watchlist.mtime) / 86400 / 1000)} 天`)
  }
  if (reports.count === 0) issues.push('无模拟盘日报 (需运行 daily_simulation.py)')

  const age = (m: number) => m ? Math.round((Date.now() - m) / 1000) : null

  const report: StatusReport = {
    ts: Date.now(),
    uptime_hours: Math.round((Date.now() - START_TS) / HOUR * 10) / 10,
    data: {
      watchlist: { exists: watchlist.exists, funds: 0, age_sec: age(watchlist.mtime) },
      ranking: { exists: ranking.exists, items: 0, age_sec: age(ranking.mtime) },
      scores: { exists: scores.exists, items: 0, age_sec: age(scores.mtime) },
      reports,
      memory,
      cache,
    },
    endpoints,
    issues,
  }

  // 读取 items 数量 (小开销)
  try {
    if (ranking.exists) {
      const d = JSON.parse(fs.readFileSync(path.join(ROOT, 'data', 'cache', 'ranking.json'), 'utf-8'))
      report.data.ranking.items = (d.items || []).length
    }
  } catch {}
  try {
    if (scores.exists) {
      const d = JSON.parse(fs.readFileSync(path.join(ROOT, 'data', 'cache', 'scores.json'), 'utf-8'))
      report.data.scores.items = (d.items || []).length
    }
  } catch {}
  try {
    if (watchlist.exists) {
      const d = JSON.parse(fs.readFileSync(path.join(ROOT, 'data', 'fund_cache', 'watchlist_mine.json'), 'utf-8'))
      report.data.watchlist.funds = (d.funds || []).length
    }
  } catch {}

  return NextResponse.json(report, {
    headers: { 'Cache-Control': 'no-store' }
  })
}
