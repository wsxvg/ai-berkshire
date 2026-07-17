import json
from collections import Counter

with open('data/fund_name_map.json', 'r', encoding='utf-8') as f:
    name_map = json.load(f)

with open('backtest/data/trading_history_fixed.json', 'r', encoding='utf-8') as f:
    trades = json.load(f)

buy = Counter()
sell = Counter()
for t in trades:
    code = t.get('fundCode', '')
    if '买入' in str(t.get('transactionType', '')):
        buy[code] += 1
    else:
        sell[code] += 1

print('=== 大佬交易 TOP 20 基金 (8856条交易,2024-03~2026-07) ===')
for code, cnt in buy.most_common(20):
    name = name_map.get(code, '?')
    print(f'  {code:6s}  {name[:30]:30s}  买{cnt:3d} 卖{sell.get(code,0):3d}')

print()
print('=== 板块分布（按基金名猜） ===')
sectors = Counter()
for code, cnt in buy.items():
    name = name_map.get(code, '')
    if '科技' in name or '互联网' in name or '信息' in name or '创新' in name or 'TMT' in name or '数字' in name or '芯片' in name or '半导体' in name or '通信' in name or '电子' in name:
        sectors['科技/TMT'] += cnt
    elif '医药' in name or '医疗' in name or '健康' in name or '生物' in name:
        sectors['医药'] += cnt
    elif '消费' in name or '食品' in name or '白酒' in name:
        sectors['消费'] += cnt
    elif '新能源' in name or '光伏' in name or '锂电' in name or '碳中和' in name or '能源' in name or '新能' in name:
        sectors['新能源'] += cnt
    elif '军工' in name or '国防' in name:
        sectors['军工'] += cnt
    elif '金融' in name or '银行' in name or '证券' in name or '保险' in name:
        sectors['金融'] += cnt
    elif '港' in name or '恒生' in name or 'H股' in name:
        sectors['港股'] += cnt
    elif '美' in name or '纳指' in name or '标普' in name or '全球' in name or 'QDII' in name or '海外' in name or '纳斯达克' in name or '美元' in name:
        sectors['海外/QDII'] += cnt
    elif '沪深300' in name or '中证500' in name or '上证' in name or '指数' in name or '宽基' in name:
        sectors['宽基'] += cnt
    elif '红利' in name or '低波' in name or '价值' in name or '稳健' in name:
        sectors['红利/价值'] += cnt
    else:
        sectors['其他/混合'] += cnt
for s, c in sectors.most_common():
    print(f'  {s:15s}  {c:4d} 次买入信号  ({c/sum(sectors.values())*100:.1f}%)')
