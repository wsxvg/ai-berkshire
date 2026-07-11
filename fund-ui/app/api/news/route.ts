import { NextResponse } from 'next/server'
import path from 'path'
import fs from 'fs'
import { cachedJson } from '../_cache'

const ROOT = path.resolve(process.cwd(), '..')

async function loadNews() {
  // 1. 优先读最新缓存 (jd_finance_api.py 内部生成)
  const cacheDir = path.join(ROOT, 'data', 'fund_cache')
  const files = fs.readdirSync(cacheDir)
    .filter(f => f.startsWith('daily_news_') && f.endsWith('.json'))
    .map(f => ({ f, mtime: fs.statSync(path.join(cacheDir, f)).mtimeMs }))
    .sort((a, b) => b.mtime - a.mtime)
  if (files.length > 0) {
    const latest = files[0]
    const data = JSON.parse(fs.readFileSync(path.join(cacheDir, latest.f), 'utf-8'))
    return { ...data, source: latest.f, _cache_age: Math.round((Date.now() - latest.mtime) / 1000) }
  }
  // 2. fallback: 调 python (冷启动, 不阻塞主线程)
  return { date: '', items: [], error: 'no cache' }
}

export const GET = cachedJson('news.json', 5 * 60 * 1000, loadNews)
