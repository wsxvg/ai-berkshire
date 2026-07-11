/**
 * 通用文件级 API 响应缓存工具
 *
 * 用法:
 *   import { cachedJson } from '../_cache'
 *   export const GET = cachedJson('news.json', 5*60*1000, async () => { ... })
 *
 * 优势:
 * - 不 spawn python 子进程 (省 0.3-1s/页)
 * - 不重新计算 (省 CPU)
 * - 同一进程内内存缓存 (省 IO)
 */

import { NextRequest, NextResponse } from 'next/server'
import path from 'path'
import fs from 'fs'

const CACHE_DIR = path.resolve(process.cwd(), '..', 'data', 'api_cache')

// 进程内内存缓存
const memCache = new Map<string, { data: any; ts: number; maxAge: number }>()

function ensureDir() {
  if (!fs.existsSync(CACHE_DIR)) {
    fs.mkdirSync(CACHE_DIR, { recursive: true })
  }
}

export function cachedJson<T>(
  name: string,
  maxAgeMs: number,
  loader: () => Promise<T> | T,
) {
  return async (req?: NextRequest) => {
    ensureDir()
    const now = Date.now()
    // 1. 内存缓存
    const mem = memCache.get(name)
    if (mem && now - mem.ts < mem.maxAge) {
      return NextResponse.json(mem.data, {
        headers: { 'X-Cache': 'memory', 'X-Cache-Age': Math.round((now - mem.ts) / 1000).toString() }
      })
    }
    // 2. 磁盘缓存
    const file = path.join(CACHE_DIR, name)
    if (fs.existsSync(file)) {
      const stat = fs.statSync(file)
      if (now - stat.mtimeMs < maxAgeMs) {
        try {
          const data = JSON.parse(fs.readFileSync(file, 'utf-8'))
          memCache.set(name, { data, ts: stat.mtimeMs, maxAge: maxAgeMs })
          return NextResponse.json(data, {
            headers: { 'X-Cache': 'file', 'X-Cache-Age': Math.round((now - stat.mtimeMs) / 1000).toString() }
          })
        } catch { /* fall through */ }
      }
    }
    // 3. 加载
    try {
      const data = await loader()
      memCache.set(name, { data, ts: now, maxAge: maxAgeMs })
      fs.writeFileSync(file, JSON.stringify(data), 'utf-8')
      return NextResponse.json(data, {
        headers: { 'X-Cache': 'miss', 'X-Cache-Age': '0' }
      })
    } catch (e: any) {
      return NextResponse.json({ error: e.message }, { status: 500 })
    }
  }
}

export function clearCache(name?: string) {
  if (name) {
    memCache.delete(name)
    const file = path.join(CACHE_DIR, name)
    if (fs.existsSync(file)) fs.unlinkSync(file)
  } else {
    memCache.clear()
    if (fs.existsSync(CACHE_DIR)) {
      for (const f of fs.readdirSync(CACHE_DIR)) {
        fs.unlinkSync(path.join(CACHE_DIR, f))
      }
    }
  }
}
