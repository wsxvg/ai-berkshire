import json
from collections import Counter

m = json.load(open('backtest/data/stock_sector_map.json', 'r', encoding='utf-8'))
c = Counter(m.values())
print(f'总股票映射: {len(m)}')
for k, v in c.most_common():
    print(f'  {k:12s} {v:4d}')
print(f'\n所有行业值集合: {set(m.values())}')
