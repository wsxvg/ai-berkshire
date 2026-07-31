"""Run a single (window, config) pair. Used by GitHub Actions matrix strategy.

Usage: python exp_capacity2_runner.py <window_idx> <config_idx>
Example: python exp_capacity2_runner.py 0 3  (W0, MOM_12_TP5)
"""
import sys, copy, json
sys.path.insert(0, '.')
from backtest.engine.backtest import run_backtest

WINDOWS = [
    ('2024-01-17', '2024-04-17'), ('2024-02-17', '2024-05-17'),
    ('2024-03-17', '2024-06-17'), ('2024-04-17', '2024-07-17'),
    ('2024-05-17', '2024-08-17'), ('2024-06-17', '2024-09-17'),
    ('2024-07-17', '2024-10-17'), ('2024-08-17', '2024-11-17'),
]

base = {
    'initial_cash': 10000,
    'no_stop_loss': True,
    'pyramiding_enabled': False,
    'smart_swap': False,
    'regime_specific': False,
    'step_take_profit': False,
    'consensus_window_days': 0,
}

CONFIGS = [
    ('MOM_14_S0', {  # larger capacity
        'weights': {'quality': 0, 'cost': 0, 'manager': 0, 'momentum': 30, 'smart_money': 70},
        'take_profit_pct': 6.0,
        'min_consensus': 2,
        'min_score': 0.0,
        'max_holdings': 14,
        'kelly_cap_bull': 0.09,
    }),
    ('MOM_16_S0', {  # max capacity
        'weights': {'quality': 0, 'cost': 0, 'manager': 0, 'momentum': 30, 'smart_money': 70},
        'take_profit_pct': 6.0,
        'min_consensus': 2,
        'min_score': 0.0,
        'max_holdings': 16,
        'kelly_cap_bull': 0.08,
    }),
    ('MOM_12_TP5', {  # lower take profit
        'weights': {'quality': 0, 'cost': 0, 'manager': 0, 'momentum': 30, 'smart_money': 70},
        'take_profit_pct': 5.0,
        'min_consensus': 2,
        'min_score': 0.0,
        'max_holdings': 12,
        'kelly_cap_bull': 0.10,
    }),
    ('MOM_12_TP8', {  # higher take profit
        'weights': {'quality': 0, 'cost': 0, 'manager': 0, 'momentum': 30, 'smart_money': 70},
        'take_profit_pct': 8.0,
        'min_consensus': 2,
        'min_score': 0.0,
        'max_holdings': 12,
        'kelly_cap_bull': 0.10,
    }),
    ('MOM_12_W20', {  # w20 - more smart money
        'weights': {'quality': 0, 'cost': 0, 'manager': 0, 'momentum': 20, 'smart_money': 80},
        'take_profit_pct': 6.0,
        'min_consensus': 2,
        'min_score': 0.0,
        'max_holdings': 12,
        'kelly_cap_bull': 0.10,
    }),
]

wi = int(sys.argv[1]) if len(sys.argv) > 1 else 0
ci = int(sys.argv[2]) if len(sys.argv) > 2 else 0

tts, tte = WINDOWS[wi]
label, params = CONFIGS[ci]

cfg = copy.deepcopy(base)
cfg.update(params)
cfg['start_date'] = tts
cfg['end_date'] = tte
cfg['kelly_cap_bear'] = params['kelly_cap_bull'] * 0.7

print(f'Running w{wi} {tts}~{tte} {label}')
res = run_backtest(cfg, clear_cache=True)

result = {
    'window': wi,
    'config': label,
    'period': f'{tts}~{tte}',
    'return': res.get('total_return', 0),
    'trades': res.get('trade_count', 0),
    'fees': res.get('total_fees', 0),
    'max_dd': res.get('max_drawdown', 0),
}
print(json.dumps(result))

# Write to file for artifact
out_file = f'cap2_w{wi}_c{ci}.json'
with open(out_file, 'w') as f:
    json.dump(result, f)
print(f'Saved to {out_file}')
