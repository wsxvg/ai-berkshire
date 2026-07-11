import { NextRequest, NextResponse } from 'next/server'
import { exec } from 'child_process'
import path from 'path'
import fs from 'fs'

const ROOT = path.resolve(process.cwd(), '..')

function runPy(file: string, timeoutMs = 60000): Promise<string> {
  return new Promise((resolve, reject) => {
    exec(`python "${file}"`, {
      cwd: ROOT, timeout: timeoutMs, encoding: 'buffer',
      env: { ...process.env, PYTHONIOENCODING: 'utf-8' }
    }, (err, stdout, stderr) => {
      if (err) reject(new Error(stderr?.toString('utf-8') || err.message))
      else resolve(stdout.toString('utf-8'))
    })
  })
}

export async function GET(req: NextRequest) {
  // 数据源: queryFullRanking 端点 (京东金融)
  // 26 个榜单 (人气认证5 + 主题榜单12 + 业绩优秀9), 每榜 TOP20
  const tmp = path.join(ROOT, '_api_feat_rankings.py')
  try {
    fs.writeFileSync(tmp, `import json
from pathlib import Path
import sys
sys.path.insert(0, '.')
from tools.jd_finance_api import get_featured_rankings

# 读持仓方向缓存 (fund_type)
fund_types = {}
import glob
for f in glob.glob('data/fund_cache/fund_profile_*.json'):
    code = Path(f).stem.replace('fund_profile_', '', 1)
    try:
        d = json.loads(Path(f).read_text('utf-8'))
        fund_types[code] = d.get('fund_type', '') or d.get('fund_type_name', '') or ''
    except: pass

# 读 name_map (name -> code), 反向 code -> name
nm = json.loads(Path('data/fund_name_map.json').read_text('utf-8'))
code_to_name = {}
for n, c in nm.items():
    if c not in code_to_name: code_to_name[c] = n

# 拉真实数据
data = get_featured_rankings(use_cache=True, max_items=20)

# 给每只基金补 type/name
for code, b in data.get('boards', {}).items():
    for f in b.get('top20', []):
        fc = f.get('code')
        if fc and not f.get('name'):
            f['name'] = code_to_name.get(fc, '')
        f['type'] = fund_types.get(fc, '')

print(json.dumps(data, ensure_ascii=False))
`, 'utf-8')
    const stdout = await runPy(tmp)
    fs.unlinkSync(tmp)
    return NextResponse.json(JSON.parse(stdout.trim()))
  } catch (e: any) {
    try { fs.unlinkSync(tmp) } catch {}
    return NextResponse.json({ error: e.message }, { status: 500 })
  }
}
