#!/usr/bin/env python3
"""Phase 7: 加权共识 + 最终组合"""
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

# 按30天平均收益的权重映射
PLAYER_WEIGHTS = {
    '11953905': 2.0,  # +16.36%  🥇
    '11979538': 2.0,  # +13.99%  🥈
    '3546208': 1.5,   # +12.49%  🥉
    '3642504': 1.5,   # +9.52%
    '2690580': 1.0,   # +8.59%
    '10458335': 1.0,  # +7.29%
    '4063754': 1.0,   # +6.38%
    '3748946': 1.0,   # +6.00%
    '4968958': 0.5,   # +5.63%
    '16020895': 0.5,  # +4.57%
    '14345330': 0.5,  # +4.19%
}
EXCLUDE_BOTTOM3 = [4968958, 16020895, 14345330]

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

# ═══ 加权共识 ═══
print("=== 加权共识 ===")
r = run_one("加权共识2", player_weights=PLAYER_WEIGHTS, use_weighted_consensus=True, min_consensus=2)
if r: results.append(r); print(f"  加权共识2: 收益{r['return']:>+7.2f}%  净赚{r['profit']:>7.0f}  回撤{r['dd']:>5.2f}%  夏普{r['sharpe']:>6.2f}")

r = run_one("加权共识3", player_weights=PLAYER_WEIGHTS, use_weighted_consensus=True, min_consensus=3)
if r: results.append(r); print(f"  加权共识3: 收益{r['return']:>+7.2f}%  净赚{r['profit']:>7.0f}  回撤{r['dd']:>5.2f}%  夏普{r['sharpe']:>6.2f}")

# ═══ 加权共识+止盈 ═══
for tp in [30, 50]:
    r = run_one(f"加权共识2+TP{tp}", player_weights=PLAYER_WEIGHTS, use_weighted_consensus=True,
                min_consensus=2, take_profit_pct=tp, profit_mode='half')
    if r: results.append(r); print(f"  加权共识2+TP{tp}: 收益{r['return']:>+7.2f}%  净赚{r['profit']:>7.0f}  回撤{r['dd']:>5.2f}%")

# ═══ 排除末3+各参数 ═══
for tp in [30, 40, 50]:
    r = run_one(f"排除末3+TP{tp}", exclude_uids=EXCLUDE_BOTTOM3, take_profit_pct=tp, profit_mode='half')
    if r: results.append(r); print(f"  排除末3+TP{tp}: 收益{r['return']:>+7.2f}%  净赚{r['profit']:>7.0f}  回撤{r['dd']:>5.2f}%  夏普{r['sharpe']:>6.2f}")

# ═══ 排除末3+动量不同阈值 ═══
for mom in [1.8, 2.0, 2.2]:
    r = run_one(f"排除末3+M{mom}", exclude_uids=EXCLUDE_BOTTOM3, momentum_sell=mom)
    if r: results.append(r); print(f"  排除末3+M{mom}: 收益{r['return']:>+7.2f}%  净赚{r['profit']:>7.0f}  回撤{r['dd']:>5.2f}%  夏普{r['sharpe']:>6.2f}")

# ═══ 排除末3+动量+止盈30 ═══
for mom in [1.8, 2.0]:
    r = run_one(f"排除末3+M{mom}+TP30", exclude_uids=EXCLUDE_BOTTOM3, momentum_sell=mom,
                take_profit_pct=30, profit_mode='half')
    if r: results.append(r); print(f"  排除末3+M{mom}+TP30: 收益{r['return']:>+7.2f}%  净赚{r['profit']:>7.0f}  回撤{r['dd']:>5.2f}%  夏普{r['sharpe']:>6.2f}")

# 基线
r = run_one("基线-全部跟投")
if r: results.append(r); print(f"  基线-全部跟投: 收益{r['return']:>+7.2f}%  净赚{r['profit']:>7.0f}  回撤{r['dd']:>5.2f}%  夏普{r['sharpe']:>6.2f}")

r = run_one("排除末3", exclude_uids=EXCLUDE_BOTTOM3)
if r: results.append(r); print(f"  排除末3: 收益{r['return']:>+7.2f}%  净赚{r['profit']:>7.0f}  回撤{r['dd']:>5.2f}%  夏普{r['sharpe']:>6.2f}")

# ═══ 最终排名 ═══
print(f"\n\n{'='*100}")
print("Phase 7 FINAL")
print(f"{'='*100}")
print(f"{'策略':36s} {'收益':>8s} {'净赚':>8s} {'回撤':>8s} {'夏普':>8s} {'交易':>5s}")
print(f"{'-'*100}")
for r in sorted(results, key=lambda x: x['sharpe'], reverse=True):
    print(f"{r['name']:36s} {r['return']:>+7.2f}% {r['profit']:>8.0f} {r['dd']:>7.2f}% {r['sharpe']:>7.2f} {r['trades']:>4d}")

out = Path(__file__).resolve().parent.parent / "backtest" / "reports" / "phase7_results.json"
out.parent.mkdir(parents=True, exist_ok=True)
json.dump({"results": sorted(results, key=lambda x: x['sharpe'], reverse=True)}, open(out,'w',encoding='utf-8'), ensure_ascii=False, indent=2)
print(f"\n保存到 {out}")