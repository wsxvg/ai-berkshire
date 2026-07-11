#!/usr/bin/env python3
"""Phase 4: 深度优化 — 围绕 weighted_consensus 突破口的系统探索"""
import sys, json, os, time, io
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backtest.engine.backtest import run_backtest

BASE = {
    "start_date": "2026-01-05", "end_date": "2026-06-30",
    "initial_cash": 100000,
    "weights": {"quality": 25, "cost": 20, "manager": 20, "momentum": 15, "smart_money": 20},
    "cost_penalty": 0, "top_n": 0, "top_n_pct": 0, "consensus_priority": False,
    "limit_boost": 0, "rebalance": True,
    "ranking_window": 90, "ranking_fwd_days": 30,
    "ranking_min_buys": 5, "ranking_recalc_days": 30,
    "verbose_ranking": False, "fund_type_filter": "all",
    "sell_consensus": 0,
}

def run(label, **kw):
    cfg = dict(BASE)
    cfg.update(kw)
    try:
        old_out = sys.stdout
        sys.stdout = io.StringIO()
        result = run_backtest(cfg)
        sys.stdout = old_out
        return {
            "label": label, "config": {k:v for k,v in cfg.items() if not isinstance(v,dict)},
            "total_return": float(result.get("total_return",0)),
            "max_drawdown": float(result.get("max_drawdown",0)),
            "benchmark": float(result.get("benchmark_return",0)),
            "trades": int(result.get("trade_count",0)),
            "final_value": float(result.get("final_value",0)),
            "fees": float(result.get("total_fees",0)),
            "final_holdings": int(result.get("final_holdings",0)),
            "excess": float(result.get("total_return",0)) - float(result.get("benchmark_return",0)),
        }
    except Exception as e:
        sys.stdout = old_out
        return {"label": label, "error": str(e)}

def show(r):
    if r.get("error"):
        print(f"  {r['label']}: ERROR {r['error']}")
    else:
        print(f"  {r['label']:25s}: Ret={r['total_return']:>+6.2f}% DD={r['max_drawdown']:>4.1f}% "
              f"Ex={r['excess']:>+6.2f}% Tr={r['trades']:3d} Hold={r['final_holdings']:2d} "
              f"Fee={r['fees']:>5.0f} Val={r['final_value']:>8.0f}")

print("=" * 70)
print("PHASE 4: Weighted Consensus Deep Dive")
print("=" * 70)

results = []

# ── 4A: Weighted consensus × min_score × consensus threshold ──
print("\n[4A] Weighted consensus × min_score × consensus")
for ms in [1.0, 1.5, 2.0]:
    for mc in [1, 2]:
        for ns in [True, False]:
            label = f"4A_ms{ms}_mc{mc}_noSL{str(ns)[0]}"
            r = run(label, min_score=ms, min_consensus=mc, use_weighted_consensus=True,
                    momentum_sell=1.0, kelly_cap=0.5, cash_reserve_pct=0.10,
                    max_position_pct=40, max_holdings=8, max_sector_pct=50,
                    max_qdii_pct=50, dynamic_ranking=True, profit_mode="half",
                    take_profit_pct=20, stop_loss_pct=-5, monthly_injection=10000,
                    no_stop_loss=ns)
            results.append(r)
            show(r)

# ── 4B: Aggressive allocation under weighted consensus ──
best_ms = 1.0  # from 4A we'll see
print("\n[4B] Aggressive allocation under weighted consensus")
for kc in [0.3, 0.5, 0.7, 1.0]:
    for cr in [0.0, 0.05, 0.10]:
        for mp in [30, 50, 80]:
            for mh in [3, 5, 10]:
                label = f"4B_kc{kc}_cr{cr}_mp{mp}_mh{mh}"
                r = run(label, min_score=1.5, min_consensus=1,
                        use_weighted_consensus=True, momentum_sell=1.0,
                        kelly_cap=kc, cash_reserve_pct=cr,
                        max_position_pct=mp, max_holdings=mh, max_sector_pct=100,
                        max_qdii_pct=100, dynamic_ranking=True, profit_mode="half",
                        take_profit_pct=30, stop_loss_pct=-15, monthly_injection=10000,
                        no_stop_loss=True)
                results.append(r)
                if len(results) % 20 == 0:
                    best = max((r for r in results if not r.get("error")), key=lambda x: x["total_return"])
                    print(f"  ... {len(results)} configs done, best: {best['total_return']:+.2f}% ({best['label']})")

# Best so far
good = [r for r in results if not r.get("error")]
good.sort(key=lambda x: -x["total_return"])
print(f"\n[4B] Best so far:")
for r in good[:5]:
    show(r)

# ── 4C: Profit mode + take profit sweep ──
print("\n[4C] Profit mode + take profit sweep")
best = good[0]
for pm in ["half", "all", "quarter", "step"]:
    for tp in [10, 20, 30, 50, 100]:
        label = f"4C_{pm}_{tp}"
        r = run(label, min_score=best["config"].get("min_score", 1.5), min_consensus=1,
                use_weighted_consensus=True, momentum_sell=1.0,
                kelly_cap=best["config"].get("kelly_cap", 0.5),
                cash_reserve_pct=best["config"].get("cash_reserve_pct", 0.05),
                max_position_pct=best["config"].get("max_position_pct", 50),
                max_holdings=best["config"].get("max_holdings", 5),
                max_sector_pct=100, max_qdii_pct=100,
                dynamic_ranking=True, profit_mode=pm,
                take_profit_pct=tp, stop_loss_pct=-15, monthly_injection=10000,
                no_stop_loss=True)
        results.append(r)
        show(r)

# ── 4D: Extreme: monthly injection sweep + no cash reserve ──
print("\n[4D] Extreme: injection sweep, no reserve")
for inj in [0, 5000, 10000, 20000, 50000]:
    for cr in [0.0, 0.05, 0.10]:
        label = f"4D_inj{inj}_cr{cr}"
        r = run(label, min_score=1.5, min_consensus=1,
                use_weighted_consensus=True, momentum_sell=1.0,
                kelly_cap=0.7, cash_reserve_pct=cr,
                max_position_pct=80, max_holdings=5, max_sector_pct=100,
                max_qdii_pct=100, dynamic_ranking=True, profit_mode="half",
                take_profit_pct=30, stop_loss_pct=-15, monthly_injection=inj,
                no_stop_loss=True)
        results.append(r)
        show(r)

# ── 4E: Dynamic ranking variants + fund type filters ──
print("\n[4E] Ranking variants + fund type")
for dr in [True, False]:
    for ft in ["all", "active", "passive"]:
        label = f"4E_dr{str(dr)[0]}_{ft}"
        r = run(label, min_score=1.5, min_consensus=1,
                use_weighted_consensus=True, momentum_sell=1.0,
                kelly_cap=0.7, cash_reserve_pct=0.05,
                max_position_pct=80, max_holdings=5, max_sector_pct=100,
                max_qdii_pct=100, dynamic_ranking=dr, profit_mode="half",
                take_profit_pct=30, stop_loss_pct=-15, monthly_injection=0,
                no_stop_loss=True, fund_type_filter=ft)
        results.append(r)
        show(r)

# ── 4F: Ultimate: everything maxed ──
print("\n[4F] Ultimate configs")
extreme_configs = [
    ("ULTRA_AGGRESSIVE", dict(min_score=1.0, min_consensus=1, use_weighted_consensus=True,
         kelly_cap=1.0, cash_reserve_pct=0.0, max_position_pct=100, max_holdings=3,
         max_sector_pct=100, max_qdii_pct=100, dynamic_ranking=True,
         momentum_sell=0.5, profit_mode="all", take_profit_pct=100,
         stop_loss_pct=-5, monthly_injection=0, no_stop_loss=True)),
    ("CONCENTRATED_5", dict(min_score=1.5, min_consensus=1, use_weighted_consensus=True,
         kelly_cap=0.7, cash_reserve_pct=0.05, max_position_pct=60, max_holdings=5,
         max_sector_pct=100, max_qdii_pct=100, dynamic_ranking=True,
         momentum_sell=1.0, profit_mode="step", take_profit_pct=20,
         stop_loss_pct=-25, monthly_injection=0, no_stop_loss=False)),
    ("MAX_MOMENTUM", dict(min_score=1.5, min_consensus=1, use_weighted_consensus=True,
         kelly_cap=0.7, cash_reserve_pct=0.0, max_position_pct=80, max_holdings=5,
         max_sector_pct=100, max_qdii_pct=100, dynamic_ranking=True,
         momentum_sell=0.5, profit_mode="all", take_profit_pct=50,
         stop_loss_pct=-10, monthly_injection=20000, no_stop_loss=False)),
    ("HIGH_CONVICTION", dict(min_score=2.0, min_consensus=1, use_weighted_consensus=True,
         kelly_cap=0.7, cash_reserve_pct=0.05, max_position_pct=60, max_holdings=3,
         max_sector_pct=100, max_qdii_pct=100, dynamic_ranking=True,
         momentum_sell=1.5, profit_mode="half", take_profit_pct=15,
         stop_loss_pct=-20, monthly_injection=0, no_stop_loss=False)),
    ("NO_STOP_LOSS_BLAZE", dict(min_score=1.0, min_consensus=1, use_weighted_consensus=True,
         kelly_cap=0.7, cash_reserve_pct=0.0, max_position_pct=80, max_holdings=5,
         max_sector_pct=100, max_qdii_pct=100, dynamic_ranking=True,
         momentum_sell=0.5, profit_mode="half", take_profit_pct=15,
         stop_loss_pct=-5, monthly_injection=50000, no_stop_loss=True)),
    ("SMART_WEIGHTED", dict(min_score=1.5, min_consensus=1, use_weighted_consensus=True,
         kelly_cap=0.5, cash_reserve_pct=0.10, max_position_pct=40, max_holdings=8,
         max_sector_pct=60, max_qdii_pct=60, dynamic_ranking=True,
         momentum_sell=1.0, profit_mode="step", take_profit_pct=20,
         stop_loss_pct=-15, monthly_injection=10000, no_stop_loss=False)),
]
for label, cfg in extreme_configs:
    r = run(label, **cfg)
    results.append(r)
    show(r)

# ── FINAL RANKING ──
good = [r for r in results if not r.get("error")]
good.sort(key=lambda x: -x["total_return"])

print("\n" + "=" * 70)
print("🏆 FINAL TOP 15 (by total return)")
print("=" * 70)
for i, r in enumerate(good[:15]):
    cfg = r.get("config", {})
    print(f"\n  #{i+1}: {r['label']}")
    print(f"       总收益率: {r['total_return']:>+7.2f}%")
    print(f"       最大回撤: {r['max_drawdown']:>5.1f}%")
    print(f"       超额收益: {r['excess']:>+7.2f}%")
    print(f"       交易次数: {r['trades']}")
    print(f"       最终持仓: {r.get('final_holdings', 0)}")
    print(f"       最终价值: ¥{r['final_value']:,.0f}")
    print(f"       手续费:   ¥{r.get('fees', 0):,.0f}")
    print(f"       基准:     {r['benchmark']:+.2f}%")

# By excess return
by_ex = sorted(good, key=lambda x: -x["excess"])
print(f"\n{'='*70}")
print("🏆 TOP 10 BY EXCESS RETURN")
print("=" * 70)
for r in by_ex[:10]:
    print(f"  {r['label']:25s}: Excess={r['excess']:>+6.2f}% Ret={r['total_return']:>+6.2f}% DD={r['max_drawdown']:>4.1f}% Trades={r['trades']:3d}")

# Save
output = {
    "best_total_return": good[0]["total_return"],
    "best_drawdown": good[0]["max_drawdown"],
    "best_excess": good[0]["excess"],
    "best_trades": good[0]["trades"],
    "best_label": good[0]["label"],
    "best_config": good[0].get("config", {}),
    "top15": [{k:v for k,v in r.items() if k != 'config'} for r in good[:15]],
    "total_tested": len(good),
}
out_path = PROJECT_ROOT / "backtest" / "reports" / "optimization_phase4.json"
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False, indent=2)
print(f"\nSaved to {out_path}")
print(f"Total time: ~{len(good) * 25 // 60}m")