"""Walk-forward test of V8 champion config across FULL 3-year period.

Single-pass window generation: 6mo train + 3mo test, slide 1 month.
Each job runs ONE (window_idx, config_idx) pair.
"""
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
    "take_profit_pct": 50.0,
    "min_consensus": 3,
    "max_holdings": 5,
    "kelly_cap_bull": 0.5,
    "kelly_cap_bear": 0.25,
    "pyramiding_enabled": False,
    "smart_swap": True,
    "regime_specific": True,
}

# Alternate configs to try
CONFIGS = [
    ("V8_CHAMPION", {}),
    ("V8_STEPTP", {"step_take_profit": True}),
    ("V8_HOLD9", {"max_holdings": 9}),
    ("V8_WINDOW5", {"consensus_window_days": 5}),
]

# 6-month train, 3-month test, slide monthly across 3 years
base_start = datetime(2023, 7, 17)
base_end = datetime(2026, 7, 24)

WINDOWS = []
current = base_start
while current + timedelta(days=270) <= base_end:
    train_end = (current + timedelta(days=180)).strftime("%Y-%m-%d")
    test_end = (current + timedelta(days=270)).strftime("%Y-%m-%d")
    WINDOWS.append((train_end, test_end))
    current += timedelta(days=30)

# Print count for CI debugging
print(f"[EXP_V8_WF] Generated {len(WINDOWS)} windows, {len(CONFIGS)} configs = {len(WINDOWS)*len(CONFIGS)} total jobs")
sys.stdout.flush()

# Bounds check
wi = int(sys.argv[1]) if len(sys.argv) > 1 else 0
ci = int(sys.argv[2]) if len(sys.argv) > 2 else 0

if wi >= len(WINDOWS):
    print(f"[EXP_V8_WF] FATAL: window index {wi} out of range (max {len(WINDOWS)-1})")
    sys.exit(1)
if ci >= len(CONFIGS):
    print(f"[EXP_V8_WF] FATAL: config index {ci} out of range (max {len(CONFIGS)-1})")
    sys.exit(1)

label, overrides = CONFIGS[ci]
tts, tte = WINDOWS[wi]

print(f"[EXP_V8_WF] Running config={label} window={wi} period={tts}~{tte}")
sys.stdout.flush()

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
print(f'[RESULT]{label} W{wi} ({tts}~{tte}): Ret={result["return"]:+.2f}%  Trades={result["trades"]}  DD={result["max_dd"]:.1f}%  Benchmark={result["benchmark_csi300"]:+.1f}%')
sys.stdout.flush()
