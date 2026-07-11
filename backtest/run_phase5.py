#!/usr/bin/env python3
"""Phase 5: 排名/共识/优先 过滤"""
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

# ═══════════════════════════════════════════
# 共识过滤（升级版）
# ═══════════════════════════════════════════
print("=== 共识过滤 ===")
for c in [2, 3, 4]:
    r = run_one(f"共识{c}", min_consensus=c)
    if r: results.append(r); print(f"  共识{c}: 收益{r['return']:>+7.2f}%  净赚{r['profit']:>7.0f}  回撤{r['dd']:>5.2f}%  夏普{r['sharpe']:>6.2f}")

# ═══════════════════════════════════════════
# Top-N 过滤（每天只买得分最高的N只）
# ═══════════════════════════════════════════
print("\n=== Top-N 过滤 ===")
for n in [2, 3, 5, 8, 10]:
    r = run_one(f"Top{n}", top_n=n)
    if r: results.append(r); print(f"  Top{n}: 收益{r['return']:>+7.2f}%  净赚{r['profit']:>7.0f}  回撤{r['dd']:>5.2f}%  夏普{r['sharpe']:>6.2f}")

# ═══════════════════════════════════════════
# Top-N% 过滤（每天只买得分最高的前N%）
# ═══════════════════════════════════════════
print("\n=== Top-N% 过滤 ===")
for pct in [25, 33, 50, 66, 75]:
    r = run_one(f"Top{pct}%", top_n_pct=pct)
    if r: results.append(r); print(f"  Top{pct}%: 收益{r['return']:>+7.2f}%  净赚{r['profit']:>7.0f}  回撤{r['dd']:>5.2f}%  夏普{r['sharpe']:>6.2f}")

# ═══════════════════════════════════════════
# 共识优先
# ═══════════════════════════════════════════
print("\n=== 共识优先 ===")
r = run_one("C优先", consensus_priority=True)
if r: results.append(r); print(f"  C优先: 收益{r['return']:>+7.2f}%  净赚{r['profit']:>7.0f}  回撤{r['dd']:>5.2f}%  夏普{r['sharpe']:>6.2f}")

# ═══════════════════════════════════════════
# Top-N + 共识 + 止盈 组合
# ═══════════════════════════════════════════
print("\n=== 组合 ===")
for n in [3, 5]:
    for tp in [30, 50]:
        label = f"Top{n}+TP{tp}"
        r = run_one(label, top_n=n, take_profit_pct=tp, profit_mode='half')
        if r: results.append(r); print(f"  {label}: 收益{r['return']:>+7.2f}%  净赚{r['profit']:>7.0f}  回撤{r['dd']:>5.2f}%  夏普{r['sharpe']:>6.2f}")

for pct in [33, 50]:
    for tp in [30, 50]:
        label = f"Top{pct}%+TP{tp}"
        r = run_one(label, top_n_pct=pct, take_profit_pct=tp, profit_mode='half')
        if r: results.append(r); print(f"  {label}: 收益{r['return']:>+7.2f}%  净赚{r['profit']:>7.0f}  回撤{r['dd']:>5.2f}%  夏普{r['sharpe']:>6.2f}")

# ═══════════════════════════════════════════
# Top-N + 共识
# ═══════════════════════════════════════════
for n in [3, 5]:
    for c in [2, 3]:
        label = f"Top{n}+共识{c}"
        r = run_one(label, top_n=n, min_consensus=c)
        if r: results.append(r); print(f"  {label}: 收益{r['return']:>+7.2f}%  净赚{r['profit']:>7.0f}  回撤{r['dd']:>5.2f}%  夏普{r['sharpe']:>6.2f}")

# ═══════════════════════════════════════════
# 最终排名
# ═══════════════════════════════════════════
print(f"\n\n{'='*100}")
print("FINAL RANKING (按夏普)")
print(f"{'='*100}")
print(f"{'策略':30s} {'收益':>8s} {'净赚':>8s} {'回撤':>8s} {'夏普':>8s} {'交易':>5s} {'持仓':>4s}")
print(f"{'-'*100}")
for r in sorted(results, key=lambda x: x['sharpe'], reverse=True):
    print(f"{r['name']:30s} {r['return']:>+7.2f}% {r['profit']:>8.0f} {r['dd']:>7.2f}% {r['sharpe']:>7.2f} {r['trades']:>4d}  {r['holdings']:>3d}")

# 按净赚排名
print(f"\n\n{'='*100}")
print("按净赚排名")
print(f"{'='*100}")
for r in sorted(results, key=lambda x: x['profit'], reverse=True)[:15]:
    print(f"{r['name']:30s} {r['return']:>+7.2f}% {r['profit']:>8.0f} {r['dd']:>7.2f}% {r['sharpe']:>7.2f} {r['trades']:>4d}  {r['holdings']:>3d}")

out = Path(__file__).resolve().parent.parent / "backtest" / "reports" / "phase5_results.json"
out.parent.mkdir(parents=True, exist_ok=True)
with open(out, "w", encoding="utf-8") as f:
    json.dump({"results": sorted(results, key=lambda x: x['sharpe'], reverse=True)},
              f, ensure_ascii=False, indent=2)
print(f"\n保存到 {out}")