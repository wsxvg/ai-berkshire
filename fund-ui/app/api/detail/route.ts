import { NextRequest, NextResponse } from 'next/server'
import { exec } from 'child_process'
import path from 'path'
import fs from 'fs'

const ROOT = path.resolve(process.cwd(), '..')

function runPy(file: string): Promise<string> {
  return new Promise((resolve, reject) => {
    exec(`python "${file}"`, {
      cwd: ROOT, timeout: 30000, encoding: 'buffer',
      env: { ...process.env, PYTHONIOENCODING: 'utf-8' }
    }, (err, stdout, stderr) => {
      if (err) reject(new Error(stderr?.toString('utf-8') || err.message))
      else resolve(stdout.toString('utf-8'))
    })
  })
}

export async function GET(req: NextRequest) {
  const code = req.nextUrl.searchParams.get('code') || ''
  if (!code) return NextResponse.json({ error: 'missing code' }, { status: 400 })

  const tmp = path.join(ROOT, '_api_detail.py')
  try {
    fs.writeFileSync(tmp, `import json, sys; sys.path.insert(0, '.')
from tools.jd_finance_api import get_fund_detail, get_fund_chart_data, _ensure_cookies
from datetime import datetime

c = _ensure_cookies(offline=True) or {}
code = '${code}'
detail = get_fund_detail(code, cookies=c) or {}
chart = get_fund_chart_data(code)
pts = chart.get('chart_points', []) if chart else []
# 只取最近 90 天
recent = pts[-90:] if len(pts) > 90 else pts

profile = detail.get('profile', {})
perf = detail.get('performance', {}).get('performance', [])
holdings = detail.get('holdings_distribution', {})

result = {
    'code': code,
    'name': profile.get('full_name', ''),
    'type': profile.get('fund_type', ''),
    'scale': profile.get('scale', ''),
    'risk': profile.get('risk_level', ''),
    'company': profile.get('manager_company', ''),
    'rating': profile.get('morningstar_rating', ''),
    'established': profile.get('established', ''),
    'chart': [{'date': p.get('xAxis','')[:10], 'value': float(p.get('yAxis',0))} for p in recent],
    'performance': [{'period': p.get('period',''), 'r': float(p.get('return',0)) if p.get('return') else None} for p in perf],
    'allocation': holdings.get('allocation', {}),
    'topStocks': holdings.get('top_stocks', []),
    'notices': detail.get('notices', []),
}
print(json.dumps(result, ensure_ascii=False))`, 'utf-8')
    const stdout = await runPy(tmp)
    fs.unlinkSync(tmp)
    return NextResponse.json(JSON.parse(stdout.trim()))
  } catch (e: any) {
    try { fs.unlinkSync(tmp) } catch { }
    return NextResponse.json({ error: e.message }, { status: 500 })
  }
}
