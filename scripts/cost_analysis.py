"""Analyze if transaction costs kill the alpha."""
import json
import bisect
from collections import defaultdict

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

# Standard mutual fund costs (China)
PURCHASE_FEE_RATE = 0.006  # 0.6% typical (after online discount)
REDEEM_FEE_SHORT = 0.015   # 1.5% penalty if redeemed within 7 days
REDEEM_FEE_MED = 0.005     # 0.5% after 7 days but < 1 year
REDEEM_FEE_LONG = 0.0      # 0% after 1 year+

all_dates = sorted(trading_by_date.keys())
valid_dates = all_dates[30:-30]

# Simulate different holding periods
holding_results = defaultdict(list)
rebalance_days_options = [1, 3, 7, 14, 21, 30]

for rebalance_days in rebalance_days_options:
    portfolio_return = 0.0
    n_trades = 0
    
    for date in valid_dates[::rebalance_days]:  # Every rebalance_days
        records = trading_by_date.get(date, [])
        fund_buys = defaultdict(int)
        fund_codes = {}
        for r in records:
            if '买入' in r.get('action', ''):
                fn = r.get('fund_name', '')
                fund_buys[fn] += 1
                fund_codes[fn] = r.get('fund_code', '')
        
        # Get 3+ consensus funds
        consensus_funds = [(fn, count) for fn, count in fund_buys.items() if count >= 3]
        consensus_funds.sort(key=lambda x: -x[1])
        
        if not consensus_funds:
            continue
        
        # Take top 5 (max_holdings)
        for fn, count in consensus_funds[:5]:
            code = fund_codes[fn]
            if not code:
                continue
            nav_buy = get_nav_on_date(code, date)
            nav_sell = get_nav_n_days_after(code, date, rebalance_days)
            if nav_buy is None or nav_sell is None:
                continue
            
            gross_return = (nav_sell - nav_buy) / nav_buy
            
            # Transaction costs
            purchase_fee = PURCHASE_FEE_RATE * 1.0  # applied to buy amount
            if rebalance_days <= 7:
                redeem_fee = REDEEM_FEE_SHORT
            elif rebalance_days <= 365:
                redeem_fee = REDEEM_FEE_MED
            else:
                redeem_fee = REDEEM_FEE_LONG
            
            net_return = gross_return - purchase_fee - redeem_fee
            holding_results[rebalance_days].append(net_return * 100)
            n_trades += 1

print("=" * 70)
print("TRANSACTION COST IMPACT ON ALPHA")
print("=" * 70)
print(f"Assumptions: Purchase fee={PURCHASE_FEE_RATE*100:.1f}%, Short-term redeem={REDEEM_FEE_SHORT*100:.1f}%, Medium-term={REDEEM_FEE_MED*100:.1f}%")
print()

for days in rebalance_days_options:
    rets = holding_results.get(days, [])
    if not rets:
        continue
    avg = sum(rets) / len(rets)
    pos = sum(1 for r in rets if r > 0) / len(rets) * 100
    print(f"  {days}-day hold: n={len(rets)}, avg={avg:+.3f}%, positive={pos:.1f}%")

print()
print("=" * 70)
print("SCENARIO: What if we hold 14 days with 3+ consensus, ignoring other scores?")
print("=" * 70)

# Simulate: buy top consensus fund, hold 14 days, reassess
n_trades = 0
total_cost = 0
total_gross = 0
win_trades = 0

for date in valid_dates[::14]:  # Every 14 days
    records = trading_by_date.get(date, [])
    fund_buys = defaultdict(int)
    fund_codes = {}
    for r in records:
        if '买入' not in r.get('action', ''):
            continue
        fn = r.get('fund_name', '')
        fund_buys[fn] += 1
        fund_codes[fn] = r.get('fund_code', '')
    
    consensus_funds = sorted(
        [(fn, count) for fn, count in fund_buys.items() if count >= 3],
        key=lambda x: -x[1]
    )
    
    if not consensus_funds:
        continue
    
    for fn, count in consensus_funds[:2]:  # Top 2 funds per rebalance
        code = fund_codes[fn]
        if not code:
            continue
        nav_buy = get_nav_on_date(code, date)
        nav_sell = get_nav_n_days_after(code, code, 14)
        if nav_buy is None or nav_sell is None:
            continue
        
        gross = (nav_sell - nav_buy) / nav_buy
        cost = PURCHASE_FEE_RATE + REDEEM_FEE_MED  # 14 days = medium-term fee
        net = gross - cost
        
        n_trades += 1
        total_gross += gross * 100
        total_cost += cost * 100
        if net > 0:
            win_trades += 1

print(f"  Total trades: {n_trades}")
print(f"  Avg gross return: {total_gross/n_trades:.3f}%" if n_trades else "  No trades")
print(f"  Avg cost: {total_cost/n_trades:.3f}%" if n_trades else "")
print(f"  Win rate: {win_trades/n_trades*100:.1f}%" if n_trades else "")
print(f"  Avg NET return: {(total_gross-total_cost)/n_trades:.3f}%" if n_trades else "")

print()
print("BREAK-EVEN ANALYSIS:")
print(f"  For 7-day hold: Need avg gross > {PURCHASE_FEE_RATE*100 + REDEEM_FEE_SHORT*100:.2f}% to break even")
print(f"  For 14-day hold: Need avg gross > {PURCHASE_FEE_RATE*100 + REDEEM_FEE_MED*100:.2f}% to break even")
print(f"  Current 7-day alpha: ~1.4%")
print(f"  Current 14-day alpha (from earlier): ~2.2%")
print()
print("CONCLUSION:")
print("  7-day hold CANNOT profit after costs (1.4% < 2.1%)")
print("  14-day hold CAN profit (2.2% > 1.1%)")
print("  → Holding period is the key variable!")
