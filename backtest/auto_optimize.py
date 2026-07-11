#!/usr/bin/env python3
"""Phase 1-4: 自动寻优回测流水线"""
import sys, json, itertools, time
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
        return None

results = []

# ═══════════════════════════════════════════
# Phase 1: 门槛扫描 (min_score 0→3.0)
# ═══════════════════════════════════════════
print("="*60)
print("Phase 1: 门槛扫描")
print("="*60)
for thresh in [0, 0.5, 1.0, 1.5, 2.0, 2.3, 2.5, 2.7, 3.0]:
    name = f"门槛{thresh}"
    cfg = {'min_score':thresh}
    r = run_one(name, **cfg)
    if r:
        results.append(r)
        print(f"  {name}: 收益{r['return']:>+7.2f}%  净赚{r['profit']:>7.0f}  回撤{r['dd']:>5.2f}%  夏普{r['sharpe']:>6.2f}  交易{r['trades']:>3d}  持仓{r['holdings']}")

# ═══════════════════════════════════════════
# Phase 2: 单维过滤
# ═══════════════════════════════════════════
print("\n"+"="*60)
print("Phase 2: 单维过滤（每个维度低于X就不买）")
print("="*60)

# 对每个维度设低门槛，只看这个维度能否奏效
dims = [
    ("质量", 2.0, {'weights':{'quality':100,'cost':0,'manager':0,'momentum':0,'smart_money':0}}),
    ("费用", 2.0, {'weights':{'quality':0,'cost':100,'manager':0,'momentum':0,'smart_money':0}}),
    ("经理", 2.0, {'weights':{'quality':0,'cost':0,'manager':100,'momentum':0,'smart_money':0}}),
    ("动量", 2.0, {'weights':{'quality':0,'cost':0,'manager':0,'momentum':100,'smart_money':0}}),
    ("聪明钱", 2.0, {'weights':{'quality':0,'cost':0,'manager':0,'momentum':0,'smart_money':100}}),
]
for dim_name, thresh, w in dims:
    name = f"单维-{dim_name}"
    r = run_one(name, min_score=thresh, **w)
    if r:
        results.append(r)
        print(f"  {name}: 收益{r['return']:>+7.2f}%  净赚{r['profit']:>7.0f}  回撤{r['dd']:>5.2f}%  夏普{r['sharpe']:>6.2f}  交易{r['trades']:>3d}  持仓{r['holdings']}")

# 单维+不同阈值（看看哪个维度区分度最高）
for thresh in [1.5, 2.0, 2.5, 3.0]:
    for dim_name, _, w in dims[:3]:  # 只测质量/费用/经理
        name = f"单维-{dim_name}{thresh}"
        r = run_one(name, min_score=thresh, **w)
        if r:
            results.append(r)
            print(f"  {name}: 收益{r['return']:>+7.2f}%  净赚{r['profit']:>7.0f}  回撤{r['dd']:>5.2f}%  夏普{r['sharpe']:>6.2f}  交易{r['trades']:>3d}  持仓{r['holdings']}")

# ═══════════════════════════════════════════
# Phase 3: 最佳维度组合
# ═══════════════════════════════════════════
print("\n"+"="*60)
print("Phase 3: 维度组合优化")
print("="*60)

# 基于Phase 1+2的最佳门槛（预计2.0左右），尝试不同权重组合
weight_combos = [
    ("默认25/20/20/15/20", {'quality':25,'cost':20,'manager':20,'momentum':15,'smart_money':20}),
    ("质量加重", {'quality':35,'cost':15,'manager':15,'momentum':15,'smart_money':20}),
    ("费用加重", {'quality':20,'cost':35,'manager':15,'momentum':15,'smart_money':15}),
    ("动量加重", {'quality':20,'cost':15,'manager':15,'momentum':35,'smart_money':15}),
    ("经理加重", {'quality':20,'cost':15,'manager':35,'momentum':15,'smart_money':15}),
    ("聪明钱加重", {'quality':20,'cost':15,'manager':15,'momentum':15,'smart_money':35}),
    ("质量+费用", {'quality':35,'cost':35,'manager':10,'momentum':10,'smart_money':10}),
    ("动量+聪明钱", {'quality':10,'cost':10,'manager':10,'momentum':35,'smart_money':35}),
    ("均衡", {'quality':20,'cost':20,'manager':20,'momentum':20,'smart_money':20}),
]

# 找Phase 1的最佳门槛
best_threshold = 2.0  # 预测2.0左右
for thresh in [1.5, 2.0, 2.5]:
    for name, w in weight_combos:
        label = f"组合{name}@门槛{thresh}"
        r = run_one(label, min_score=thresh, weights=w)
        if r:
            results.append(r)
            print(f"  {label}: 收益{r['return']:>+7.2f}%  净赚{r['profit']:>7.0f}  回撤{r['dd']:>5.2f}%  夏普{r['sharpe']:>6.2f}  交易{r['trades']:>3d}  持仓{r['holdings']}")

# ═══════════════════════════════════════════
# Phase 4: 最佳筛选+止盈优化
# ═══════════════════════════════════════════
print("\n"+"="*60)
print("Phase 4: 止盈优化")
print("="*60)

# 用Phase 3找到的最佳配置，调止盈
best_min_score = 2.0
best_weights = {'quality':25,'cost':20,'manager':20,'momentum':15,'smart_money':20}

for tp in [15, 20, 25, 30, 40, 50]:
    for mode in ['half', 'quarter']:
        label = f"止盈{tp}-{mode}"
        r = run_one(label, min_score=best_min_score, weights=best_weights,
                    take_profit_pct=tp, profit_mode=mode)
        if r:
            results.append(r)
            print(f"  {label}: 收益{r['return']:>+7.2f}%  净赚{r['profit']:>7.0f}  回撤{r['dd']:>5.2f}%  夏普{r['sharpe']:>6.2f}  交易{r['trades']:>3d}")

# 最佳配置+止损也试试
for sl in [-5, -8, -10, -15]:
    label = f"止损{abs(sl)}"
    r = run_one(label, min_score=best_min_score, weights=best_weights,
                no_stop_loss=False, stop_loss_pct=sl)
    if r:
        results.append(r)
        print(f"  {label}: 收益{r['return']:>+7.2f}%  净赚{r['profit']:>7.0f}  回撤{r['dd']:>5.2f}%  夏普{r['sharpe']:>6.2f}  交易{r['trades']:>3d}")

# 最佳配置+止盈+止损
for tp in [25, 30]:
    for sl in [-8, -10]:
        label = f"止盈{tp}+止损{abs(sl)}"
        r = run_one(label, min_score=best_min_score, weights=best_weights,
                    take_profit_pct=tp, profit_mode='half',
                    no_stop_loss=False, stop_loss_pct=sl)
        if r:
            results.append(r)
            print(f"  {label}: 收益{r['return']:>+7.2f}%  净赚{r['profit']:>7.0f}  回撤{r['dd']:>5.2f}%  夏普{r['sharpe']:>6.2f}  交易{r['trades']:>3d}")

# ═══════════════════════════════════════════
# 最终排名
# ═══════════════════════════════════════════
print(f"\n\n{'='*100}")
print("FINAL RANKING (按夏普)")
print(f"{'='*100}")
print(f"{'策略':40s} {'收益':>8s} {'净赚':>8s} {'回撤':>8s} {'夏普':>8s} {'交易':>5s}")
print(f"{'-'*100}")
for r in sorted(results, key=lambda x: x['sharpe'], reverse=True):
    print(f"{r['name']:40s} {r['return']:>+7.2f}% {r['profit']:>8.0f} {r['dd']:>7.2f}% {r['sharpe']:>7.2f} {r['trades']:>4d}")

# 按净赚排名
print(f"\n\n{'='*100}")
print("FINAL RANKING (按净赚)")
print(f"{'='*100}")
for r in sorted(results, key=lambda x: x['profit'], reverse=True)[:15]:
    print(f"{r['name']:40s} {r['return']:>+7.2f}% {r['profit']:>8.0f} {r['dd']:>7.2f}% {r['sharpe']:>7.2f} {r['trades']:>4d}")

# 保存
out = Path(__file__).resolve().parent.parent / "backtest" / "reports" / "auto_optimization.json"
out.parent.mkdir(parents=True, exist_ok=True)
with open(out, "w", encoding="utf-8") as f:
    json.dump({"results": sorted(results, key=lambda x: x['sharpe'], reverse=True),
               "period": "2025-01-05 ~ 2026-07-01", "monthly": 3000},
              f, ensure_ascii=False, indent=2)
print(f"\n保存到 {out}")