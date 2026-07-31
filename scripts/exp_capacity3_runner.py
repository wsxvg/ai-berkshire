"""Capacity3 experiment: test 14-24 holdings, different TP and weights.
Outputs one JSON per (window, config) pair for GitHub Actions artifact collection."""
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

configs = [
    # c0: MOM_12 baseline + TP5 (faster exit → more trades/year)
    ('MOM12_TP5', {
        'weights': {'quality': 0, 'cost': 0, 'manager': 0, 'momentum': 30, 'smart_money': 70},
        'take_profit_pct': 5.0,
        'min_consensus': 2, 'min_score': 0, 'max_holdings': 12, 'kelly_cap_bull': 0.10,
    }),
    # c1: 16 slots, TP6 (more capacity)
    ('MOM16_TP6', {
        'weights': {'quality': 0, 'cost': 0, 'manager': 0, 'momentum': 30, 'smart_money': 70},
        'take_profit_pct': 6.0,
        'min_consensus': 2, 'min_score': 0, 'max_holdings': 16, 'kelly_cap_bull': 0.10,
    }),
    # c2: 24 slots max capacity
    ('MOM24_TP6', {
        'weights': {'quality': 0, 'cost': 0, 'manager': 0, 'momentum': 30, 'smart_money': 70},
        'take_profit_pct': 6.0,
        'min_consensus': 2, 'min_score': 0, 'max_holdings': 24, 'kelly_cap_bull': 0.10,
    }),
    # c3: Mo20/SM80 weight with 16 slots — test if more smart_money weight helps
    ('MOM16_SM80', {
        'weights': {'quality': 0, 'cost': 0, 'manager': 0, 'momentum': 20, 'smart_money': 80},
        'take_profit_pct': 6.0,
        'min_consensus': 2, 'min_score': 0, 'max_holdings': 16, 'kelly_cap_bull': 0.10,
    }),
    # c4: 16 slots + TP8 (let winners run)
    ('MOM16_TP8', {
        'weights': {'quality': 0, 'cost': 0, 'manager': 0, 'momentum': 30, 'smart_money': 70},
        'take_profit_pct': 8.0,
        'min_consensus': 2, 'min_score': 0, 'max_holdings': 16, 'kelly_cap_bull': 0.10,
    }),
]

wi = int(sys.argv[1]) if len(sys.argv) > 1 else 0
ci = int(sys.argv[2]) if len(sys.argv) > 2 else 0

label, params = configs[ci]
tts, tte = WINDOWS[wi]

cfg = copy.deepcopy(base)
cfg.update(params)
cfg['start_date'] = tts
cfg['end_date'] = tte
cfg['kelly_cap_bear'] = params['kelly_cap_bull'] * 0.7

res = run_backtest(cfg, clear_cache=True)
result = {
    'window': wi,
    'config': label,
    'params': params,
    'period': f'{tts}~{tte}',
    'return': res.get('total_return', 0),
    'trades': res.get('trade_count', 0),
    'fees': res.get('total_fees', 0),
    'max_dd': res.get('max_drawdown', 0),
    'win_rate': res.get('win_rate', 0),
    'avg_hold_days': res.get('avg_hold_days', 0),
}
outname = f'cap3_w{wi}_c{ci}.json'
with open(outname, 'w') as f:
    json.dump(result, f)
print(f'{label} W{wi}: Ret={result["return"]:+.3f}%  Trades={result["trades"]}  DD={result["max_dd"]:.2f}%  WR={result["win_rate"]:.0f}%')
