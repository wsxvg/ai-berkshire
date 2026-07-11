#!/usr/bin/env python3
"""Phase 6: 大佬筛选 + DCA 优化"""
import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backtest.engine.backtest import run_backtest

BASE = {'start_date':'2025-01-05','end_date':'2026-07-01',
        'initial_cash':3000, 'monthly_injection':3000,
        'weights':{'quality':25,'cost':20,'manager':20,'momentum':15,'smart_money':20}}
K_BASE = {'min_score':0.0, 'no_stop_loss':True, 'take_profit_pct':1000,
          'profit_mode':'half', 'cost_penalty':0, 'min_consensus':2,
          'fund_type_filter':'all', 'momentum_sell':0, 'max_position_pct':100}

# UID性能排名（按30天平均收益）
# TOP3: 11953905(+16.4%), 11979538(+14.0%), 3546208(+12.5%)
# BOTTOM3: 4968958(+5.6%), 16020895(+4.6%), 14345330(+4.2%)
TOP3 = [11953905, 11979538, 3546208]
TOP5 = TOP3 + [3642504, 2690580]
TOP8 = TOP5 + [10458335, 4063754, 3748946]
EXCLUDE_BOTTOM3 = [4968958, 16020895, 14345330]
EXCLUDE_BOTTOM5 = [4968958, 16020895, 14345330, 3748946, 4063754]
EXCLUDE_BOTTOM1 = [14345330]

def run_one(name, **overrides):
    cfg = dict(BASE)
    cfg.update(K_BASE)
    cfg.update(overrides)
    try:
        r = run_backtest(cfg)
        total_in = r.get('monthly_injections', 0) + cfg.get('initial_cash', 0)
        return {
            "name": name,
            "return": r['total_return'],
            "final_val": r['daily_values'][-1]['total'] if r.get('daily_values') else 0,
            "profit": (r['daily_values'][-1]['total'] - total_in) if r.get('daily_values') else 0,
            "dd": r['max_drawdown'],
            "trades": r['trade_count'],
            "holdings": r['final_holdings'],
            "sharpe": r['total_return'] / max(r['max_drawdown'], 1),
            "fees": r.get('total_fees', 0),
        }
    except Exception as e:
        print(f"  FAILED {name}: {e}")
        return None

results = []

# ═══ 大佬筛选 ═══
print("=== 大佬筛选 ===")
for label, uids in [("TOP3-跟投", TOP3), ("TOP5-跟投", TOP5), ("TOP8-跟投", TOP8),
                    ("排除末3", EXCLUDE_BOTTOM3), ("排除末5", EXCLUDE_BOTTOM5), ("排除末1", EXCLUDE_BOTTOM1)]:
    r = run_one(label, exclude_uids=uids)
    if r: results.append(r); print(f"  {label}: 收益{r['return']:>+7.2f}%  净赚{r['profit']:>7.0f}  回撤{r['dd']:>5.2f}%  夏普{r['sharpe']:>6.2f}  交易{r['trades']:>3d}")

# ═══ 大佬筛选+止盈 ═══
print("\n=== 大佬筛选+止盈 ===")
for uids, label in [(TOP3, "TOP3"), (TOP5, "TOP5"), (EXCLUDE_BOTTOM3, "排除末3")]:
    for tp in [30, 50]:
        name = f"{label}+TP{tp}"
        r = run_one(name, exclude_uids=uids, take_profit_pct=tp, profit_mode='half')
        if r: results.append(r); print(f"  {name}: 收益{r['return']:>+7.2f}%  净赚{r['profit']:>7.0f}  回撤{r['dd']:>5.2f}%  夏普{r['sharpe']:>6.2f}")

# ═══ 大佬筛选+共识3 ═══
print("\n=== 大佬筛选+共识3 ===")
for uids, label in [(TOP3, "TOP3"), (TOP5, "TOP5"), (EXCLUDE_BOTTOM3, "排除末3")]:
    name = f"{label}+共识3"
    r = run_one(name, exclude_uids=uids, min_consensus=3)
    if r: results.append(r); print(f"  {name}: 收益{r['return']:>+7.2f}%  净赚{r['profit']:>7.0f}  回撤{r['dd']:>5.2f}%  夏普{r['sharpe']:>6.2f}")

# ═══ 大佬筛选+动量+止盈 ═══
print("\n=== 大佬筛选+动量+止盈 ===")
for uids, label in [(TOP3, "TOP3"), (TOP5, "TOP5"), (EXCLUDE_BOTTOM3, "排除末3")]:
    name = f"{label}+M20+TP30"
    r = run_one(name, exclude_uids=uids, momentum_sell=2.0,
                take_profit_pct=30, profit_mode='half')
    if r: results.append(r); print(f"  {name}: 收益{r['return']:>+7.2f}%  净赚{r['profit']:>7.0f}  回撤{r['dd']:>5.2f}%  夏普{r['sharpe']:>6.2f}")

# ═══ 最终排名 ═══
bm = "(全部11人+107%基准)"
print(f"\n\n{'='*100}")
print(f"大佬筛选+DCA优化 FINAL (基准: 跟投全部人 +107%, 净赚64,217, 回撤9.04%)")
print(f"{'='*100}")
print(f"{'策略':36s} {'收益':>8s} {'净赚':>8s} {'回撤':>8s} {'夏普':>8s} {'交易':>5s}")
print(f"{'-'*100}")
for r in sorted(results, key=lambda x: x['sharpe'], reverse=True):
    print(f"{r['name']:36s} {r['return']:>+7.2f}% {r['profit']:>8.0f} {r['dd']:>7.2f}% {r['sharpe']:>7.2f} {r['trades']:>4d}")

print(f"\n{'='*100}")
print(f"按净赚排名 TOP10")
print(f"{'='*100}")
for r in sorted(results, key=lambda x: x['profit'], reverse=True)[:10]:
    print(f"{r['name']:36s} {r['return']:>+7.2f}% {r['profit']:>8.0f} {r['dd']:>7.2f}% {r['sharpe']:>7.2f}")

out = Path(__file__).resolve().parent.parent / "backtest" / "reports" / "phase6_results.json"
out.parent.mkdir(parents=True, exist_ok=True)
json.dump({"results": sorted(results, key=lambda x: x['sharpe'], reverse=True)}, open(out,'w',encoding='utf-8'), ensure_ascii=False, indent=2)
print(f"\n保存到 {out}")