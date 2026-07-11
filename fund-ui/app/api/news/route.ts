import { NextResponse } from 'next/server'
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

export async function GET() {
  const tmp = path.join(ROOT, '_api_news.py')
  try {
    fs.writeFileSync(tmp, `import json, sys
from pathlib import Path
sys.path.insert(0, '.')
from tools.jd_finance_api import get_daily_news, _ensure_cookies
try:
    c = _ensure_cookies(offline=True)
    news = get_daily_news(cookies=c, use_cache=True)
    print(json.dumps(news, ensure_ascii=False))
except Exception as e:
    print(json.dumps({"date": "", "items": [], "error": str(e)}, ensure_ascii=False))`, 'utf-8')
    const stdout = await runPy(tmp)
    fs.unlinkSync(tmp)
    return NextResponse.json(JSON.parse(stdout.trim()))
  } catch (e: any) {
    try { fs.unlinkSync(tmp) } catch {}
    return NextResponse.json({ date: '', items: [], error: e.message }, { status: 500 })
  }
}
