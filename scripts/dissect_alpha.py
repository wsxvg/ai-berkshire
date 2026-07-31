"""Dissect WHERE the alpha comes from - does consensus filter kill it?"""
import json
import bisect
from collections import defaultdict
import statistics

with open('backtest/data/trading_by_date_fixed.json') as f:
    trading_by_date = json.load(f)

with open('backtest/data/fund_charts.json') as f:
    fund_charts = json.load(f)

def get_nav_n_days_after(code, date_str, n):
    pts = fund_charts.get(code, [])
    if not pts:
        return None
    dates = [p.get('xAxis', '') for p in pts]
    idx = bisect.bisect_right(dates, date_str) - 1
    if idx < 0:
        return None
    target_idx = idx + n
    if target_idx >= len(pts):
        return None
    return float(pts[target_idx].get('yAxis', 0)) / 100 + 1

def get_nav_on_date(code, date_str):
    pts = fund_charts.get(code, [])
    if not pts:
        return None
    dates = [p.get('xAxis', '') for p in pts]
    idx = bisect.bisect_right(dates, date_str) - 1
    if idx < 0:
        return None
    return float(pts[idx].get('yAxis', 0)) / 100 + 1

all_dates = sorted(trading_by_date.keys())
valid_dates = all_dates[30:-30]

# Per date, count experts buying each fund
consensus_returns = defaultdict(list)  # consensus_level -> [returns]

for date in valid_dates:
    records = trading_by_date.get(date, [])
    # Group by fund
    fund_buys = defaultdict(int)
    fund_codes = {}
    for r in records:
        if '买入' in r.get('action', ''):
            fn = r.get('fund_name', '')
            fund_buys[fn] += 1
            fund_codes[fn] = r.get('fund_code', '')
    
    # For each fund, calculate forward return based on how many experts bought
    for fn, count in fund_buys.items():
        code = fund_codes[fn]
        nav_t0 = get_nav_on_date(code, date)
        nav_t7 = get_nav_n_days_after(code, date, 7)
        if nav_t0 and nav_t7:
            ret = (nav_t7 - nav_t0) / nav_t0 * 100
            # Group by consensus level
            if count >= 1:
                consensus_returns[1].append(ret)
            if count >= 2:
                consensus_returns[2].append(ret)
            if count >= 3:
                consensus_returns[3].append(ret)
            if count >= 5:
                consensus_returns[5].append(ret)

print("=" * 70)
print("ALPHA DISSECTION: Does consensus requirement filter out alpha?")
print("=" * 70)
print()
print("Average 7-day forward return by expert consensus level:")
print()

for level in [1, 2, 3, 5]:
    rets = consensus_returns.get(level, [])
    if not rets:
        print(f"  {level}+ experts: No data")
        continue
    avg = sum(rets) / len(rets)
    med = statistics.median(rets)
    pos = sum(1 for r in rets if r > 0) / len(rets) * 100
    std = statistics.stdev(rets) if len(rets) > 1 else 0
    t_stat = avg / (std / len(rets)**0.5) if std > 0 else 0
    print(f"  {level}+ experts buying same fund: n={len(rets)}, avg={avg:+.3f}%, median={med:+.3f}%")
    print(f"       positive={pos:.1f}%, std={std:.3f}%, t-stat={t_stat:+.1f}")

print()
print("Interpretation:")
print("  If level 1 has highest per-trade alpha → single-expert signals work")
print("  If level 3 is best → consensus filter is working correctly")
print("  If level 5 has lowest → massive consensus means overbought/popular funds")

# Also check: by SIGNAL SIZE (amount traded)
print()
print("=" * 70)
print("ALPHA BY SIZE: Small vs large trades")
print("=" * 70)
size_returns = defaultdict(list)

for date in valid_dates[:100]:  # Sample first 100 days
    records = trading_by_date.get(date, [])
    for r in records:
        if '买入' not in r.get('action', ''):
            continue
        fn = r.get('fund_name', '')
        code = r.get('fund_code', '')
        if not code:
            continue
        nav_t0 = get_nav_on_date(code, date)
        nav_t7 = get_nav_n_days_after(code, date, 7)
        if nav_t0 is None or nav_t7 is None:
            continue
        ret = (nav_t7 - nav_t0) / nav_t0 * 100
        
        # Parse amount
        amount_str = r.get('amount', '0').replace('元', '').replace(',', '')
        try:
            amount = float(amount_str)
        except:
            amount = 0
        
        if amount >= 10000:
            size_returns['large'].append(ret)
        else:
            size_returns['small'].append(ret)

for key, label in [('small', '<10000'), ('large', '>=10000')]:
    rets = size_returns.get(key, [])
    if rets:
        avg = sum(rets) / len(rets)
        pos = sum(1 for r in rets if r > 0) / len(rets) * 100
        print(f"  {label}: n={len(rets)}, avg={avg:+.3f}%, positive={pos:.1f}%")

# Check how often 3+ experts agree vs 1 expert
print()
print("=" * 70)
print("SIGNAL FREQUENCY: How often do we get consensus signals?")
print("=" * 70)
freq = defaultdict(int)
total_days_with_signals = 0
for date in valid_dates:
    records = trading_by_date.get(date, [])
    fund_buys = defaultdict(int)
    for r in records:
        if '买入' in r.get('action', ''):
            fund_buys[r.get('fund_name', '')] += 1
    if fund_buys:
        total_days_with_signals += 1
        for fn, count in fund_buys.items():
            if count >= 1:
                freq['1+'] += 1
            if count >= 2:
                freq['2+'] += 1
            if count >= 3:
                freq['3+'] += 1

print(f"  Days with any signals: {total_days_with_signals} / {len(valid_dates)}")
print(f"  Signals at 1+ experts: {freq.get('1+', 0)}")
print(f"  Signals at 2+ experts: {freq.get('2+', 0)}")
print(f"  Signals at 3+ experts: {freq.get('3+', 0)}")
print()
print(f"  Signals lost by requiring 3+: {freq.get('1+', 0) - freq.get('3+', 0)}")
