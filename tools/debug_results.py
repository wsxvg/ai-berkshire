import json
r = json.load(open('data/long_term_backtest_results.json', 'r', encoding='utf-8'))
print('type:', type(r).__name__)
if isinstance(r, list):
    print('len:', len(r))
    print('first 2:')
    for x in r[:2]:
        print(json.dumps(x, ensure_ascii=False, indent=2))
