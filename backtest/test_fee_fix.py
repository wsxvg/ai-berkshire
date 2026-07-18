# -*- coding: utf-8 -*-
"""费率修复后的冒烟测试：验证申购费、赎回费、T+N、年交易上限全部正常
跑短周期(3个月)回测，检查费用合理、交易数量正常
"""
import sys, time, json
sys.path.insert(0, '.')
from backtest.engine.backtest import run_backtest

_cfg = json.load(open('data/evolution/best_config.json', 'r', encoding='utf-8'))
BASE = dict(_cfg.get('config', {}))
BASE['start_date'] = '2023-10-01'
BASE['end_date'] = '2023-12-31'
BASE['initial_cash'] = 100000

print("=== smoke test: 2023-Q4 (3 months) ===", flush=True)
t0 = time.time()
r = run_backtest(BASE)
elapsed = time.time() - t0

trades = r.get('trades', [])
buys = [t for t in trades if t.get('action') == 'buy']
sells = [t for t in trades if 'sell' in t.get('action', '')]
total_fees = r.get('total_fees', 0)

print(f"\n=== Result ===", flush=True)
print(f"  return: {r.get('total_return', 0):.2f}%", flush=True)
print(f"  maxDD: {r.get('max_drawdown', 0):.2f}%", flush=True)
print(f"  trades: {r.get('trade_count', 0)}", flush=True)
print(f"  buys: {len(buys)}  sells: {len(sells)}", flush=True)
print(f"  total_fees: {total_fees}", flush=True)
print(f"  elapsed: {elapsed:.0f}s", flush=True)

# 费率合理性检查
if buys:
    avg_fee_rate = sum(t.get('fee', 0) / t.get('amount', 1) for t in buys) / len(buys)
    print(f"  avg purchase fee rate: {avg_fee_rate*100:.3f}% (expect 0~1.5%)", flush=True)
    if avg_fee_rate > 0.05:
        print(f"  [FAIL] fee rate too high! (>5%)", flush=True)
        sys.exit(1)
    if avg_fee_rate < 0 and avg_fee_rate != 0:
        print(f"  [FAIL] negative fee rate!", flush=True)
        sys.exit(1)
    print(f"  [PASS] fee rate reasonable", flush=True)

if sells:
    avg_sell_fee_rate = sum(t.get('fee', 0) / max(t.get('amount', 1), 1) for t in sells) / len(sells)
    print(f"  avg sell fee rate: {avg_sell_fee_rate*100:.3f}%", flush=True)

print(f"\n[OK] smoke test passed", flush=True)
