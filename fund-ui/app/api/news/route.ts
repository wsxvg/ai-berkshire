import { NextRequest, NextResponse } from 'next/server'
import path from 'path'
import fs from 'fs'
import { cachedJson } from '../_cache'

const ROOT = path.resolve(process.cwd(), '..')

async function loadNews(req?: NextRequest) {
  const asof = req?.nextUrl.searchParams.get('asof') // 可选: 截至日期 YYYY-MM-DD
  const lookback = parseInt(req?.nextUrl.searchParams.get('lookback') || '7', 10)

  // 1. 优先读按日期分目录的快照 (修复未来函数)
  const datedDir = path.join(ROOT, 'data', 'fund_cache', 'daily_news')
  if (fs.existsSync(datedDir)) {
    const files = fs.readdirSync(datedDir)
      .filter(f => f.endsWith('.json'))
      .map(f => ({ f, mtime: fs.statSync(path.join(datedDir, f)).mtimeMs, date: f.replace('.json', '') }))
      .sort((a, b) => b.mtime - a.mtime)

    if (files.length > 0) {
      if (asof) {
        // 历史回测模式: 只看 <= asof 的快照
        const fromDate = new Date(asof)
        fromDate.setDate(fromDate.getDate() - lookback)
        const valid = files.filter(f => {
          const d = new Date(f.date)
          return d >= fromDate && d <= new Date(asof)
        })
        const allItems: any[] = []
        for (const v of valid) {
          const data = JSON.parse(fs.readFileSync(path.join(datedDir, v.f), 'utf-8'))
          for (const it of (data.items || [])) {
            allItems.push({ ...it, _date: v.date })
          }
        }
        allItems.sort((a, b) => (b._date || '').localeCompare(a._date || ''))
        return {
          date: asof,
          items: allItems,
          source: `asof=${asof} (${valid.length} snapshots, lookback=${lookback})`,
          _asof: asof,
        }
      } else {
        // 默认模式: 最新一份
        const latest = files[0]
        const data = JSON.parse(fs.readFileSync(path.join(datedDir, latest.f), 'utf-8'))
        return { ...data, source: `dated/${latest.f}`, _cache_age: Math.round((Date.now() - latest.mtime) / 1000) }
      }
    }
  }

  // 2. fallback: 旧版 main.json
  const mainFile = path.join(ROOT, 'data', 'fund_cache', 'daily_news_main.json')
  if (fs.existsSync(mainFile)) {
    const data = JSON.parse(fs.readFileSync(mainFile, 'utf-8'))
    return { ...data, source: 'daily_news_main.json (legacy)' }
  }

  // 3. 无缓存
  return { date: '', items: [], error: 'no cache' }
}

export async function GET(req: NextRequest) {
  const asof = req.nextUrl.searchParams.get('asof')
  // 实时 (asof 不传) 用 5min cache, 历史 (asof 传了) 不用 cache
  if (asof) {
    return NextResponse.json(await loadNews(req))
  }
  return NextResponse.json(await cachedJson('news.json', 5 * 60 * 1000, () => loadNews())())
}
