"""Walk-forward test of V8 champion config across FULL 3-year period."""
import sys, copy, json
from datetime import datetime, timedelta
sys.path.insert(0, '.')
from backtest.engine.backtest import run_backtest

# Full 3-year V8 champion config
V8_CHAMPION = {
    "initial_cash": 10000,
    "weights": {"quality": 25, "cost": 20, "manager": 20, "momentum": 15, "smart_money": 20},
    "min_score": 3.0,
    "no_stop_loss": True,
    "take_profit_pct": 50.0,  # 50% - very high, let winners run
    "min_consensus": 3,
    "max_holdings": 5,
    "kelly_cap_bull": 0.5,
    "kelly_cap_bear": 0.25,
    "pyramiding_enabled": False,
    "smart_swap": True,
    "regime_specific": True,
}

# Alternate configs to try:
# A) V8 champion + step_take_profit=True
# B) V8 champion with max_holdings=9 (ablation log shows Holdings: 9 for best run)
# C) V8 champion with consensus_window_days=5 (multi-day consensus)

CONFIGS = [
    ("V8_CHAMPION", {}),
    ("V8_STEPTP", {"step_take_profit": True}),
    ("V8_HOLD9", {"max_holdings": 9}),
    ("V8_WINDOW5", {"consensus_window_days": 5}),
]

# 6-month train, 3-month test, slide monthly across 3 years (2023-07 to 2026-07)
# This gives us 24 windows
TRAIN_MONTHS = 6
TEST_MONTHS = 3

# Generate windows
base_start = datetime(2023, 7, 17)
base_end = datetime(2026, 7, 24)

windows = []
current = base_start
while current + timedelta(days=TRAIN_MONTHS*30 + TEST_MONTHS*30) <= base_end:
    train_start = current.strftime("%Y-%m-%d")
    train_end = (current + timedelta(days=TRAIN_MONTHS*30)).strftime("%Y-%m-%d")
    test_end = (current + timedelta(days=(TRAIN_MONTHS+TEST_MONTHS)*30)).strftime("%Y-%m-%d")
    
    # For walk-forward, backtest uses train period to compute scores, then test period to trade
    # The backtest handles this internally when we pass start_date = train_end, end_date = test_end
    # But we also need to pre-load training data... which the engine already handles
    
    windows.append((train_end, test_end))
    current += timedelta(days=30)  # slide 1 month

# Total windows: (36 - 9) = 27 months of sliding / 1 month = ~24 windows
# But we just use a fixed set of 24 for matrix simplicity
# Actually let's create 24 fixed windows covering the period evenly
base_start = datetime(2023, 7, 17)
base_end = datetime(2026, 7, 24)
total_days = (base_end - base_start).days

# 24 windows, each with 6mo train + 3mo test
# Sliding by (total_days / 24) days each
window_days = total_days // 24
WINDOWS = []
for i in range(24):
    start = base_start + timedelta(days=i * window_days)
    train_end = start + timedelta(days=180)  # ~6mo
    test_end = start + timedelta(days=270)   # ~9mo
    if test_end <= base_end:
        WINDOWS.append((train_end.strftime("%Y-%m-%d"), test_end.strftime("%Y-%m-%d")))

wi = int(sys.argv[1]) if len(sys.argv) > 1 else 0
ci = int(sys.argv[2]) if len(sys.argv) > 2 else 0

label, overrides = CONFIGS[ci]
tts, tte = WINDOWS[wi]

cfg = copy.deepcopy(V8_CHAMPION)
cfg.update(overrides)
cfg['start_date'] = tts
cfg['end_date'] = tte

res = run_backtest(cfg, clear_cache=True)
result = {
    'window': wi,
    'config': label,
    'period': f'{tts}~{tte}',
    'return': res.get('total_return', 0),
    'trades': res.get('trade_count', 0),
    'fees': res.get('total_fees', 0),
    'max_dd': res.get('max_drawdown', 0),
    'win_rate': res.get('win_rate', 0),
    'avg_hold_days': res.get('avg_hold_days', 0),
    'benchmark_csi300': res.get('benchmark_csi300', res.get('benchmark_return', 0)),
    'holdings_avg': res.get('avg_holdings', res.get('holdings', 0)),
}

outname = f'v8wf_w{wi}_c{ci}.json'
with open(outname, 'w') as f:
    json.dump(result, f)
print(f'{label} W{wi} ({tts}~{tte}): Ret={result["return"]:+.2f}%  Trades={result["trades"]}  DD={result["max_dd"]:.1f}%  Benchmark={result["benchmark_csi300"]:+.1f}%')
