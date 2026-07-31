"""Hypothesis: Expert + LOW momentum = higher alpha (mean reversion effect).
Test by comparing expert signal returns conditioned on momentum direction.
"""
import json, bisect
from collections import defaultdict

with open('backtest/data/trading_by_date_fixed.json') as f:
    trading_by_date = json.load(f)
with open('backtest/data/fund_charts.json') as f:
    fund_charts = json.load(f)

def get_nav_n_days(code, date, n):
    pts = fund_charts.get(code, [])
    if not pts: return None
    dates = [p['xAxis'] for p in pts]
    idx = bisect.bisect_right(dates, date) - 1
    if idx < 0: return None
    ti = idx + n
    if ti >= len(pts): return None
    return float(pts[ti]['yAxis'])/100+1

def get_nav(code, date):
    pts = fund_charts.get(code, [])
    if not pts: return None
    dates = [p['xAxis'] for p in pts]
    idx = bisect.bisect_right(dates, date) - 1
    if idx < 0: return None
    return float(pts[idx]['yAxis'])/100+1

all_dates = sorted(trading_by_date.keys())
valid = all_dates[30:-30]

# Categorize expert signals by momentum
data = defaultdict(list)  # (consensus, mom_dir) -> [ret_7d]

for date in valid:
    records = trading_by_date.get(date, [])
    fund_buys = defaultdict(int)
    fund_codes = {}
    for r in records:
        if '买入' in r.get('action',''):
            fn = r.get('fund_name','')
            fund_buys[fn] += 1
            fund_codes[fn] = r.get('fund_code','')
    for fn, cnt in fund_buys.items():
        code = fund_codes.get(fn, '')
        if not code: continue
        
        # Compute momentum (past 5-day return)
        nav_t0 = get_nav(code, date)
        nav_t5 = get_nav_n_days(code, date, -5)
        if nav_t0 is None or nav_t5 is None: continue
        
        mom = (nav_t0 - nav_t5) / nav_t5 * 100  # 5-day past return
        nav_t7 = get_nav_n_days(code, date, 7)
        if nav_t7 is None: continue
        
        ret_7d = (nav_t7 - nav_t0) / nav_t0 * 100
        
        # Convention: cnt >= 2 means "consensus"
        key = ('2+', 'pos_mom') if cnt >= 2 and mom > 0 else \
              ('2+', 'neg_mom') if cnt >= 2 and mom <= 0 else \
              ('1', 'pos_mom') if cnt == 1 and mom > 0 else \
              ('1', 'neg_mom')
        data[key].append(ret_7d)

print("EXPERT ALPHA BY MOMENTUM DIRECTION (7-day forward return):")
print()
print(f"{'Category':<20} {'n':>6} {'AvgRet':>8} {'Median':>8} {'Win%':>6} {'T-stat':>8}")
print("-" * 60)

import statistics
for key in [('2+','pos_mom'), ('2+','neg_mom'), ('1','pos_mom'), ('1','neg_mom')]:
    vals = data.get(key, [])
    if not vals: continue
    avg = sum(vals)/len(vals)
    med = statistics.median(vals)
    pos_pct = sum(1 for v in vals if v > 0)/len(vals)*100
    std = statistics.stdev(vals) if len(vals) > 1 else 0
    t = avg/(std/len(vals)**0.5) if std > 0 else 0
    name = f"{key[0]} exp, {key[1]}"
    print(f"{name:<20} {len(vals):>6} {avg:>+7.3f}% {med:>+7.3f}% {pos_pct:>5.1f}% {t:>+7.1f}")

print()
print("Key question: Do experts have HIGHER alpha when buying into NEGATIVE momentum (mean reversion)?")
print("If yes, momentum FILTER is HURTING returns.")
