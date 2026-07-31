"""Walk-forward test: Expert-following strategies vs V8 Champion (9 windows)."""
import sys, json, copy
sys.path.insert(0, '.')
from backtest.engine.backtest import run_backtest

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

LABELS = ['EXP_3P', 'EXP_2P', 'EXP_MOM', 'V8_ORIGINAL']

base = {
    'initial_cash': 10000,
    'no_stop_loss': True,
    'pyramiding_enabled': False,
    'smart_swap': False,
    'regime_specific': False,
    'step_take_profit': False,
    'consensus_window_days': 0,
}

CONFIGS = {
    'EXP_3P': {
        'weights': {'quality': 0, 'cost': 0, 'manager': 0, 'momentum': 0, 'smart_money': 100},
        'take_profit_pct': 8.0,
        'min_consensus': 3,
        'min_score': 2.5,
        'max_holdings': 3,
    },
    'EXP_2P': {
        'weights': {'quality': 0, 'cost': 0, 'manager': 0, 'momentum': 0, 'smart_money': 100},
        'take_profit_pct': 5.0,
        'min_consensus': 2,
        'min_score': 1.5,
        'max_holdings': 3,
    },
    'EXP_MOM': {
        'weights': {'quality': 0, 'cost': 0, 'manager': 0, 'momentum': 30, 'smart_money': 70},
        'take_profit_pct': 6.0,
        'min_consensus': 2,
        'min_score': 2.0,
        'max_holdings': 4,
    },
    'V8_ORIGINAL': {
        'weights': {'quality': 25, 'cost': 20, 'manager': 20, 'momentum': 15, 'smart_money': 20},
        'take_profit_pct': 0.5,
        'min_consensus': 3,
        'min_score': 3.0,
        'smart_swap': True,
        'step_take_profit': True,
        'max_holdings': 5,
    },
}

# Run walk-forward for given window
wi = int(sys.argv[1]) if len(sys.argv) > 1 else 0
ts, te, tts, tte = WINDOWS[wi]
print(f'=== Window {wi}: Test {tts}~{tte} ===')
sys.stdout.flush()

# Test phase only (skip train - we use fixed configs, no optimization needed)
test_results = {}
train_results = {}
for label in LABELS:
    test_cfg = copy.deepcopy(base)
    test_cfg.update(CONFIGS[label])
    test_cfg['start_date'] = tts
    test_cfg['end_date'] = tte
    test_res = run_backtest(test_cfg, clear_cache=True)
    
    test_results[label] = {
        'return': round(test_res.get('total_return', 0), 4),
        'drawdown': round(test_res.get('max_drawdown', 0), 4),
        'sharpe': round(test_res.get('sharpe_ratio', 0), 2),
        'trades': test_res.get('trade_count', 0),
        'fees': round(test_res.get('total_fees', 0), 2),
    }
    train_results[label] = {'return': 0, 'drawdown': 0}
    print(f'  {label:12s}: Test={test_results[label]["return"]:+.2f}%  DD={test_results[label]["drawdown"]:.2f}%  Trades={test_results[label]["trades"]:3d}  Fees={test_results[label]["fees"]:.0f}')
    sys.stdout.flush()

# Save results
result = {
    'window': wi,
    'train_period': f'{ts}~{te}',
    'test_period': f'{tts}~{tte}',
    'train_results': train_results,
    'test_results': test_results,
}
    
with open(f'expert_wf_window{wi}.json', 'w') as f:
    json.dump(result, f, indent=2)

print(f'\nSaved: expert_wf_window{wi}.json')
