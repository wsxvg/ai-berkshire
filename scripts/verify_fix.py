"""Verify: does longer holding period with expert consensus produce real alpha?"""
import json
import bisect
from collections import defaultdict

with open('backtest/data/trading_by_date_fixed.json') as f:
    trading_by_date = json.load(f)

with open('backtest/data/fund_charts.json') as f:
    fund_charts = json.load(f)

def get_nav_on_date(code, date_str):
    pts = fund_charts.get(code, [])
    if not pts:
        return None
    dates = [p.get('xAxis', '') for p in pts]
    idx = bisect.bisect_right(dates, date_str) - 1
    if idx < 0:
        return None
    return float(pts[idx].get('yAxis', 0)) / 100 + 1

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

# Check if backtest engine has fee support
print("=== CHECKING FOR FEE SUPPORT IN BACKTEST ENGINE ===")
with open('backtest/engine/backtest.py') as f:
    content = f.read()

# Search for transaction cost modeling
for term in ['purchase_fee', 'redeem_fee', 'transaction_cost', 'fee_rate', '手续费', '申购费', '赎回费']:
    count = content.count(term)
    if count > 0:
        print(f"  Found '{term}' {count} times")

# Find relevant sections
import re
for match in re.finditer(r'(fee|cost|手续费|申购|赎回).*?(?:\n\s*.*){0,3}', content, re.IGNORECASE):
    line_num = content[:match.start()].count('\n') + 1
    if line_num > 2700:  # We only care about main loop section
        continue
    text = match.group()[:100]
    if 'fee' in text.lower() or 'cost' in text.lower() or '购' in text or '赎' in text:
        if 'def ' not in text and 'import' not in text:
            # Only print if not in a function definition
            first_line = text.split('\n')[0]
            if len(first_line) < 80:
                print(f"  Line {line_num}: {first_line}")

print()
print("=== SCENARIO: Expert Consensus + Long Hold (No Mini-Take-Profit) ===")
print()

# Simulate: every 14 days, buy 3+ consensus funds, hold 14 days
# Take profit at 2.5% instead of 0.5%
TAKE_PROFIT = 2.5  # percent
MIN_HOLD = 14  # days
PURCHASE_FEE = 0.006
REDEEM_MED = 0.005

all_dates = sorted(trading_by_date.keys())
valid_dates = all_dates[60:-60]

trade_results = []
period_returns = []

for rebalance_idx, date in enumerate(valid_dates):
    # Every MIN_HOLD days
    if rebalance_idx % MIN_HOLD != 0:
        continue
    
    records = trading_by_date.get(date, [])
    fund_buys = defaultdict(int)
    fund_codes = {}
    for r in records:
        if '买入' in r.get('action', ''):
            fn = r.get('fund_name', '')
            fund_buys[fn] += 1
            fund_codes[fn] = r.get('fund_code', '')
    
    # 2+ experts for more signals (3+ is too rare at short rebalance)
    consensus = sorted(
        [(fn, cnt) for fn, cnt in fund_buys.items() if cnt >= 2],
        key=lambda x: -x[1]
    )[:5]
    
    period_pnl = 0.0
    n_trades = 0
    
    for fn, cnt in consensus:
        code = fund_codes[fn]
        if not code:
            continue
        
        nav_buy = get_nav_on_date(code, date)
        nav_sell = get_nav_n_days_after(code, date, MIN_HOLD)
        if nav_buy is None or nav_sell is None:
            continue
        
        gross_ret = (nav_sell - nav_buy) / nav_buy * 100
        total_cost = (PURCHASE_FEE + REDEEM_MED) * 100
        net_ret = gross_ret - total_cost
        
        # Only record if we held (no early take-profit)
        # Or if hit take-profit before MIN_HOLD, calculate actual hold
        # For simplicity: assume we hold full MIN_HOLD
        
        trade_results.append({
            'date': date,
            'code': code,
            'consensus': cnt,
            'gross': gross_ret,
            'net': net_ret,
        })
        
        period_pnl += net_ret
        n_trades += 1
    
    if n_trades > 0:
        period_returns.append(period_pnl / n_trades)

print(f"Total trades: {len(trade_results)}")
print(f"Rebalance periods: {len(period_returns)}")
print()

if trade_results:
    avg_gross = sum(t['gross'] for t in trade_results) / len(trade_results)
    avg_net = sum(t['net'] for t in trade_results) / len(trade_results)
    winners = sum(1 for t in trade_results if t['net'] > 0)
    
    print(f"Avg gross return: {avg_gross:+.3f}%")
    print(f"Avg total cost: {(PURCHASE_FEE+REDEEM_MED)*100:.2f}%")
    print(f"Avg net return: {avg_net:+.3f}%")
    print(f"Win rate: {winners/len(trade_results)*100:.1f}%")
    print()
    
    # Group by consensus level
    for level in [2, 3]:
        sub = [t for t in trade_results if t['consensus'] >= level]
        if sub:
            avg = sum(t['net'] for t in sub) / len(sub)
            wr = sum(1 for t in sub if t['net'] > 0) / len(sub)
            print(f"  {level}+ consensus: n={len(sub)}, avg={avg:+.3f}%, win={wr*100:.1f}%")

# Annualized return
if period_returns:
    avg_period_ret = sum(period_returns) / len(period_returns)
    periods_per_year = 365 / MIN_HOLD
    annual_approx = avg_period_ret * periods_per_year
    print()
    print(f"Approximate annualized return: {annual_approx:+.1f}%")
    print(f"  (= {avg_period_ret:+.3f}% per {MIN_HOLD}-day period × {periods_per_year:.0f} periods)")
