#!/usr/bin/env python3
"""Deep K-line analysis: was the July 2026 crash predictable from technical data?"""
import json, os, sys
from collections import defaultdict

DATA_DIR = 'C:/fund/data'

# ── Load data ──────────────────────────────────────────
charts_dir = os.path.join(DATA_DIR, 'fund_charts')
name_map = json.load(open(os.path.join(DATA_DIR, 'fund_name_map.json')))

# name_map is {name: code} - INVERTED! Also need reverse lookup.
# Build forward lookup: code -> name
code_to_name = {}
for k, v in name_map.items():
    # k=name, v=code
    code_to_name[v] = k

# Load a few key funds that the strategy likely holds
target_funds = []

# First find 华夏全球科技先锋混合(QDII) - user specifically asked about this
for code, name in code_to_name.items():
    if '全球' in str(name) or '华夏全球' in str(name):
        target_funds.append((code, name))

# Also find 000001 (the one we know crashed)
if '000001' not in [c for c, n in target_funds]:
    target_funds.append(('000001', code_to_name.get('000001', 'UNKNOWN-000001')))

# Find CSI 300 / broad market index
index_funds = []
for code, name in code_to_name.items():
    s = str(name)
    if '沪深300' in s or '300ETF' in s or '上证指数' in s or '深证' in s:
        index_funds.append((code, name))

print('=== TARGET USER-ASKED FUNDS (华夏全球) ===')
for code, name in target_funds[:20]:
    print(f'  {code}: {name}')

print('\n=== INDEX/CSI FUNDS ===')
for code, name in index_funds[:20]:
    print(f'  {code}: {name}')

# ── K-line pattern analysis ────────────────────────────
def load_chart(code):
    fpath = os.path.join(charts_dir, f'{code}.json')
    if not os.path.exists(fpath):
        return []
    try:
        return json.load(open(fpath))
    except:
        []

def extract_nav_series(chart):
    """Extract [(date, nav), ...] sorted by date."""
    return [(e['xAxis'], e['yAxis']) for e in chart if e.get('yAxis', 0) > 0]

def pct_change(series, days=1):
    """Compute rolling pct change."""
    changes = []
    for i in range(days, len(series)):
        prev = series[i-days][1]
        curr = series[i][1]
        if prev > 0:
            changes.append((series[i][0], (curr - prev) / prev * 100))
    return changes

def moving_avg(series, window):
    """Simple moving average of NAV values."""
    mas = []
    vals = [s[1] for s in series]
    for i in range(window-1, len(vals)):
        ma = sum(vals[i-window+1:i+1]) / window
        mas.append((series[i][0], ma))
    return mas

def analyze_crash_signals(code, name):
    """Check for pre-crash technical signals."""
    chart = load_chart(code)
    if not chart or len(chart) < 80:
        return None
    
    series = extract_nav_series(chart)
    if len(series) < 80:
        return None
    
    # Find the crash period: 6/30 - 7/20 2026
    # Look for the peak before crash
    june_july = [(d, v) for d, v in series if d >= '2026-05-01' and d <= '2026-08-31']
    before_crash = [(d, v) for d, v in series if d >= '2026-04-01' and d <= '2026-07-01']
    during_crash = [(d, v) for d, v in series if d >= '2026-06-20' and d <= '2026-07-31']
    
    if not june_july or not before_crash:
        return None
    
    # Key metrics
    peak_val = max(v for d, v in before_crash)
    peak_date = [d for d, v in before_crash if v == peak_val][0]
    
    # Find the lowest point in July
    july_vals = [(d, v) for d, v in june_july if d >= '2026-07-01' and d <= '2026-07-31']
    if not july_vals:
        return None
    trough_val = min(v for d, v in july_vals)
    trough_date = [d for d, v in july_vals if v == trough_val][0]
    
    crash_magnitude = (trough_val - peak_val) / peak_val * 100
    
    # 60-day return before crash (the regime detection signal)
    all_before = [(d, v) for d, v in series if d < '2026-07-01']
    if len(all_before) >= 60:
        nav_60d_before = all_before[-1][1]  # NAV on 60-day window start
        nav_now = series[-1][1] if series[-1][0] >= '2026-06-25' else all_before[-1][1]
        # Find actual 60 days before 7/1
        pre_july = [(d, v) for d, v in series if d <= '2026-07-01']
        if len(pre_july) >= 2:
            ret_60d = (pre_july[-1][1] - pre_july[-min(60, len(pre_july))][1]) / pre_july[-min(60, len(pre_july))][1] * 100
        else:
            ret_60d = 0
    else:
        ret_60d = 0
    
    # MA signals
    ma20 = moving_avg(series, 20)
    ma60 = moving_avg(series, 60)
    
    # Check if MA20 crossed below MA60 before crash (death cross)
    death_cross = False
    death_cross_date = None
    if ma20 and ma60:
        ma20_dict = dict(ma20)
        ma60_dict = dict(ma60)
        for d, v in ma20:
            if d in ma60_dict and d >= '2026-05-01' and d <= '2026-07-05':
                if ma20_dict.get(d, 0) < ma60_dict.get(d, 0):
                    # Check if prev day it was above
                    pass
    
    # Check consecutive down days before crash
    daily = []
    for i in range(1, len(series)):
        d = series[i][0]
        if d >= '2026-05-01' and d <= '2026-07-15':
            prev = series[i-1][1]
            curr = series[i][1]
            daily.append((d, (curr-prev)/prev*100 if prev > 0 else 0))
    
    # 5-day rolling drop before crash
    pre_weekly = [(d, v) for d, v in series if d >= '2026-06-15' and d <= '2026-07-10']
    
    return {
        'code': code,
        'name': name,
        'peak_date': peak_date,
        'peak_val': peak_val,
        'trough_date': trough_date,
        'trough_val': trough_val,
        'crash_magnitude_pct': crash_magnitude,
        'ret_60d': ret_60d,
        'june_july_series': june_july,
        'pre_july_daily_changes': daily[-30:] if daily else [],
    }

# ── Analyze the specific funds user asked about ─────────
print('\n' + '='*70)
print('DEEP ANALYSIS: JULY 2026 CRASH PREDICTABILITY')
print('='*70)

results = []
for code, name in target_funds[:10]:
    r = analyze_crash_signals(code, name)
    if r:
        results.append(r)

# Also analyze index funds
for code, name in index_funds[:5]:
    r = analyze_crash_signals(code, name)
    if r:
        results.append(r)

# Print results
for r in results:
    print(f"\n{'─'*60}")
    print(f"Fund: {r['name']} ({r['code']})")
    print(f"  Peak: {r['peak_date']} @ {r['peak_val']:.2f}")
    print(f"  Trough: {r['trough_date']} @ {r['trough_val']:.2f}")
    print(f"  Crash magnitude: {r['crash_magnitude_pct']:.1f}%")
    print(f"  60d return before July: {r['ret_60d']:.1f}%")
    print(f"  Pre-July daily changes (last 30):")
    for d, chg in r['pre_july_daily_changes'][-15:]:
        marker = " <<<" if chg < -5 else ""
        print(f"    {d}: {chg:+.2f}%{marker}")

# ── Index analysis ─────────────────────────────────────
print('\n' + '='*70)
print('MARKET INDEX (CSI300 PROXY) — WAS THERE A BENCHMARK CRASH?')
print('='*70)

# Use fund_charts_index.json
try:
    idx_data = json.load(open(os.path.join(DATA_DIR, 'fund_charts_index.json')))
    print(f'Type: {type(idx_data)}, Keys: {list(idx_data.keys())[:5] if isinstance(idx_data, dict) else f"len={len(idx_data)}"}')
    if isinstance(idx_data, dict):
        for k, v in list(idx_data.items())[:3]:
            print(f'  {k}: {str(v)[:200]}')
    elif isinstance(idx_data, list):
        for item in idx_data[:3]:
            print(f'  {str(item)[:200]}')
except Exception as e:
    print(f'Error loading index data: {e}')

# Also check trading_by_date_fixed.json for any July trading signals
print('\n=== TRADING SIGNALS (July) ===')
try:
    tbd = json.load(open(os.path.join(DATA_DIR, 'trading_by_date_fixed.json')))
    july_signals = {}
    if isinstance(tbd, dict):
        for code, signals in tbd.items():
            if isinstance(signals, list):
                july_s = [s for s in signals if '07-0' in str(s.get('date', '')) or '2026-07' in str(s.get('date', ''))]
                if july_s:
                    july_signals[code] = july_s[:3]
            elif isinstance(signals, dict):
                july_s = {d: v for d, v in signals.items() if '07-0' in d or '2026-07' in d}
                if july_s:
                    july_signals[code] = dict(list(july_s.items())[:3])
        for code, sigs in list(july_signals.items())[:10]:
            print(f'  {code}: {sigs}')
    elif isinstance(tbd, list):
        july_items = [t for t in tbd if '07-0' in str(t) or '2026-07' in str(t)]
        print(f'  July signals in list: {len(july_items)}')
        for item in july_items[:10]:
            print(f'    {str(item)[:150]}')
except Exception as e:
    print(f'Error: {e}')
