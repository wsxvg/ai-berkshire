"""Test expert-following with optimal parameters - LOW TURNOVER."""
import sys, json, copy
sys.path.insert(0, '.')
from backtest.engine.backtest import run_backtest
from datetime import datetime

WINDOWS = [
    ('2023-07-17', '2024-01-17', '2024-01-17', '2024-04-17'),
    ('2023-08-17', '2024-02-17', '2024-02-17', '2024-05-17'),
    ('2023-09-17', '2024-03-17', '2024-03-17', '2024-06-17'),
    ('2023-10-17', '2024-04-17', '2024-04-17', '2024-07-17'),
    ('2023-11-17', '2024-05-17', '2024-05-17', '2024-08-17'),
    ('2023-12-17', '2024-06-17', '2024-06-17', '2024-09-17'),
    ('2024-01-17', '2024-07-17', '2024-07-17', '2024-10-17'),
    ('2024-02-17', '2024-08-17', '2024-08-17', '2024-11-17'),
    ('2024-03-17', '2024-09-17', '2024-09-17', '2026-07-24'),
]

base = {
    'initial_cash': 10000,
    'no_stop_loss': True,
    'pyramiding_enabled': False,
    'smart_swap': False,
    'regime_specific': False,
    'step_take_profit': False,
    'consensus_window_days': 3,
}

configs = [
    # Config 1: Pure expert-following (3+ consensus) - smart_money score max=5
    ('EXP_3P', {
        'weights': {'quality': 0, 'cost': 0, 'manager': 0, 'momentum': 0, 'smart_money': 100},
        'take_profit_pct': 8.0,
        'min_consensus': 3,
        'consensus_window_days': 0,  # SAME DAY only (not lookback)
        'min_score': 2.5,  # Score range is 0-5 for pure SM
        'max_holdings': 3,
    }),
    # Config 2: Pure expert (2+ consensus) - more signals
    ('EXP_2P', {
        'weights': {'quality': 0, 'cost': 0, 'manager': 0, 'momentum': 0, 'smart_money': 100},
        'take_profit_pct': 5.0,
        'min_consensus': 2,
        'consensus_window_days': 0,
        'min_score': 1.5,
        'max_holdings': 3,
    }),
    # Config 3: Expert + momentum combo
    ('EXP_MOM', {
        'weights': {'quality': 0, 'cost': 0, 'manager': 0, 'momentum': 30, 'smart_money': 70},
        'take_profit_pct': 6.0,
        'min_consensus': 2,
        'consensus_window_days': 0,
        'min_score': 2.0,
        'max_holdings': 4,
    }),
]

# Config 4: Original V8 champion for comparison
configs.append(('V8_ORIGINAL', {
    'weights': {'quality': 25, 'cost': 20, 'manager': 20, 'momentum': 15, 'smart_money': 20},
    'take_profit_pct': 0.5,
    'min_consensus': 3,
    'min_score': 3.0,
    'smart_swap': True,
    'step_take_profit': True,
    'max_holdings': 5,
    'consensus_window_days': 0,
}))

# Run first 4 windows
wi = int(sys.argv[1]) if len(sys.argv) > 1 else 0
ts, te, tts, tte = WINDOWS[wi]
print(f'=== Window {wi}: Test {tts}~{tte} ===')

results = {}
for label, params in configs:
    test_cfg = copy.deepcopy(base)
    test_cfg.update(params)
    test_cfg['start_date'] = tts
    test_cfg['end_date'] = tte
    
    # Save initial cash for fee ratio
    initial = test_cfg['initial_cash']
    
    test_res = run_backtest(test_cfg, clear_cache=False)
    
    ret = test_res.get('total_return', 0)
    fees = test_res.get('total_fees', 0)
    trades = test_res.get('trade_count', 0)
    dd = test_res.get('max_drawdown', 0)
    
    results[label] = {
        'return': ret,
        'drawdown': dd,
        'trades': trades,
        'fees': fees,
        'fee_ratio': round(fees / initial * 100, 3),
        'gross_est': round(ret + fees / initial * 100, 2),
    }
    print(f'  {label:12s}: Ret={ret:+.2f}%  DD={dd:.2f}%  Trades={trades:3d}  Fees={fees:>6.0f}  Gross~{ret + fees/initial*100:.2f}%')

# Summary
print()
print('=== SUMMARY (sorted by return) ===')
sorted_results = sorted(results.items(), key=lambda x: -x[1]['return'])
for label, r in sorted_results:
    print(f'  {label:12s}: Return={r["return"]:+.2f}%  (gross~{r["gross_est"]:+.2f}%)  Trades={r["trades"]}  FeeRatio={r["fee_ratio"]:.2f}%')

with open(f'expert_v2_w{wi}.json', 'w') as f:
    json.dump({'window': wi, 'test_period': f'{tts}~{tte}', 'results': results}, f, indent=2)
print(f'Saved: expert_v2_w{wi}.json')
