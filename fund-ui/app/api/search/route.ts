import { NextRequest, NextResponse } from 'next/server'
import { exec } from 'child_process'
import path from 'path'
import fs from 'fs'

const ROOT = path.resolve(process.cwd(), '..')

function runPy(file: string): Promise<string> {
  return new Promise((resolve, reject) => {
    exec(`python "${file}"`, {
      cwd: ROOT, timeout: 15000, encoding: 'buffer',
      env: { ...process.env, PYTHONIOENCODING: 'utf-8' }
    }, (err, stdout, stderr) => {
      if (err) reject(new Error(stderr?.toString('utf-8') || err.message))
      else resolve(stdout.toString('utf-8'))
    })
  })
}

export async function GET(req: NextRequest) {
  const q = req.nextUrl.searchParams.get('q') || ''
  if (!q || q.length < 2) return NextResponse.json([])

  const tmp = path.join(ROOT, '_api_search.py')
  try {
    fs.writeFileSync(tmp, `import json, sys; sys.path.insert(0, '.')
from tools.jd_finance_api import _api_form, _ensure_cookies
c = _ensure_cookies(offline=True) or {}
import urllib.parse
# 直接用京东搜索建议接口
data = _api_form('gw/generic/base/h5/m/getSearchResultCompletionWord',
    {'keyword': '${q}'}, cookies=c)
rd = data.get('resultData', {}).get('datas', {})
items = rd.get('fundItemList', []) or rd.get('wordList', [])
results = []
for item in items[:10]:
    results.append({
        'code': item.get('code', item.get('fundCode', '')),
        'name': item.get('name', item.get('fundName', item.get('word', ''))),
        'type': item.get('fundType', ''),
    })
print(json.dumps(results, ensure_ascii=False))`, 'utf-8')
    const stdout = await runPy(tmp)
    fs.unlinkSync(tmp)
    const data = JSON.parse(stdout.trim())
    return NextResponse.json(data)
  } catch (e: any) {
    try { fs.unlinkSync(tmp) } catch {}
    return NextResponse.json([])
  }
}
