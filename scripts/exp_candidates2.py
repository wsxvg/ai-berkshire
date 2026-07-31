"""Robust experiment runner - handles errors per window/config."""
import sys, json, copy, traceback
sys.path.insert(0, '.')
from backtest.engine.backtest import run_backtest

LOG_FILE = 'exp_candidates2.log'
f = open(LOG_FILE, 'w', buffering=1)

def log(msg):
    f.write(msg + '\n')
    f.flush()
    print(msg, flush=True)

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

configs = [
    ('SM_2P', {
        'weights': {'quality': 0, 'cost': 0, 'manager': 0, 'momentum': 0, 'smart_money': 100},
        'take_profit_pct': 6.0,
        'min_consensus': 2,
        'min_score': 0.5,
        'max_holdings': 4,
    }),
    ('EXP_MOM', {
        'weights': {'quality': 0, 'cost': 0, 'manager': 0, 'momentum': 30, 'smart_money': 70},
        'take_profit_pct': 6.0,
        'min_consensus': 2,
        'min_score': 2.0,
        'max_holdings': 4,
    }),
]

results = {}
for wi in range(8):
    tts, tte = WINDOWS[wi]
    log(f'\n=== Window {wi}: {tts}~{tte} ===')
    results[wi] = {}
    for label, params in configs:
        try:
            cfg = copy.deepcopy(base)
            cfg.update(params)
            cfg['start_date'] = tts
            cfg['end_date'] = tte
            res = run_backtest(cfg, clear_cache=True)
            ret = res.get('total_return', 0)
            dd = res.get('max_drawdown', 0)
            trades = res.get('trade_count', 0)
            fees = res.get('total_fees', 0)
            results[wi][label] = {'ret': ret, 'dd': dd, 'trades': trades, 'fees': fees}
            log(f'  {label:12s}: Ret={ret:+.2f}%  Trades={trades:3d}  Fees={fees:.0f}  DD={dd:.2f}%')
        except Exception as e:
            log(f'  {label:12s}: ERROR - {str(e)[:50]}')
            traceback.print_exc(file=f)
            f.flush()

# Summary
log('\n=== FINAL TABLE ===')
labels = ['SM_2P', 'EXP_MOM']
print(f"{'Window':>6} {'Exp_MOM':>10} {'SM_2P':>10}")
for wi in range(8):
    if wi in results:
        em = results[wi].get('EXP_MOM', {}).get('ret', 0)
        sm = results[wi].get('SM_2P', {}).get('ret', 0)
        print(f"{wi:>6} {em:>+9.2f}% {sm:>+9.2f}%")

f.close()
print(f'\nResults written to {LOG_FILE}')
