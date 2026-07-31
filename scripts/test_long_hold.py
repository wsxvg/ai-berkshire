"""Test: longer hold period + higher take-profit should capture the expert alpha."""
import sys, json, copy
sys.path.insert(0, '.')
from backtest.engine.backtest import run_backtest

# Use the same window structure as wf_simple_runner
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
    'weights': {'quality': 0, 'cost': 0, 'manager': 0, 'momentum': 0, 'smart_money': 100},
    'no_stop_loss': True,
    'take_profit_pct': 5.0,
    'pyramiding_enabled': False,
    'smart_swap': False,
    'regime_specific': False,
    'step_take_profit': False,
    'consensus_window_days': 5,
    'min_consensus': 2,
    'min_score': 1.0,
    'max_holdings': 5,
    'kelly_cap_bull': 0.3,
    'kelly_cap_bear': 0.25,
}

# Also test V8 with higher take profit for comparison
configs = [
    ('EXPERT_ONLY_LONG', {
        'weights': {'quality': 0, 'cost': 0, 'manager': 0, 'momentum': 0, 'smart_money': 100},
        'take_profit_pct': 5.0,
        'min_consensus': 2,
        'min_score': 1.0,
        'smart_swap': False,
        'step_take_profit': False,
        'consensus_window_days': 5,
    }),
    ('V8_TP5', {  # Same as champion but take-profit=5%
        'weights': {'quality': 25, 'cost': 20, 'manager': 20, 'momentum': 15, 'smart_money': 20},
        'take_profit_pct': 5.0,
        'min_consensus': 3,
        'min_score': 3.0,
        'smart_swap': True,
        'step_take_profit': True,
        'max_holdings': 5,
    }),
]

# Run first 3 windows
wi = int(sys.argv[1]) if len(sys.argv) > 1 else 0
ts, te, tts, tte = WINDOWS[wi]
print(f'=== Window {wi}: Train {ts}~{te} | Test {tts}~{tte} ===')

results = {}
for label, params in configs:
    test_cfg = copy.deepcopy(base)
    test_cfg.update(params)
    test_cfg['start_date'] = tts
    test_cfg['end_date'] = tte
    test_res = run_backtest(test_cfg, clear_cache=False)
    
    results[label] = {
        'return': test_res.get('total_return', 0),
        'drawdown': test_res.get('max_drawdown', 0),
        'sharpe': test_res.get('sharpe_ratio', 0),
        'trades': test_res.get('trade_count', 0),
        'fees': test_res.get('total_fees', 0),
    }
    print(f'  {label}: Return={test_res.get("total_return",0):.2f}%, DD={test_res.get("max_drawdown",0):.2f}%, Trades={test_res.get("trade_count",0)}, Fees={test_res.get("total_fees",0):.0f}')

with open(f'expert_long_hold_w{wi}.json', 'w') as f:
    json.dump({'window': wi, 'test_period': f'{tts}~{tte}', 'results': results}, f, indent=2)

print(f'Saved: expert_long_hold_w{wi}.json')
