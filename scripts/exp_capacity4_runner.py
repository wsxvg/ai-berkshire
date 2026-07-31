"""Capacity4: test 30 holdings, Mo40 weight, regime_specific, min_consensus=1.
Same 8-windows walk-forward, single (wi, ci) pair per invocation."""
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
    # c0: 30 slots, TP6, Mo30 — 直接推容量上限
    ('MOM30_TP6', {
        'weights': {'quality': 0, 'cost': 0, 'manager': 0, 'momentum': 30, 'smart_money': 70},
        'take_profit_pct': 6.0,
        'min_consensus': 2, 'min_score': 0, 'max_holdings': 30, 'kelly_cap_bull': 0.10,
    }),
    # c1: 30 slots with TP8 — 利润跑得更多 (因为容量大单仓位小)
    ('MOM30_TP8', {
        'weights': {'quality': 0, 'cost': 0, 'manager': 0, 'momentum': 30, 'smart_money': 70},
        'take_profit_pct': 8.0,
        'min_consensus': 2, 'min_score': 0, 'max_holdings': 30, 'kelly_cap_bull': 0.10,
    }),
    # c2: MOM24 with Mo40/SM60 — momentum 多一点看能不能抗 W4/W6 回撤
    ('MOM24_Mo40', {
        'weights': {'quality': 0, 'cost': 0, 'manager': 0, 'momentum': 40, 'smart_money': 60},
        'take_profit_pct': 6.0,
        'min_consensus': 2, 'min_score': 0, 'max_holdings': 24, 'kelly_cap_bull': 0.10,
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
outname = f'cap4_w{wi}_c{ci}.json'
with open(outname, 'w') as f:
    json.dump(result, f)
print(f'{label} W{wi}: Ret={result["return"]:+.3f}%  Trades={result["trades"]}  DD={result["max_dd"]:.2f}%  WR={result["win_rate"]:.0f}%')
