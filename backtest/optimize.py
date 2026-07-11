#!/usr/bin/env python3
"""回测参数优化器 — 系统搜索最优参数组合。
不作弊：只用历史真实数据，不用未来信息。
"""
import sys, json, itertools, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backtest.engine.backtest import run_backtest

BASE_CFG = {
    'start_date': '2026-01-05', 'end_date': '2026-06-30',
    'initial_cash': 0,
    'monthly_injection': 2500,  # DCA场景
    'weights': {'quality':25,'cost':20,'manager':20,'momentum':15,'smart_money':20},
    'min_score': 3.3,
    'take_profit_pct': 30,
    'take_profit_sell_pct': 0.5,
    'stop_loss_pct': -15,
    'momentum_sell': 2.0,
    'max_position_pct': 25,
    'kelly_cap': 0.2,
    'cash_reserve_pct': 0.2,
}

def test_params(**overrides):
    cfg = dict(BASE_CFG)
    cfg.update(overrides)
    try:
        r = run_backtest(cfg)
        result = {
            'return': r['total_return'],
            'dd': r['max_drawdown'],
            'trades': r['trade_count'],
            'fees': r.get('total_fees', 0),
            'holdings': r['final_holdings'],
            'sharpe': r['total_return'] / max(r['max_drawdown'], 1) if r['max_drawdown'] > 0 else 0,
        }
        return result
    except Exception as e:
        import traceback
        print(f"  ERROR: {e}")
        print(f"  {traceback.format_exc()[:200]}")
        return {'return': -999, 'dd': 999, 'trades': 0, 'fees': 0, 'holdings': 0, 'sharpe': -999}

def grid_search(param_name, values, fixed_params=None):
    """对单个参数做网格搜索，其他参数固定。"""
    results = []
    for v in values:
        p = dict(fixed_params or {})
        p[param_name] = v
        r = test_params(**p)
        r['param'] = param_name
        r['value'] = v
        results.append(r)
        status = "OK" if r['return'] > -999 else "FAIL"
        print(f"  {param_name}={v:>8}  ret={r['return']:>+7.2f}%  dd={r['dd']:>5.2f}%  sharp={r['sharpe']:>5.2f}  trades={r['trades']:>3d}  {status}")
    return results

def find_best(results):
    """按夏普比率找最优。夏普 = 收益/回撤。"""
    best = max(results, key=lambda r: r['sharpe'])
    return best

print("=" * 70)
print("Backtest Parameter Optimizer (DCA 2500/month)")
print("=" * 70)

# Phase 1: Buy threshold
print("\n--- Phase 1: min_score (buy threshold) ---")
r1 = grid_search("min_score", [2.5, 3.0, 3.3, 3.5, 3.7, 4.0])
best_score = find_best(r1)['value']
print(f"  >> Best min_score = {best_score}")

# Phase 2: Take profit
print("\n--- Phase 2: take_profit_pct ---")
r2 = grid_search("take_profit_pct", [15, 20, 25, 30, 40, 50], {"min_score": best_score})
best_tp = find_best(r2)['value']
print(f"  >> Best take_profit = {best_tp}%")

# Phase 3: Take profit sell fraction
print("\n--- Phase 3: take_profit_sell_pct ---")
r3 = grid_search("take_profit_sell_pct", [0.25, 0.33, 0.4, 0.5, 0.6],
                 {"min_score": best_score, "take_profit_pct": best_tp})
best_tps = find_best(r3)['value']
print(f"  >> Best take_profit_sell = {best_tps}")

# Phase 4: Stop loss
print("\n--- Phase 4: stop_loss_pct ---")
r4 = grid_search("stop_loss_pct", [-8, -10, -15, -20, -25, -30],
                 {"min_score": best_score, "take_profit_pct": best_tp, "take_profit_sell_pct": best_tps})
best_sl = find_best(r4)['value']
print(f"  >> Best stop_loss = {best_sl}%")

# Phase 5: Momentum sell
print("\n--- Phase 5: momentum_sell threshold ---")
r5 = grid_search("momentum_sell", [1.0, 1.5, 2.0, 2.5, 3.0],
                 {"min_score": best_score, "take_profit_pct": best_tp,
                  "take_profit_sell_pct": best_tps, "stop_loss_pct": best_sl})
best_mom = find_best(r5)['value']
print(f"  >> Best momentum_sell = {best_mom}")

# Phase 6: Cash reserve
print("\n--- Phase 6: cash_reserve_pct ---")
r6 = grid_search("cash_reserve_pct", [0.05, 0.1, 0.15, 0.2, 0.25, 0.3],
                 {"min_score": best_score, "take_profit_pct": best_tp,
                  "take_profit_sell_pct": best_tps, "stop_loss_pct": best_sl,
                  "momentum_sell": best_mom})
best_cr = find_best(r6)['value']
print(f"  >> Best cash_reserve = {best_cr}")

# Phase 7: Max position
print("\n--- Phase 7: max_position_pct ---")
r7 = grid_search("max_position_pct", [10, 15, 20, 25, 30, 40],
                 {"min_score": best_score, "take_profit_pct": best_tp,
                  "take_profit_sell_pct": best_tps, "stop_loss_pct": best_sl,
                  "momentum_sell": best_mom, "cash_reserve_pct": best_cr})
best_mp = find_best(r7)['value']
print(f"  >> Best max_position = {best_mp}%")

# Phase 8: Kelly cap
print("\n--- Phase 8: kelly_cap ---")
r8 = grid_search("kelly_cap", [0.1, 0.15, 0.2, 0.25, 0.3, 0.4],
                 {"min_score": best_score, "take_profit_pct": best_tp,
                  "take_profit_sell_pct": best_tps, "stop_loss_pct": best_sl,
                  "momentum_sell": best_mom, "cash_reserve_pct": best_cr,
                  "max_position_pct": best_mp})
best_kc = find_best(r8)['value']
print(f"  >> Best kelly_cap = {best_kc}")

# Phase 9: Weight scan (try a few weight combos)
print("\n--- Phase 9: Weight combos ---")
opt_params = {"min_score": best_score, "take_profit_pct": best_tp,
              "take_profit_sell_pct": best_tps, "stop_loss_pct": best_sl,
              "momentum_sell": best_mom, "cash_reserve_pct": best_cr,
              "max_position_pct": best_mp, "kelly_cap": best_kc}
w_combos = [
    ("Default",      {'quality':25,'cost':20,'manager':20,'momentum':15,'smart_money':20}),
    ("Equal",        {'quality':20,'cost':20,'manager':20,'momentum':20,'smart_money':20}),
    ("HeavyQ",       {'quality':35,'cost':15,'manager':20,'momentum':15,'smart_money':15}),
    ("HeavyMomentum",{'quality':20,'cost':15,'manager':15,'momentum':35,'smart_money':15}),
    ("HeavyCost",    {'quality':20,'cost':35,'manager':15,'momentum':15,'smart_money':15}),
    ("HeavySM",      {'quality':20,'cost':15,'manager':15,'momentum':15,'smart_money':35}),
    ("Balanced",     {'quality':25,'cost':20,'manager':20,'momentum':20,'smart_money':15}),
]
best_w = None
best_w_ret = -999
for name, w in w_combos:
    p = dict(opt_params)
    p['weights'] = w
    r = test_params(**p)
    s = f"  {name:15s}  ret={r['return']:>+7.2f}%  dd={r['dd']:>5.2f}%  sharp={r['sharpe']:>5.2f}  trades={r['trades']:>3d}"
    print(s)
    if r['sharpe'] > best_w_ret:
        best_w_ret = r['sharpe']
        best_w = w
opt_params['weights'] = best_w

# Final result
print("\n" + "=" * 70)
print("BEST PARAMETERS FOUND")
print("=" * 70)
for k, v in opt_params.items():
    if k != 'weights':
        print(f"  {k}: {v}")
    else:
        print(f"  weights: {v}")

final = test_params(**opt_params)
print(f"\nBEST RESULT (DCA 2500/month):")
print(f"  Return:  {final['return']:+.2f}%")
print(f"  MaxDD:   {final['dd']:.2f}%")
print(f"  Sharpe:  {final['sharpe']:.2f}")
print(f"  Trades:  {final['trades']}")
print(f"  Fees:    {final['fees']:.2f}")
print(f"  Holdings:{final['holdings']}")

# Also run one-time 10k with same params
print("\n--- Same params, One-time 10k ---")
ot = test_params(**dict(opt_params, initial_cash=10000, monthly_injection=0))
print(f"  Return:  {ot['return']:+.2f}%")
print(f"  MaxDD:   {ot['dd']:.2f}%")
print(f"  Sharpe:  {ot['sharpe']:.2f}")

# Save results
results = {
    "best_params": opt_params,
    "dca_2500": final,
    "one_time_10k": ot,
}
out_path = Path(__file__).parent.parent / "backtest" / "reports" / "optimization_result.json"
out_path.parent.mkdir(parents=True, exist_ok=True)
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)
print(f"\nSaved to {out_path}")