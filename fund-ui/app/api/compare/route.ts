import { NextRequest, NextResponse } from 'next/server'
import { exec } from 'child_process'
import path from 'path'
import fs from 'fs'

const ROOT = path.resolve(process.cwd(), '..')

function runPy(file: string): Promise<string> {
  return new Promise((resolve, reject) => {
    exec(`python "${file}"`, {
      cwd: ROOT, timeout: 20000, encoding: 'buffer',
      env: { ...process.env, PYTHONIOENCODING: 'utf-8' }
    }, (err, stdout, stderr) => {
      if (err) reject(new Error(stderr?.toString('utf-8') || err.message))
      else resolve(stdout.toString('utf-8'))
    })
  })
}

export async function GET(req: NextRequest) {
  const codes = req.nextUrl.searchParams.get('codes') || ''
  if (!codes) return NextResponse.json([])

  const tmp = path.join(ROOT, '_api_compare.py')
  try {
    fs.writeFileSync(tmp, `import json, sys; sys.path.insert(0, '.')
from pathlib import Path
fc = json.loads(Path('data/fund_charts.json').read_text('utf-8'))

codes = '${codes}'.split(',')
# 找到所有基金共同的时间范围
all_dates = set()
code_data = {}
for code in codes:
    code = code.strip()
    if code not in fc: continue
    pts = [(p['xAxis'][:10], float(p['yAxis'])) for p in fc[code][-90:]]
    code_data[code] = {d: v for d, v in pts}
    all_dates.update(d for d, v in pts)

dates = sorted(all_dates)
result = []
for d in dates:
    row = {'date': d}
    for code, cd in code_data.items():
        row[code] = round(cd.get(d, None) or 0, 2)
    result.append(row)
print(json.dumps(result, ensure_ascii=False))`, 'utf-8')
    const stdout = await runPy(tmp)
    fs.unlinkSync(tmp)
    return NextResponse.json(JSON.parse(stdout.trim()))
  } catch (e: any) {
    try { fs.unlinkSync(tmp) } catch {}
    return NextResponse.json([])
  }
}
