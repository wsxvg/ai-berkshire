#!/usr/bin/env python3
"""全量参数自动扫描 - 找最佳组合"""
import sys, json, itertools
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
        dds = [d["total"] for d in r.get("daily_values",[])]
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
        return None

all_results = []

# ═══ 基线 ═══
r = run_one("基线-排末3")
if r: all_results.append(r)

# ═══ 1. 行业分散扫描 ═══
for sector in [20, 22, 25, 28, 30, 35]:
    r = run_one(f"行业{sector}%", max_sector_pct=sector)
    if r: all_results.append(r)

# ═══ 2. QDII+行业组合 ═══
for sector in [25, 30]:
    for qdii in [30, 40, 50]:
        r = run_one(f"行业{sector}+QDII{qdii}", max_sector_pct=sector, max_qdii_pct=qdii)
        if r: all_results.append(r)

# ═══ 3. 动量+分散组合 ═══
for sector in [25, 30]:
    for mom in [1.8, 2.0]:
        r = run_one(f"M{mom}+行业{sector}", momentum_sell=mom, max_sector_pct=sector)
        if r: all_results.append(r)

# ═══ 4. 动量+分散+止盈组合 ═══
for mom in [1.8, 2.0]:
    for tp in [30, 50]:
        for sector in [25, 30]:
            name = f"M{mom}+TP{tp}+行业{sector}"
            r = run_one(name, momentum_sell=mom, take_profit_pct=tp, profit_mode='half', max_sector_pct=sector)
            if r: all_results.append(r)

# ═══ 5. 止盈+分散组合 ═══
for tp in [30, 50]:
    for sector in [25, 30]:
        name = f"TP{tp}+行业{sector}"
        r = run_one(name, take_profit_pct=tp, profit_mode='half', max_sector_pct=sector)
        if r: all_results.append(r)

# ═══ 6. 动量不同阈值+行业25 ═══
for mom in [1.6, 1.7, 1.8, 1.9, 2.0, 2.1]:
    r = run_one(f"M{mom}+行业25", momentum_sell=mom, max_sector_pct=25)
    if r: all_results.append(r)

# ═══ 最终排名 ═══
print(f"\n{'='*110}")
print("FINAL RANKING (all strategies)")
print(f"{'='*110}")
print(f"{'Strategy':40s} {'Ret':>7s} {'Profit':>8s} {'DD':>7s} {'Sharpe':>7s} {'Trades':>5s} {'Hold':>4s}")
print(f"{'-'*110}")
sorted_results = sorted(all_results, key=lambda x: x['sharpe'], reverse=True)
for r in sorted_results:
    print(f"{r['name']:40s} {r['return']:>+7.2f}% {r['profit']:>8.0f} {r['dd']:>7.2f}% {r['sharpe']:>7.2f} {r['trades']:>5d} {r['holdings']:>4d}")

# 按净赚排名
print(f"\n{'='*110}")
print("BY PROFIT")
print(f"{'='*110}")
for r in sorted(all_results, key=lambda x: x['profit'], reverse=True)[:15]:
    print(f"{r['name']:40s} {r['return']:>+7.2f}% {r['profit']:>8.0f} {r['dd']:>7.2f}% {r['sharpe']:>7.2f} {r['trades']:>5d}")

# 最夏普最高+回撤最低的综合
print(f"\n{'='*110}")
print("BEST COMBINATION (Sharpe > 10 AND DD < 10%)")
print(f"{'='*110}")
for r in sorted_results:
    if r['sharpe'] > 10 and r['dd'] < 10:
        print(f"{r['name']:40s} {r['return']:>+7.2f}% {r['profit']:>8.0f} {r['dd']:>7.2f}% {r['sharpe']:>7.2f}")

out = Path(__file__).resolve().parent.parent / "backtest" / "reports" / "full_scan.json"
out.parent.mkdir(parents=True, exist_ok=True)
json.dump(sorted_results, open(out,'w',encoding='utf-8'), ensure_ascii=False, indent=2)
print(f"\nSaved to {out}")