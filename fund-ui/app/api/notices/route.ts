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
  const codes = (req.nextUrl.searchParams.get('codes') || '').split(',').filter(Boolean)
  if (!codes.length) return NextResponse.json([])

  const tmp = path.join(ROOT, '_api_notices.py')
  try {
    fs.writeFileSync(tmp, `import json, sys
from pathlib import Path
sys.path.insert(0, '.')
from tools.jd_finance_api import get_fund_notices, _ensure_cookies

c = _ensure_cookies(offline=True)
codes = ${JSON.stringify(codes)}
results = []
for code in codes:
    try:
        n = get_fund_notices(code, cookies=c, use_cache=True)
        notices = n.get('notices', [])
        if notices:
            # 只看最近的 + 关键类型 (限购/分红/清盘)
            keywords = ['限购', '分红', '清盘', '转换', '合并', '份额', '费率']
            for nb in notices[:5]:
                title = nb.get('title', '')
                is_critical = any(kw in title for kw in keywords)
                results.append({
                    'code': code,
                    'date': nb.get('date', ''),
                    'title': title,
                    'url': nb.get('url', ''),
                    'type': nb.get('type', ''),
                    'is_critical': is_critical,
                })
    except Exception as e:
        pass
print(json.dumps(results, ensure_ascii=False))`, 'utf-8')
    const stdout = await runPy(tmp)
    fs.unlinkSync(tmp)
    return NextResponse.json(JSON.parse(stdout.trim()))
  } catch (e: any) {
    try { fs.unlinkSync(tmp) } catch {}
    return NextResponse.json({ error: e.message }, { status: 500 })
  }
}
