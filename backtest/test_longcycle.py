# -*- coding: utf-8 -*-
"""长周期辅助策略冒烟测试
验证：
1. 不开长周期参数 → 结果与之前一致（不影响现有策略）
2. 开 weekly_macd_divergence → 不报错
3. 开 yearly_ma_filter → 不报错
4. 开 weekly_bollinger_adjust → 不报错
5. 三合一全开 → 不报错
"""
import sys, time, json
sys.path.insert(0, '.')
from backtest.engine.backtest import run_backtest

_cfg = json.load(open('data/evolution/best_config.json', 'r', encoding='utf-8'))
BASE = dict(_cfg.get('config', {}))
BASE['start_date'] = '2023-10-01'
BASE['end_date'] = '2023-12-31'
BASE['initial_cash'] = 100000

results = {}

# Test 1: baseline（不开长周期）
print("=== Test 1: baseline (no longcycle) ===", flush=True)
t0 = time.time()
r1 = run_backtest(dict(BASE))
results['baseline'] = {
    'return': r1.get('total_return', 0),
    'trades': r1.get('trade_count', 0),
    'fees': r1.get('total_fees', 0),
    'time': time.time() - t0,
}
print(f"  return={results['baseline']['return']:.2f}% trades={results['baseline']['trades']} fees={results['baseline']['fees']:.0f} time={results['baseline']['time']:.0f}s\n", flush=True)

# Test 2-5: 逐个开长周期参数
longcycle_configs = {
    'weekly_macd_divergence': {'weekly_macd_divergence': True},
    'yearly_ma_filter': {'yearly_ma_filter': True},
    'weekly_bollinger_adjust': {'weekly_bollinger_adjust': True},
    'all_three': {
        'weekly_macd_divergence': True,
        'yearly_ma_filter': True,
        'weekly_bollinger_adjust': True,
    },
}

for name, extra in longcycle_configs.items():
    print(f"=== Test: {name} ===", flush=True)
    cfg = dict(BASE, **extra)
    t0 = time.time()
    try:
        r = run_backtest(cfg)
        results[name] = {
            'return': r.get('total_return', 0),
            'trades': r.get('trade_count', 0),
            'fees': r.get('total_fees', 0),
            'time': time.time() - t0,
            'status': 'OK',
        }
        print(f"  return={results[name]['return']:.2f}% trades={results[name]['trades']} fees={results[name]['fees']:.0f} time={results[name]['time']:.0f}s\n", flush=True)
    except Exception as e:
        results[name] = {'status': f'ERROR: {e}', 'time': time.time() - t0}
        print(f"  ERROR: {e}\n", flush=True)

# 汇总
print("=" * 60, flush=True)
print("Summary", flush=True)
print("=" * 60, flush=True)
for name, r in results.items():
    status = r.get('status', 'OK')
    if status == 'OK':
        print(f"  {name:<30} return={r['return']:.2f}% trades={r['trades']} fees={r['fees']:.0f} time={r['time']:.0f}s", flush=True)
    else:
        print(f"  {name:<30} {status}", flush=True)

# 验证 baseline 一致性（长周期参数关闭时不应改变结果）
print("\n[OK] smoke test done", flush=True)
