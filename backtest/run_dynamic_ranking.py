#!/usr/bin/env python3
"""动态大佬排分参数扫描"""
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
    # 每次重置函数静态变量
    run_backtest._last_rank_date = None
    run_backtest._rank_weights = {}
    run_backtest._rank_excluded = set()
    try:
        r = run_backtest(cfg)
        total_in = r.get('monthly_injections',0) + 3000
        return {
            "name": name,
            "return": r['total_return'],
            "profit": r['daily_values'][-1]['total'] - total_in,
            "dd": r['max_drawdown'],
            "trades": r['trade_count'],
            "holdings": r['final_holdings'],
            "sharpe": r['total_return'] / max(r['max_drawdown'], 1),
            "fees": r.get('total_fees', 0),
        }
    except Exception as e:
        print(f"  FAILED {name}: {e}")
        import traceback; traceback.print_exc()
        return None

results = []
bm = "\n基线: +107.03%, 净赚64,217, 回撤9.04%\n"

# ═══ 窗口大小 ═══
print("=== 动态排分: 窗口大小 ===")
for window in [30, 60, 90, 180, 365]:
    name = f"动态-窗口{window}d"
    r = run_one(name, dynamic_ranking=True, ranking_window=window,
                ranking_fwd_days=30, ranking_min_buys=3, ranking_recalc_days=30)
    if r: results.append(r); print(f"  窗口{window}d: 收益{r['return']:+7.2f}%  净赚{r['profit']:>7.0f}  回撤{r['dd']:.2f}%  夏普{r['sharpe']:.2f}")

# ═══ 向前收益天数 ═══
print("\n=== 动态排分: 向前收益天数 ===")
for fwd in [7, 14, 30, 60]:
    name = f"动态-前望{fwd}d"
    r = run_one(name, dynamic_ranking=True, ranking_window=90,
                ranking_fwd_days=fwd, ranking_min_buys=3, ranking_recalc_days=30)
    if r: results.append(r); print(f"  前望{fwd}d: 收益{r['return']:+7.2f}%  净赚{r['profit']:>7.0f}  回撤{r['dd']:.2f}%  夏普{r['sharpe']:.2f}")

# ═══ 最少买入次数 ═══
print("\n=== 动态排分: 最少买入次数 ===")
for mb in [3, 5, 10]:
    name = f"动态-最少{mb}笔"
    r = run_one(name, dynamic_ranking=True, ranking_window=90,
                ranking_fwd_days=30, ranking_min_buys=mb, ranking_recalc_days=30)
    if r: results.append(r); print(f"  最少{mb}笔: 收益{r['return']:+7.2f}%  净赚{r['profit']:>7.0f}  回撤{r['dd']:.2f}%  夏普{r['sharpe']:.2f}")

# ═══ 重算频率 ═══
print("\n=== 动态排分: 重算频率 ===")
for recalc in [10, 30, 60, 90]:
    name = f"动态-每{recalc}d"
    r = run_one(name, dynamic_ranking=True, ranking_window=90,
                ranking_fwd_days=30, ranking_min_buys=3, ranking_recalc_days=recalc)
    if r: results.append(r); print(f"  每{recalc}d: 收益{r['return']:+7.2f}%  净赚{r['profit']:>7.0f}  回撤{r['dd']:.2f}%  夏普{r['sharpe']:.2f}")

# ═══ 权重阈值映射 ═══
# 测试不同的权重映射策略（通过修改权重计算函数不方便，先用静态权重模拟）
print("\n=== 手动权重对比 ===")
# 对比之前的最佳静态方案
for label, uids in [("排除末3", [4968958, 16020895, 14345330]),
                    ("排除末5", [4968958, 16020895, 14345330, 3748946, 4063754])]:
    r = run_one(label, exclude_uids=uids)
    if r: results.append(r); print(f"  {label}: 收益{r['return']:+7.2f}%  净赚{r['profit']:>7.0f}  回撤{r['dd']:.2f}%  夏普{r['sharpe']:.2f}")

# 基线
r = run_one("基线-全部跟投")
if r: results.append(r); print(f"  基线: 收益{r['return']:+7.2f}%  净赚{r['profit']:>7.0f}  回撤{r['dd']:.2f}%")

print(f"\n\n{'='*100}")
print("动态大佬排分 FINAL")
print(f"{'='*100}")
print(f"{'策略':24s} {'收益':>8s} {'净赚':>8s} {'回撤':>8s} {'夏普':>8s} {'交易':>5s}")
print(f"{'-'*100}")
for r in sorted(results, key=lambda x: x['sharpe'], reverse=True):
    print(f"{r['name']:24s} {r['return']:>+7.2f}% {r['profit']:>8.0f} {r['dd']:>7.2f}% {r['sharpe']:>7.2f} {r['trades']:>4d}")

out = Path(__file__).resolve().parent.parent / "backtest" / "reports" / "dynamic_ranking.json"
out.parent.mkdir(parents=True, exist_ok=True)
json.dump({"results": sorted(results, key=lambda x: x['sharpe'], reverse=True)},
          open(out,'w',encoding='utf-8'), ensure_ascii=False, indent=2)
print(f"\n保存到 {out}")