"""Experiment: parallel walk-forward via multiprocessing."""
import sys, copy, multiprocessing, os
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
    ('EXP_MOM_4', {
        'weights': {'quality': 0, 'cost': 0, 'manager': 0, 'momentum': 30, 'smart_money': 70},
        'take_profit_pct': 6.0,
        'min_consensus': 2,
        'min_score': 2.0,
        'max_holdings': 4,
        'kelly_cap_bull': 0.25,
    }),
    ('EXP_MOM_8', {
        'weights': {'quality': 0, 'cost': 0, 'manager': 0, 'momentum': 30, 'smart_money': 70},
        'take_profit_pct': 6.0,
        'min_consensus': 2,
        'min_score': 2.0,
        'max_holdings': 8,
        'kelly_cap_bull': 0.15,
    }),
    ('EXP_MOM_KELLY', {
        'weights': {'quality': 0, 'cost': 0, 'manager': 0, 'momentum': 30, 'smart_money': 70},
        'take_profit_pct': 6.0,
        'min_consensus': 2,
        'min_score': 2.0,
        'max_holdings': 4,
        'kelly_cap_bull': 0.40,
    }),
    ('RAW_8', {
        'weights': {'quality': 0, 'cost': 0, 'manager': 0, 'momentum': 0, 'smart_money': 100},
        'take_profit_pct': 6.0,
        'min_consensus': 2,
        'min_score': 0.5,
        'max_holdings': 8,
        'kelly_cap_bull': 0.15,
    }),
]

def run_window(wi):
    """Run all configs for a single window in a subprocess."""
    tts, tte = WINDOWS[wi]
    results = []
    for label, params in CONFIGS:
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
            results.append(f'  {label:12s}: Ret={ret:+.2f}%  Trades={trades:3d}  Fees={fees:.0f}  DD={dd:.2f}%')
        except Exception as e:
            results.append(f'  {label:12s}: ERROR - {str(e)[:80]}')
    return wi, tts, tte, results

if __name__ == '__main__':
    start_wi = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    end_wi = int(sys.argv[2]) if len(sys.argv) > 2 else 7
    windows_to_run = list(range(start_wi, end_wi + 1))
    print(f'Running {len(windows_to_run)} windows with {len(CONFIGS)} configs each...')
    
    # Use Pool for parallelism
    with multiprocessing.Pool(processes=4) as pool:
        outputs = pool.map(run_window, windows_to_run)
    
    # Aggregate results (sorted by window)
    outputs.sort(key=lambda x: x[0])
    for wi, tts, tte, results in outputs:
        print(f'\n=== Window {wi}: {tts}~{tte} ===')
        for r in results:
            print(r)
    
    # Also save to file
    with open(f'exp_sizing_v2_w{start_wi}_to_w{end_wi}.log', 'w') as f:
        for wi, tts, tte, results in outputs:
            f.write(f'\n=== Window {wi}: {tts}~{tte} ===\n')
            for r in results:
                f.write(r + '\n')
    
    print('\nDone. All windows complete.')
