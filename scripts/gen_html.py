import json, os, sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))

# 输入：每日推送日志
p = PROJECT / "logs" / "daily_push_v3.json"
if not os.path.exists(p):
    print('not found:', p)
    raise SystemExit(0)

d = json.load(open(p, encoding='utf-8', errors='replace'))
h = d.get('my_holdings', {}).get('holdings', [])
total_amt = sum(x.get('amount_yuan', 0) for x in h)
total_profit = sum(x.get('amount_yuan', 0) * x.get('profit_rate', 0) / 100.0 for x in h)
avg_rate = sum(x.get('profit_rate', 0) for x in h) / len(h) if h else 0

rows = ''
for x in h:
    rate = x.get('profit_rate', 0)
    color = 'red' if rate < -10 else ('orange' if rate < 0 else 'green')
    advice = '止损候选 (>10%)' if rate < -10 else ('观望' if rate < -5 else ('持有' if rate < 0 else '止盈候选'))
    rows += '<tr><td>%s</td><td>%s</td><td>%.0f</td><td style=color:%s>%+.1f%%</td><td>%s</td></tr>' % (
        x.get('name',''), x.get('code',''), x.get('amount_yuan',0), color, rate, advice
    )

html = '''<!DOCTYPE html><html><head><meta charset=utf-8><title>我的基金持仓</title><style>body{font-family:Arial;max-width:900px;margin:30px auto;padding:20px}h1{color:#333}.summary{background:#f5f5f5;padding:15px;border-radius:8px;margin:20px 0}table{width:100%%;border-collapse:collapse}th,td{padding:8px 12px;border-bottom:1px solid #eee;text-align:left}th{background:#333;color:#fff}.red{color:#d32f2f;font-weight:bold}.green{color:#388e3c;font-weight:bold}.orange{color:#f57c00}.advice{background:#fff3e0;padding:15px;border-left:4px solid #ff9800;margin:20px 0}</style></head><body>'''
html += '<div class=summary><b>总市值:</b> ¥%.0f | <b>总盈亏:</b> %+.0f | <b>平均:</b> %+.1f%% | <b>持仓数:</b> %d</div>' % (
    total_amt, total_profit, avg_rate, len(h)
)
html += '<h1>📊 我的基金持仓</h1>'
html += '<table><tr><th>基金名</th><th>代码</th><th>金额(¥)</th><th>盈亏</th><th>建议</th></tr>' + rows + '</table>'
html += '</body></html>'

# 输出：fund-ui 静态资源目录
out = PROJECT / "fund-ui" / "public" / "my_holdings.html"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(html, encoding='utf-8')
print('HTML saved:', out)
