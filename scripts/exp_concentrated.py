"""Concentrated aggressive strategy: 1-3 holdings, high kelly cap, high TP."""
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

# max_holdings=1 with full kelly (1.0) means ALL IN one fund
configs = [
    # c0: full momentum, aggressive
    ('MOM_1TP10', {
        'weights': {'quality': 0, 'cost': 0, 'manager': 0, 'momentum': 100, 'smart_money': 0},
        'take_profit_pct': 10.0,
        'min_consensus': 2, 'min_score': 0, 'max_holdings': 1, 'kelly_cap_bull': 1.0,
    }),
    # c1: blend with smart money
    ('BLEND_1TP8', {
        'weights': {'quality': 0, 'cost': 0, 'manager': 0, 'momentum': 50, 'smart_money': 50},
        'take_profit_pct': 8.0,
        'min_consensus': 2, 'min_score': 0, 'max_holdings': 1, 'kelly_cap_bull': 1.0,
    }),
    # c2: 2 holdings for a bit of diversity
    ('BLEND_2TP8', {
        'weights': {'quality': 0, 'cost': 0, 'manager': 0, 'momentum': 50, 'smart_money': 50},
        'take_profit_pct': 8.0,
        'min_consensus': 2, 'min_score': 0, 'max_holdings': 2, 'kelly_cap_bull': 0.50,
    }),
    # c3: 3 holdings
    ('BLEND_3TP8', {
        'weights': {'quality': 0, 'cost': 0, 'manager': 0, 'momentum': 50, 'smart_money': 50},
        'take_profit_pct': 8.0,
        'min_consensus': 2, 'min_score': 0, 'max_holdings': 3, 'kelly_cap_bull': 0.35,
    }),
    # c4: blend TP12
    ('BLEND_1TP12', {
        'weights': {'quality': 0, 'cost': 0, 'manager': 0, 'momentum': 50, 'smart_money': 50},
        'take_profit_pct': 12.0,
        'min_consensus': 2, 'min_score': 0, 'max_holdings': 1, 'kelly_cap_bull': 1.0,
    }),
    # c5: higher momentum
    ('MOM70_1TP10', {
        'weights': {'quality': 0, 'cost': 0, 'manager': 0, 'momentum': 70, 'smart_money': 30},
        'take_profit_pct': 10.0,
        'min_consensus': 2, 'min_score': 0, 'max_holdings': 1, 'kelly_cap_bull': 1.0,
    }),
    # c6: min_score=2 (higher quality filter)
    ('BLEND_1TP8_HQ', {
        'weights': {'quality': 0, 'cost': 0, 'manager': 0, 'momentum': 50, 'smart_money': 50},
        'take_profit_pct': 8.0,
        'min_consensus': 2, 'min_score': 2.0, 'max_holdings': 1, 'kelly_cap_bull': 1.0,
    }),
    # c7: balanced TP8 3hold
    ('BLEND_3TP10', {
        'weights': {'quality': 0, 'cost': 0, 'manager': 0, 'momentum': 50, 'smart_money': 50},
        'take_profit_pct': 10.0,
        'min_consensus': 2, 'min_score': 0, 'max_holdings': 3, 'kelly_cap_bull': 0.35,
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
    'period': f'{tts}~{tte}',
    'return': res.get('total_return', 0),
    'trades': res.get('trade_count', 0),
    'fees': res.get('total_fees', 0),
    'max_dd': res.get('max_drawdown', 0),
    'win_rate': res.get('win_rate', 0),
    'avg_hold_days': res.get('avg_hold_days', 0),
}

outname = f'conc_w{wi}_c{ci}.json'
with open(outname, 'w') as f:
    json.dump(result, f)
print(f'{label} W{wi}: Ret={result["return"]:+.2f}%  Trades={result["trades"]}  DD={result["max_dd"]:.1f}%  Hold={result["avg_hold_days"]:.0f}d')
