import json
from collections import Counter

t = json.load(open('backtest/data/trading_history_fixed.json', 'r', encoding='utf-8'))
print('type:', type(t).__name__)
if isinstance(t, list):
    print('len:', len(t))
    print('keys[0]:', list(t[0].keys()) if t else 'empty')
    print('sample[0]:', t[0])
elif isinstance(t, dict):
    print('keys:', list(t.keys())[:5])
    k0 = list(t.keys())[0]
    print('first val type:', type(t[k0]).__name__)
    if isinstance(t[k0], list) and t[k0]:
        print('first rec keys:', list(t[k0][0].keys()))
        print('first rec:', t[k0][0])
    else:
        print('first val:', t[k0])
