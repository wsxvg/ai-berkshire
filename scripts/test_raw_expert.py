"""Test pure expert-following without scoring filters - is the score system destroying alpha?"""
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

base = {
    'initial_cash': 10000,
    'no_stop_loss': True,
    'pyramiding_enabled': False,
    'smart_swap': False,
    'regime_specific': False,
    'step_take_profit': False,
    'consensus_window_days': 0,
}

# Strategy variations to test
configs = [
    # A: Pure expert, no scoring filters - min_score=0
    # Buy whenever >=2 experts buy, no other criteria
    ('RAW_2P', {
        'weights': {'quality': 0, 'cost': 0, 'manager': 0, 'momentum': 0, 'smart_money': 100},
        'take_profit_pct': 6.0,
        'min_consensus': 2,
        'min_score': 0.5,  # Very low - only need some SM activity
        'max_holdings': 5,
    }),
    # B: Raw expert with momentum filter MINIMAL
    ('RAW_EXP_MOM', {
        'weights': {'quality': 0, 'cost': 0, 'manager': 0, 'momentum': 20, 'smart_money': 80},
        'take_profit_pct': 6.0,
        'min_consensus': 2,
        'min_score': 1.0,
        'max_holdings': 5,
    }),
    # C: Pure expert, 3-person consensus
    ('RAW_3P', {
        'weights': {'quality': 0, 'cost': 0, 'manager': 0, 'momentum': 0, 'smart_money': 100},
        'take_profit_pct': 8.0,
        'min_consensus': 3,
        'min_score': 0.5,
        'max_holdings': 4,
    }),
]

for wi in range(8):  # Skip window 8 for speed
    ts, te, tts, tte = WINDOWS[wi]
    print(f'\n=== Window {wi}: Test {tts}~{tte} ===')
    for label, params in configs:
        cfg = copy.deepcopy(base)
        cfg.update(params)
        cfg['start_date'] = tts
        cfg['end_date'] = tte
        res = run_backtest(cfg, clear_cache=True)
        print(f'  {label:15s}: Return={res.get("total_return",0):+.2f}%  Trades={res.get("trade_count",0):3d}  Fees={res.get("total_fees",0):.0f}  DD={res.get("max_drawdown",0):.2f}%')

print('\nDone')
