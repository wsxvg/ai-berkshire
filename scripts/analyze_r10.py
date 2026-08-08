#!/usr/bin/env python3
"""Aggregate and analyze R10 OOS results."""
import json, os
from collections import defaultdict

results = []
for f in sorted(os.listdir('.')):
    if f.startswith('strict_test_ci') and f.endswith('.json'):
        with open(f) as fh:
            results.append(json.load(fh))

print(f'R10 OOS Evaluation ({len(results)} windows)')
print('=' * 80)

by_cand = defaultdict(list)
for r in results:
    by_cand[r['candidate']].append(r)

summary = {}
for name, items in by_cand.items():
    avg = sum(i['return'] for i in items) / len(items)
    avg_b = sum(i['benchmark'] for i in items) / len(items)
    beats = sum(1 for i in items if i['return'] > i['benchmark'])
    avg_dd = sum(i['max_dd'] for i in items) / len(items)
    avg_trades = sum(i['trades'] for i in items) / len(items)
    avg_fees = sum(i['fees'] for i in items) / len(items)
    summary[name] = {
        'avg': avg, 'bench': avg_b, 'beats': beats, 'total': len(items),
        'maxdd': avg_dd, 'trades': avg_trades, 'fees': avg_fees, 'items': items
    }

ranked = sorted(summary.items(), key=lambda x: -x[1]['avg'])
base_avg = summary.get('R4_BASELINE', {}).get('avg', 0)

print()
for rank, (name, s) in enumerate(ranked, 1):
    marker = ' <-- BEST' if rank == 1 else ''
    diff = s['avg'] - base_avg
    vs_base = ' (%.3f vs BASE)' % diff if name != 'R4_BASELINE' else ''
    print('%d. %-20s avg=%.3f%% bench=%.3f%% beats=%d/%d maxdd=%.2f trades=%.0f fees=%.2f%s%s' % (
        rank, name, s['avg'], s['bench'], s['beats'], s['total'], s['maxdd'], s['trades'], s['fees'], vs_base, marker))

# Detail by window
print()
print('Window-by-window (avg return across all candidates):')
by_wi = defaultdict(list)
for r in results:
    by_wi[r['wi']].append(r)
for wi in sorted(by_wi.keys()):
    items = by_wi[wi]
    avg = sum(i['return'] for i in items) / len(items)
    avg_b = sum(i['benchmark'] for i in items) / len(items)
    period = items[0]['period']
    print('  wi=%2d (%s): strat=%.2f%% bench=%.2f%% excess=%.2f%%' % (wi, period, avg, avg_b, avg - avg_b))

# Per-candidate detail
print()
print('Per-candidate detail (all windows):')
for name in ['R4_BASELINE', 'DYN_AGGRESSIVE', 'DYN_DEFENSIVE', 'DYN_MOMENTUM', 'DYN_TREND']:
    if name not in summary:
        continue
    s = summary[name]
    print()
    print('--- %s (avg=%.3f%%) ---' % (name, s['avg']))
    for it in sorted(s['items'], key=lambda x: x['wi']):
        marker = ' *WIN*' if it['return'] > it['benchmark'] else ''
        print('  wi=%2d %s: return=%.2f%% bench=%.2f%% dd=%.2f trades=%d fees=%.2f%s' % (
            it['wi'], it['period'], it['return'], it['benchmark'], it['max_dd'], it['trades'], it['fees'], marker))

# Save summary as JSON
eval_result = {
    'round': 10,
    'note': 'OOS EVALUATION - OUT-OF-SAMPLE, NO CHEATING, 74 windows (Wi=13 of CI=4 missing)',
    'summary': {name: {k: v for k, v in s.items() if k != 'items'} for name, s in summary.items()},
    'baseline': 'R4_BASELINE',
    'baseline_avg': base_avg,
    'best_candidate': ranked[0][0],
    'best_avg': ranked[0][1]['avg'],
    'improvement_vs_baseline': ranked[0][1]['avg'] - base_avg,
}
with open('v9-results/strict_oos_r10_eval.json', 'w') as f:
    json.dump(eval_result, f, ensure_ascii=False, indent=2)
print()
print('Saved: v9-results/strict_oos_r10_eval.json')
