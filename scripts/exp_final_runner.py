"""Final extreme tests:
- MOM24 base vs MOM24 min_consensus=1 vs MOM24 TP6 kelly_cap=0.15
- Summary: confirm whether MOM24_TP6 is local optimum."""
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
    # c0: MOM24 baseline (re-run for confirmation)
    ('MOM24_BASE', {
        'weights': {'quality': 0, 'cost': 0, 'manager': 0, 'momentum': 30, 'smart_money': 70},
        'take_profit_pct': 6.0,
        'min_consensus': 2, 'min_score': 0, 'max_holdings': 24, 'kelly_cap_bull': 0.10,
        'smart_swap': False,
    }),
    # c1: MOM24 + min_consensus=1 (lower filter, pick up more signals)
    ('MOM24_MC1', {
        'weights': {'quality': 0, 'cost': 0, 'manager': 0, 'momentum': 30, 'smart_money': 70},
        'take_profit_pct': 6.0,
        'min_consensus': 1, 'min_score': 0, 'max_holdings': 24, 'kelly_cap_bull': 0.10,
        'smart_swap': False,
    }),
    # c2: MOM24 + kelly_cap=0.15 (larger position size)
    ('MOM24_KC15', {
        'weights': {'quality': 0, 'cost': 0, 'manager': 0, 'momentum': 30, 'smart_money': 70},
        'take_profit_pct': 6.0,
        'min_consensus': 2, 'min_score': 0, 'max_holdings': 24, 'kelly_cap_bull': 0.15,
        'smart_swap': False,
    }),
    # c3: MOM24_TP6 + TP8 on half the positions (hybrid TP strategy)
    ('MOM24_TP7', {
        'weights': {'quality': 0, 'cost': 0, 'manager': 0, 'momentum': 30, 'smart_money': 70},
        'take_profit_pct': 7.0,
        'min_consensus': 2, 'min_score': 0, 'max_holdings': 24, 'kelly_cap_bull': 0.10,
        'smart_swap': False,
    }),
    # c4: MOM24 + smart_swap=True (allow swapping existing holdings)
    ('MOM24_SWAP', {
        'weights': {'quality': 0, 'cost': 0, 'manager': 0, 'momentum': 30, 'smart_money': 70},
        'take_profit_pct': 6.0,
        'min_consensus': 2, 'min_score': 0, 'max_holdings': 24, 'kelly_cap_bull': 0.10,
        'smart_swap': True,
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
outname = f'final_w{wi}_c{ci}.json'
with open(outname, 'w') as f:
    json.dump(result, f)
print(f'{label} W{wi}: Ret={result["return"]:+.3f}%  Trades={result["trades"]}  DD={result["max_dd"]:.2f}%  WR={result["win_rate"]:.0f}%')
