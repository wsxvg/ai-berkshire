"""Test if expert buy signals predict future fund returns (univariate analysis)."""
import json
import bisect
from collections import defaultdict

# Load data
with open('backtest/data/trading_by_date_fixed.json') as f:
    trading_by_date = json.load(f)

with open('backtest/data/fund_charts.json') as f:
    fund_charts = json.load(f)

print(f"trading_by_date: {len(trading_by_date)} days")
print(f"fund_charts: {len(fund_charts)} funds")
print()

# For each date, count how many experts bought each fund
# Then check next-day, 3-day, 7-day, 14-day, 30-day returns

def get_nav_on_date(code, date_str):
    """Get NAV for fund on or before date_str."""
    pts = fund_charts.get(code, [])
    if not pts:
        return None
    # pts are sorted by xAxis
    dates = [p.get('xAxis', '') for p in pts]
    idx = bisect.bisect_right(dates, date_str) - 1
    if idx < 0:
        return None
    return float(pts[idx].get('yAxis', 0)) / 100 + 1  # Convert to 1.xxx format


def get_nav_n_days_after(code, date_str, n):
    """Get NAV n trading days after date_str."""
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


# Analyze signal -> future return
results = defaultdict(list)  # signal_type -> [returns]

all_dates = sorted(trading_by_date.keys())

# Only use dates that have enough history for forward testing
# Skip first 30 days and last 30 days
valid_dates = all_dates[30:-30]

for date in valid_dates:
    records = trading_by_date.get(date, [])
    for r in records:
        if '买入' not in r.get('action', ''):
            continue
        fn = r.get('fund_name', '')
        code = r.get('fund_code', '')
        if not code:
            continue
        
        # Get buy-day NAV and future NAVs
        nav_t0 = get_nav_on_date(code, date)
        if nav_t0 is None:
            continue
        
        # Check returns at different horizons
        for horizon, label in [(1, 'T+1'), (3, 'T+3'), (7, 'T+7'), (14, 'T+14'), (30, 'T+30')]:
            nav_future = get_nav_n_days_after(code, date, horizon)
            if nav_future is None:
                continue
            ret = (nav_future - nav_t0) / nav_t0 * 100
            results[label].append(ret)

# Print results
print("=" * 60)
print("SIGNAL ALPHA TEST: Expert buy signals vs future fund returns")
print("=" * 60)
print()
for horizon in ['T+1', 'T+3', 'T+7', 'T+14', 'T+30']:
    rets = results[horizon]
    if not rets:
        print(f"{horizon}: No data")
        continue
    import statistics
    avg_ret = sum(rets) / len(rets)
    median_ret = statistics.median(rets)
    pos_pct = sum(1 for r in rets if r > 0) / len(rets) * 100
    
    print(f"{horizon}: n={len(rets)}, avg={avg_ret:+.3f}%, median={median_ret:+.3f}%, positive={pos_pct:.1f}%")
    if len(rets) > 1:
        std = statistics.stdev(rets)
        print(f"       std={std:.3f}%, t-stat={avg_ret/(std/len(rets)**0.5):+.2f}" if std > 0 else "")

print()
print("Interpretation:")
print("- If avg return at T+1/T+3 is significantly positive, expert buys DO have alpha")
print("- If avg return is ~0%, expert buys have NO predictive power")
print("- If avg return is NEGATIVE, expert buys are actually contrarian signals")

# Also check: what about SAME-DAY? (should be ~0 since we buy at same NAV)
print()
print("Same-day check (should be ~0%):")
for horizon in ['T+1']:
    rets = results[horizon]
    if rets:
        avg = sum(rets) / len(rets)
        print(f"  Average return next day after expert buy: {avg:+.4f}%")
