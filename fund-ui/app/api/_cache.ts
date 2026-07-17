/**
 * 通用文件级 API 响应缓存工具
 *
 * 用法:
 *   import { cachedJson } from '../_cache'
 *   export const GET = cachedJson('news.json', 5*60*1000, async () => { ... })
 *
 * 增强 (v2):
 * - 每个文件大小限制 50MB
 * - 缓存目录总大小 200MB 上限
 * - 写入失败回退到内存缓存
 * - clearCache 支持批量清理
 */

import { NextRequest, NextResponse } from 'next/server'
import path from 'path'
import fs from 'fs'

const CACHE_DIR = path.resolve(process.cwd(), '..', 'data', 'api_cache')
const MAX_FILE_SIZE = 50 * 1024 * 1024  // 50MB
const MAX_TOTAL_SIZE = 200 * 1024 * 1024  // 200MB

// 进程内内存缓存
const memCache = new Map<string, { data: any; ts: number; maxAge: number }>()

function ensureDir() {
  if (!fs.existsSync(CACHE_DIR)) {
    fs.mkdirSync(CACHE_DIR, { recursive: true })
  }
}

function getTotalCacheSize(): number {
  try {
    return fs.readdirSync(CACHE_DIR)
      .filter(f => f.endsWith('.json'))
      .reduce((s, f) => {
        try { return s + fs.statSync(path.join(CACHE_DIR, f)).size } catch { return s }
      }, 0)
  } catch { return 0 }
}

function evictIfNeeded() {
  try {
    if (getTotalCacheSize() <= MAX_TOTAL_SIZE) return
    // 按 mtime 升序, 删最老的直到 < 80% 上限
    const files = fs.readdirSync(CACHE_DIR)
      .filter(f => f.endsWith('.json'))
      .map(f => ({ f, mtime: fs.statSync(path.join(CACHE_DIR, f)).mtimeMs }))
      .sort((a, b) => a.mtime - b.mtime)
    let total = getTotalCacheSize()
    for (const { f } of files) {
      if (total <= MAX_TOTAL_SIZE * 0.8) break
      const p = path.join(CACHE_DIR, f)
      const size = fs.statSync(p).size
      fs.unlinkSync(p)
      total -= size
    }
  } catch {}
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
      try {
        const stat = fs.statSync(file)
        if (now - stat.mtimeMs < maxAgeMs && stat.size < MAX_FILE_SIZE) {
          const data = JSON.parse(fs.readFileSync(file, 'utf-8'))
          memCache.set(name, { data, ts: stat.mtimeMs, maxAge: maxAgeMs })
          return NextResponse.json(data, {
            headers: { 'X-Cache': 'file', 'X-Cache-Age': Math.round((now - stat.mtimeMs) / 1000).toString() }
          })
        }
      } catch { /* fall through */ }
    }
    // 3. 加载
    try {
      const data = await loader()
      memCache.set(name, { data, ts: now, maxAge: maxAgeMs })
      // 异步写盘 (不阻塞响应)
      setTimeout(() => {
        try {
          evictIfNeeded()
          const json = JSON.stringify(data)
          if (json.length < MAX_FILE_SIZE) {
            const tmp = file + '.tmp'
            fs.writeFileSync(tmp, json, 'utf-8')
            fs.renameSync(tmp, file)
          }
        } catch (e) {
          // 写盘失败只记录, 不影响内存缓存
          console.warn(`[cache] write ${name} failed:`, (e as Error).message)
        }
      }, 0)
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
        if (f.endsWith('.json')) {
          try { fs.unlinkSync(path.join(CACHE_DIR, f)) } catch {}
        }
      }
    }
  }
}

/**
 * 获取缓存统计
 */
export function getCacheStats() {
  try {
    if (!fs.existsSync(CACHE_DIR)) return { files: 0, total_size: 0, mem_entries: memCache.size }
    const files = fs.readdirSync(CACHE_DIR).filter(f => f.endsWith('.json'))
    const total = files.reduce((s, f) => {
      try { return s + fs.statSync(path.join(CACHE_DIR, f)).size } catch { return s }
    }, 0)
    return { files: files.length, total_size: total, mem_entries: memCache.size }
  } catch {
    return { files: 0, total_size: 0, mem_entries: memCache.size }
  }
}
