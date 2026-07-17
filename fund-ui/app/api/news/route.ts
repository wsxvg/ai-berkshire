import { NextRequest, NextResponse } from 'next/server'
import path from 'path'
import fs from 'fs'
import { cachedJson } from '../_cache'

const ROOT = path.resolve(process.cwd(), '..')

const MAX_LOOKBACK = 90

async function loadNews(req?: NextRequest) {
  const asof = req?.nextUrl.searchParams.get('asof')
  const lookbackParam = parseInt(req?.nextUrl.searchParams.get('lookback') || '7', 10)
  const lookback = Math.max(1, Math.min(lookbackParam, MAX_LOOKBACK))

  // 1. 优先读按日期分目录的快照
  const datedDir = path.join(ROOT, 'data', 'fund_cache', 'daily_news')
  if (fs.existsSync(datedDir)) {
    const files = fs.readdirSync(datedDir)
      .filter(f => f.endsWith('.json'))
      .map(f => ({ f, mtime: fs.statSync(path.join(datedDir, f)).mtimeMs, date: f.replace('.json', '') }))
      .sort((a, b) => b.mtime - a.mtime)

    if (files.length > 0) {
      if (asof) {
        // 历史回测模式
        const asofDate = new Date(asof)
        if (isNaN(asofDate.getTime())) {
          return { error: 'invalid asof (expect YYYY-MM-DD)', items: [] }
        }
        const fromDate = new Date(asof)
        fromDate.setDate(fromDate.getDate() - lookback)
        const valid = files.filter(f => {
          const d = new Date(f.date)
          return d >= fromDate && d <= asofDate
        })
        const allItems: any[] = []
        for (const v of valid) {
          try {
            const data = JSON.parse(fs.readFileSync(path.join(datedDir, v.f), 'utf-8'))
            for (const it of (data.items || [])) {
              allItems.push({ ...it, _date: v.date })
            }
          } catch {}
        }
        allItems.sort((a, b) => (b._date || '').localeCompare(a._date || ''))
        return {
          date: asof,
          items: allItems,
          source: `asof=${asof} (${valid.length} snapshots, lookback=${lookback})`,
          _asof: asof,
          _lookback: lookback,
        }
      } else {
        // 默认模式
        const latest = files[0]
        try {
          const data = JSON.parse(fs.readFileSync(path.join(datedDir, latest.f), 'utf-8'))
          return {
            ...data,
            source: `dated/${latest.f}`,
            _cache_age: Math.round((Date.now() - latest.mtime) / 1000),
          }
        } catch (e: any) {
          return { error: 'parse latest failed: ' + e.message, items: [] }
        }
      }
    }
  }

  // 2. fallback: 旧版 main.json
  const mainFile = path.join(ROOT, 'data', 'fund_cache', 'daily_news_main.json')
  if (fs.existsSync(mainFile)) {
    try {
      const data = JSON.parse(fs.readFileSync(mainFile, 'utf-8'))
      return { ...data, source: 'daily_news_main.json (legacy)' }
    } catch (e: any) {
      return { error: 'parse main failed: ' + e.message, items: [] }
    }
  }

  // 3. 无缓存
  return {
    error: 'no news cache',
    hint: 'run: py -3.10 scripts/auto-pipeline.py (生成 daily_news/YYYY-MM-DD.json)',
    items: [],
  }
}

export async function GET(req: NextRequest) {
  const asof = req.nextUrl.searchParams.get('asof')
  if (asof) {
    // 历史回测: 不缓存 (每请求都不同)
    const data = await loadNews(req)
    if (data.error) {
      return NextResponse.json(data, { status: 503 })
    }
    return NextResponse.json(data, { headers: { 'X-Cache': 'bypass' } })
  }
  // 实时: 5min 缓存
  try {
    const data = await cachedJson('news.json', 5 * 60 * 1000, () => loadNews())()
    return NextResponse.json(data)
  } catch (e: any) {
    return NextResponse.json({ error: e.message, items: [] }, { status: 500 })
  }
}
