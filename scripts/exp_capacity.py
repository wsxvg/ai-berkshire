"""Capacity experiment: test higher max_holdings + lower min_score.

Key hypothesis: EXP_MOM_8 gets +0.61% with 8 slots. Can we get even more
alpha with 10-12 slots and lower min_score to use all slots?
"""
import sys, copy, multiprocessing
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
    ('MOM_8_S2', {  # baseline
        'weights': {'quality': 0, 'cost': 0, 'manager': 0, 'momentum': 30, 'smart_money': 70},
        'take_profit_pct': 6.0,
        'min_consensus': 2,
        'min_score': 2.0,
        'max_holdings': 8,
        'kelly_cap_bull': 0.15,
    }),
    ('MOM_10_S1', {  # more slots, lower score
        'weights': {'quality': 0, 'cost': 0, 'manager': 0, 'momentum': 30, 'smart_money': 70},
        'take_profit_pct': 6.0,
        'min_consensus': 2,
        'min_score': 1.0,
        'max_holdings': 10,
        'kelly_cap_bull': 0.12,
    }),
    ('MOM_10_S0', {  # more slots, no score filter
        'weights': {'quality': 0, 'cost': 0, 'manager': 0, 'momentum': 30, 'smart_money': 70},
        'take_profit_pct': 6.0,
        'min_consensus': 2,
        'min_score': 0.0,
        'max_holdings': 10,
        'kelly_cap_bull': 0.12,
    }),
    ('MOM_12_S0', {  # even more slots
        'weights': {'quality': 0, 'cost': 0, 'manager': 0, 'momentum': 30, 'smart_money': 70},
        'take_profit_pct': 6.0,
        'min_consensus': 2,
        'min_score': 0.0,
        'max_holdings': 12,
        'kelly_cap_bull': 0.10,
    }),
    ('MOM_10_C1', {  # single consensus
        'weights': {'quality': 0, 'cost': 0, 'manager': 0, 'momentum': 30, 'smart_money': 70},
        'take_profit_pct': 6.0,
        'min_consensus': 1,
        'min_score': 0.0,
        'max_holdings': 10,
        'kelly_cap_bull': 0.12,
    }),
]

def run_window(wi, configs):
    tts, tte = WINDOWS[wi]
    results = []
    for label, params in configs:
        try:
            cfg = copy.deepcopy(base)
            cfg.update(params)
            cfg['start_date'] = tts
            cfg['end_date'] = tte
            cfg['kelly_cap_bear'] = params['kelly_cap_bull'] * 0.7
            res = run_backtest(cfg, clear_cache=True)
            ret = res.get('total_return', 0)
            dd = res.get('max_drawdown', 0)
            trades = res.get('trade_count', 0)
            fees = res.get('total_fees', 0)
            results.append((label, ret, trades, fees, dd))
        except Exception as e:
            results.append((label, 0, 0, 0, 0))
    return wi, tts, tte, results

if __name__ == '__main__':
    workers = multiprocessing.Pool(processes=4)
    jobs = [(wi, CONFIGS) for wi in range(8)]
    outputs = workers.starmap(run_window, jobs)
    outputs.sort(key=lambda x: x[0])
    
    for wi, tts, tte, results in outputs:
        print(f'\n=== Window {wi}: {tts}~{tte} ===')
        for label, ret, trades, fees, dd in results:
            print(f'  {label:12s}: Ret={ret:+.2f}%  Trades={trades:3d}  Fees={fees:.0f}  DD={dd:.2f}%')
    
    # Aggregate
    print('\n=== AVERAGES ===')
    for ci, (label, *_) in enumerate(CONFIGS):
        rets = [outputs[wi][3][ci][1] for wi in range(8)]
        avg = sum(rets) / len(rets)
        wins = sum(1 for r in rets if r > 0)
        print(f'  {label:12s}: Avg={avg:+.3f}%/q  ({wins}/8 positive)')
