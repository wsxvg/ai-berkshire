import { NextRequest, NextResponse } from 'next/server'
import path from 'path'
import fs from 'fs'

const ROOT = path.resolve(process.cwd(), '..')
const API_CACHE = path.join(ROOT, 'data', 'api_cache')

/**
 * 健康检查
 * GET /api/health
 *
 * 用途: 负载均衡 / K8s liveness probe / 监控告警
 * 返: 200 (ok) / 503 (degraded)
 */
export async function GET() {
  const checks: Record<string, { ok: boolean; latency_ms?: number; error?: string }> = {}

  // 1. 关键目录可写
  const t0 = Date.now()
  try {
    fs.mkdirSync(API_CACHE, { recursive: true })
    const test = path.join(API_CACHE, '.health_check')
    fs.writeFileSync(test, String(Date.now()))
    fs.unlinkSync(test)
    checks.fs = { ok: true, latency_ms: Date.now() - t0 }
  } catch (e: any) {
    checks.fs = { ok: false, error: e.message }
  }

  // 2. 关键数据文件可读
  for (const f of [
    'data/fund_cache/watchlist_mine.json',
    'data/cache/ranking.json',
    'data/cache/scores.json',
  ]) {
    const p = path.join(ROOT, f)
    const t = Date.now()
    try {
      fs.accessSync(p, fs.constants.R_OK)
      checks[f] = { ok: true, latency_ms: Date.now() - t }
    } catch (e: any) {
      checks[f] = { ok: false, error: e.message }
    }
  }

  // 3. Python 解释器可用
  const t1 = Date.now()
  try {
    const { execSync } = require('child_process')
    execSync('python --version', { timeout: 5000, stdio: 'ignore' })
    checks.python = { ok: true, latency_ms: Date.now() - t1 }
  } catch (e: any) {
    checks.python = { ok: false, error: 'python not in PATH' }
  }

  const allOk = Object.values(checks).every(c => c.ok)
  const report = {
    status: allOk ? 'ok' : 'degraded',
    ts: Date.now(),
    checks,
    degraded: Object.entries(checks).filter(([_, v]) => !v.ok).map(([k]) => k),
  }

  return NextResponse.json(report, {
    status: allOk ? 200 : 503,
    headers: { 'Cache-Control': 'no-store' }
  })
}
