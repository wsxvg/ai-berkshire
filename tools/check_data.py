import json
import os
w = json.load(open(r'c:\项目\A基金\基金\data\watchlist.json', 'r', encoding='utf-8'))
print('watchlist type:', type(w).__name__, 'len:', len(w) if isinstance(w, list) else 'N/A')
if isinstance(w, list):
    for x in w[:5]:
        print('  ', x)
elif isinstance(w, dict):
    for k, v in list(w.items())[:5]:
        print('  ', k, '→', str(v)[:80])

# 看看 holdings_snapshot
if os.path.exists(r'c:\项目\A基金\基金\data\holdings_snapshot.json'):
    hs = json.load(open(r'c:\项目\A基金\基金\data\holdings_snapshot.json', 'r', encoding='utf-8'))
    print('\nholdings_snapshot type:', type(hs).__name__)
    if isinstance(hs, dict) and 'holdings' in hs:
        print('  users:', list(hs['holdings'].keys())[:5])
        for user, funds in list(hs['holdings'].items())[:2]:
            print(f'  {user}: {len(funds) if isinstance(funds, list) else "?"} 基金')
            for f in (funds if isinstance(funds, list) else [])[:3]:
                print(f'    {f.get("code", "?")} {f.get("name", "?")} profit={f.get("profit_rate", "?")}')

# 看看 fund_holdings 缓存里有没有 top_stocks
if os.path.exists(r'c:\项目\A基金\基金\data\fund_cache\fund_holdings_002112_latest.json'):
    fh = json.load(open(r'c:\项目\A基金\基金\data\fund_cache\fund_holdings_002112_latest.json', 'r', encoding='utf-8'))
    print('\nfund_holdings 002112 字段:', list(fh.keys()))
    print('  top_stocks 数量:', len(fh.get('top_stocks', [])))
    if fh.get('top_stocks'):
        for s in fh['top_stocks'][:3]:
            print(f'    {s.get("name", "?")}({s.get("code", "?")}) {s.get("ratio", "?")}')
