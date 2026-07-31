"""Run multiple candidate strategies, then WF validate."""
import sys, json, copy, os
sys.path.insert(0, '.')
from backtest.engine.backtest import run_backtest

# Log to file directly
LOG_FILE = 'exp_candidates.log'
f = open(LOG_FILE, 'w', buffering=1)  # Line buffered

def log(msg):
    f.write(msg + '\n')
    f.flush()
    print(msg)

WINDOWS = [
    ('2024-01-17', '2024-04-17'),
    ('2024-02-17', '2024-05-17'),
    ('2024-03-17', '2024-06-17'),
    ('2024-04-17', '2024-07-17'),
    ('2024-05-17', '2024-08-17'),
    ('2024-06-17', '2024-09-17'),
    ('2024-07-17', '2024-10-17'),
    ('2024-08-17', '2024-11-17'),
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

# CANDIDATE STRATEGIES (after momentum analysis)
configs = [
    ('SM_2P', {
        'weights': {'quality': 0, 'cost': 0, 'manager': 0, 'momentum': 0, 'smart_money': 100},
        'take_profit_pct': 6.0,
        'min_consensus': 2,
        'min_score': 0.5,
        'max_holdings': 4,
    }),
    ('SM_3P_HOLD', {
        'weights': {'quality': 0, 'cost': 0, 'manager': 0, 'momentum': 0, 'smart_money': 100},
        'take_profit_pct': 10.0,
        'min_consensus': 3,
        'min_score': 0.5,
        'max_holdings': 3,
    }),
    ('SM_2P_VLOW', {
        'weights': {'quality': 0, 'cost': 0, 'manager': 0, 'momentum': 0, 'smart_money': 100},
        'take_profit_pct': 3.0,
        'min_consensus': 2,
        'min_score': 0.5,
        'max_holdings': 5,
    }),
    ('SM_1P_HIGH', {
        'weights': {'quality': 0, 'cost': 0, 'manager': 0, 'momentum': 0, 'smart_money': 100},
        'take_profit_pct': 4.0,
        'min_consensus': 1,
        'min_score': 1.0,
        'max_holdings': 5,
    }),
]

# Run all 8 windows
for wi in range(8):
    tts, tte = WINDOWS[wi]
    log(f'\n=== Window {wi}: {tts}~{tte} ===')
    for label, params in configs:
        cfg = copy.deepcopy(base)
        cfg.update(params)
        cfg['start_date'] = tts
        cfg['end_date'] = tte
        res = run_backtest(cfg, clear_cache=True)
        trades = res.get('trade_count', 0)
        ret = res.get('total_return', 0)
        dd = res.get('max_drawdown', 0)
        fees = res.get('total_fees', 0)
        log(f'  {label:12s}: Ret={ret:+.2f}%  Trades={trades:3d}  Fees={fees:.0f}  DD={dd:.2f}%')

log('\n--- ALL DONE ---')

# Summary
f.close()
print(f'\nResults written to {LOG_FILE}')
