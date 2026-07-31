"""Experiment: test higher max_holdings and position_size to capture more alpha."""
import sys, copy
sys.path.insert(0, '.')
from backtest.engine.backtest import run_backtest

f = open('exp_sizing.log', 'w')
def log(msg):
    f.write(msg + '\n')
    f.flush()
    print(msg, flush=True)

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
    # 1. Current baseline EXP_MOM
    ('EXP_MOM_4', {
        'weights': {'quality': 0, 'cost': 0, 'manager': 0, 'momentum': 30, 'smart_money': 70},
        'take_profit_pct': 6.0,
        'min_consensus': 2,
        'min_score': 2.0,
        'max_holdings': 4,
        'kelly_cap_bull': 0.25,
    }),
    # 2. Double holdings
    ('EXP_MOM_8', {
        'weights': {'quality': 0, 'cost': 0, 'manager': 0, 'momentum': 30, 'smart_money': 70},
        'take_profit_pct': 6.0,
        'min_consensus': 2,
        'min_score': 2.0,
        'max_holdings': 8,
        'kelly_cap_bull': 0.15,
    }),
    # 3. Higher kelly (aggressive)
    ('EXP_MOM_KELLY', {
        'weights': {'quality': 0, 'cost': 0, 'manager': 0, 'momentum': 30, 'smart_money': 70},
        'take_profit_pct': 6.0,
        'min_consensus': 2,
        'min_score': 2.0,
        'max_holdings': 4,
        'kelly_cap_bull': 0.40,
    }),
    # 4. Minimal filters - capture ALL expert signals
    ('RAW_8', {
        'weights': {'quality': 0, 'cost': 0, 'manager': 0, 'momentum': 0, 'smart_money': 100},
        'take_profit_pct': 6.0,
        'min_consensus': 2,
        'min_score': 0.5,
        'max_holdings': 8,
        'kelly_cap_bull': 0.15,
    }),
]

wi = int(sys.argv[1]) if len(sys.argv) > 1 else 0
tts, tte = WINDOWS[wi]
log(f'\n=== Window {wi}: {tts}~{tte} ===')
for label, params in configs:
        try:
            cfg = copy.deepcopy(base)
            cfg.update(params)
            cfg['start_date'] = tts
            cfg['end_date'] = tte
            cfg['kelly_cap_bear'] = params.get('kelly_cap_bull', 0.25) * 0.7
            res = run_backtest(cfg, clear_cache=True)
            ret = res.get('total_return', 0)
            dd = res.get('max_drawdown', 0)
            trades = res.get('trade_count', 0)
            fees = res.get('total_fees', 0)
            log(f'  {label:12s}: Ret={ret:+.2f}%  Trades={trades:3d}  Fees={fees:.0f}  DD={dd:.2f}%')
        except Exception as e:
            log(f'  {label:12s}: ERROR - {str(e)[:60]}')

    f.close()
    print('Done')
