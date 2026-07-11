#!/usr/bin/env python3
"""组合分散参数回测"""
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

EXCLUDE_UIDS = [4968958, 16020895, 14345330]

def run_one(name, **overrides):
    cfg = dict(BASE)
    cfg.update(K_BASE)
    cfg.update({'exclude_uids': EXCLUDE_UIDS})
    cfg.update(overrides)
    run_backtest._last_rank_date = None
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
        }
    except Exception as e:
        print(f"  FAILED {name}: {e}")
        return None

results = []

# ═══ 行业分散限制 ═══
print("=== 行业分散 ===")
for limit in [20, 25, 30, 35, 40, 50]:
    name = f"排末3+行业{limit}%"
    r = run_one(name, max_sector_pct=limit)
    if r: results.append(r); print(f"  行业{limit}%: 收益{r['return']:+7.2f}%  净赚{r['profit']:>7.0f}  回撤{r['dd']:.2f}%  夏普{r['sharpe']:.2f}  持仓{r['holdings']}")

# ═══ QDII限制 ═══
print("\n=== QDII限制 ===")
for limit in [20, 30, 40, 50]:
    name = f"排末3+QDII{limit}%"
    r = run_one(name, max_qdii_pct=limit)
    if r: results.append(r); print(f"  QDII{limit}%: 收益{r['return']:+7.2f}%  净赚{r['profit']:>7.0f}  回撤{r['dd']:.2f}%  夏普{r['sharpe']:.2f}")

# ═══ 行业+QDII组合 ═══
print("\n=== 行业+QDII组合 ===")
for sector in [25, 30, 35]:
    for qdii in [30, 40, 50]:
        name = f"排末3+行业{sector}+QDII{qdii}"
        r = run_one(name, max_sector_pct=sector, max_qdii_pct=qdii)
        if r: results.append(r); print(f"  行业{sector}+QDII{qdii}: 收益{r['return']:+7.2f}%  净赚{r['profit']:>7.0f}  回撤{r['dd']:.2f}%  夏普{r['sharpe']:.2f}")

# 基线
r = run_one("排末3(基线)", exclude_uids=EXCLUDE_UIDS)
if r: results.append(r); print(f"\n  基线(排末3): 收益{r['return']:+7.2f}%  净赚{r['profit']:>7.0f}  回撤{r['dd']:.2f}%  夏普{r['sharpe']:.2f}")

print(f"\n\n{'='*100}")
print("组合分散 FINAL")
print(f"{'='*100}")
print(f"{'策略':36s} {'收益':>8s} {'净赚':>8s} {'回撤':>8s} {'夏普':>8s} {'持仓':>5s}")
print(f"{'-'*100}")
for r in sorted(results, key=lambda x: x['sharpe'], reverse=True):
    print(f"{r['name']:36s} {r['return']:>+7.2f}% {r['profit']:>8.0f} {r['dd']:>7.2f}% {r['sharpe']:>7.2f} {r['holdings']:>4d}")

out = Path(__file__).resolve().parent.parent / "backtest" / "reports" / "diversification.json"
out.parent.mkdir(parents=True, exist_ok=True)
json.dump({"results": sorted(results, key=lambda x: x['sharpe'], reverse=True)},
          open(out,'w',encoding='utf-8'), ensure_ascii=False, indent=2)
print(f"\n保存到 {out}")