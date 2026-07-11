#!/usr/bin/env python3
"""Phase 5: 极限探索 — 冲击 100%+ 收益率"""
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
    "verbose_ranking": False, "fund_type_filter": "all", "sell_consensus": 0,
    "use_weighted_consensus": True, "dynamic_ranking": True,
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
            "label": label,
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
        print(f"  {r['label']:30s}: Ret={r['total_return']:>+7.2f}% DD={r['max_drawdown']:>5.1f}% "
              f"Ex={r['excess']:>+7.2f}% Tr={r['trades']:4d} Hold={r['final_holdings']:2d} "
              f"Fees={r['fees']:>5.0f} Val={r['final_value']:>8.0f}")

print("=" * 70)
print("PHASE 5: 极限收益率探索 — 冲击 100%+")
print("=" * 70)

results = []

# ── 5A: 无限止盈 + 无限仓位 + 无限集中 ──
# Key insight: take_profit=100 gives 47%. What if we never take profit?
print("\n[5A] 无限止盈 + 无限集中")
for tp in [100, 200, 500, 99999]:
    for mh in [2, 3, 5]:
        for kc in [0.5, 0.7, 1.0]:
            label = f"5A_tp{tp}_mh{mh}_kc{kc}"
            r = run(label, min_score=1.5, min_consensus=1,
                    kelly_cap=kc, cash_reserve_pct=0.05,
                    max_position_pct=80, max_holdings=mh,
                    max_sector_pct=100, max_qdii_pct=100,
                    momentum_sell=0.5, profit_mode="quarter",
                    take_profit_pct=tp, stop_loss_pct=-15,
                    monthly_injection=0, no_stop_loss=False)
            results.append(r)
            show(r)

# ── 5B: 无尽趋势 — 禁用所有卖出规则 ──
print("\n[5B] 无尽趋势 — 禁用全部卖出")
# no_stop_loss=True + momentum_sell=0.1 (practically never) + huge take_profit
for ns in [True]:
    for mom in [0.1, 0.5]:
        for sl in [-5, -15, -50]:
            label = f"5B_noSL{str(ns)[0]}_mom{mom}_sl{abs(sl)}"
            r = run(label, min_score=1.5, min_consensus=1,
                    kelly_cap=0.5, cash_reserve_pct=0.05,
                    max_position_pct=80, max_holdings=5,
                    max_sector_pct=100, max_qdii_pct=100,
                    momentum_sell=mom, profit_mode="quarter",
                    take_profit_pct=99999, stop_loss_pct=sl,
                    monthly_injection=0, no_stop_loss=ns)
            results.append(r)
            show(r)

# ── 5C: 极限杠杆 — 零现金 + 满仓集中 ──
print("\n[5C] 极限杠杆 — 零现金 + 满仓集中")
for cr in [0.0, 0.02, 0.05]:
    for kc in [0.5, 0.7, 1.0]:
        for mh in [2, 3]:
            label = f"5C_cr{cr}_kc{kc}_mh{mh}"
            r = run(label, min_score=1.5, min_consensus=1,
                    kelly_cap=kc, cash_reserve_pct=cr,
                    max_position_pct=100, max_holdings=mh,
                    max_sector_pct=100, max_qdii_pct=100,
                    momentum_sell=0.5, profit_mode="quarter",
                    take_profit_pct=99999, stop_loss_pct=-15,
                    monthly_injection=0, no_stop_loss=False)
            results.append(r)
            show(r)

# ── 5D: 超级月投 — 大额定投放大收益 ──
print("\n[5D] 超级月投 — 大额定投放大收益")
for inj in [10000, 20000, 50000, 100000]:
    for pm in ["quarter", "half"]:
        label = f"5D_inj{inj}_{pm}"
        r = run(label, min_score=1.5, min_consensus=1,
                kelly_cap=0.5, cash_reserve_pct=0.05,
                max_position_pct=60, max_holdings=5,
                max_sector_pct=100, max_qdii_pct=100,
                momentum_sell=0.5, profit_mode=pm,
                take_profit_pct=99999, stop_loss_pct=-15,
                monthly_injection=inj, no_stop_loss=False)
        results.append(r)
        show(r)

# ── 5E: 买入持有浓缩精华 — 只买最好的 ──
print("\n[5E] 精华浓缩 — 超高门槛 + 满仓")
for ms in [2.5, 3.0, 3.5]:
    for mc in [1, 2]:
        for mh in [2, 3]:
            label = f"5E_ms{ms}_mc{mc}_mh{mh}"
            r = run(label, min_score=ms, min_consensus=mc,
                    kelly_cap=0.7, cash_reserve_pct=0.0,
                    max_position_pct=80, max_holdings=mh,
                    max_sector_pct=100, max_qdii_pct=100,
                    momentum_sell=0.5, profit_mode="quarter",
                    take_profit_pct=99999, stop_loss_pct=-15,
                    monthly_injection=0, no_stop_loss=False)
            results.append(r)
            show(r)

# ── 5F: 组合拳 — 把最好的元素组合在一起 ──
print("\n[5F] 组合拳 — 最佳元素组合")
combos = [
    ("MAX_1", dict(min_score=1.5, min_consensus=1, cash_reserve_pct=0.0,
     max_position_pct=80, max_holdings=3, momentum_sell=0.5,
     profit_mode="quarter", take_profit_pct=99999, stop_loss_pct=-50,
     no_stop_loss=False, monthly_injection=0, kelly_cap=0.7)),
    ("MAX_2", dict(min_score=1.5, min_consensus=1, cash_reserve_pct=0.0,
     max_position_pct=100, max_holdings=3, momentum_sell=0.5,
     profit_mode="half", take_profit_pct=99999, stop_loss_pct=-100,
     no_stop_loss=True, monthly_injection=0, kelly_cap=0.7)),
    ("MAX_3", dict(min_score=1.5, min_consensus=1, cash_reserve_pct=0.02,
     max_position_pct=80, max_holdings=5, momentum_sell=0.3,
     profit_mode="quarter", take_profit_pct=99999, stop_loss_pct=-10,
     no_stop_loss=False, monthly_injection=50000, kelly_cap=0.5)),
    ("MAX_4", dict(min_score=1.0, min_consensus=1, cash_reserve_pct=0.0,
     max_position_pct=100, max_holdings=8, momentum_sell=0.5,
     profit_mode="quarter", take_profit_pct=99999, stop_loss_pct=-15,
     no_stop_loss=False, monthly_injection=0, kelly_cap=0.5)),
    ("MAX_5", dict(min_score=1.5, min_consensus=1, cash_reserve_pct=0.0,
     max_position_pct=60, max_holdings=2, momentum_sell=0.5,
     profit_mode="all", take_profit_pct=99999, stop_loss_pct=-15,
     no_stop_loss=False, monthly_injection=0, kelly_cap=0.7)),
    ("MAX_6", dict(min_score=1.5, min_consensus=2, cash_reserve_pct=0.0,
     max_position_pct=100, max_holdings=3, momentum_sell=0.5,
     profit_mode="quarter", take_profit_pct=99999, stop_loss_pct=-50,
     no_stop_loss=True, monthly_injection=50000, kelly_cap=0.5)),
    ("MAX_7", dict(min_score=1.5, min_consensus=1, cash_reserve_pct=0.05,
     max_position_pct=40, max_holdings=10, momentum_sell=0.5,
     profit_mode="step", take_profit_pct=99999, stop_loss_pct=-10,
     no_stop_loss=False, monthly_injection=20000, kelly_cap=0.7)),
    ("MAX_8", dict(min_score=0.5, min_consensus=1, cash_reserve_pct=0.0,
     max_position_pct=100, max_holdings=2, momentum_sell=0.1,
     profit_mode="all", take_profit_pct=99999, stop_loss_pct=-5,
     no_stop_loss=False, monthly_injection=0, kelly_cap=0.5)),
]
for name, params in combos:
    r = run(name, **params)
    results.append(r)
    show(r)

# ── FINAL RANKING ──
good = [r for r in results if not r.get("error")]
good.sort(key=lambda x: -x["total_return"])

print("\n" + "=" * 70)
print("FINAL TOP 15 (by total return)")
print("=" * 70)
for i, r in enumerate(good[:15]):
    print(f"\n  #{i+1}: {r['label']}")
    print(f"       Total Return: {r['total_return']:>+7.2f}%")
    print(f"       Max Drawdown: {r['max_drawdown']:>5.1f}%")
    print(f"       Excess:       {r['excess']:>+7.2f}%")
    print(f"       Trades:       {r['trades']}")
    print(f"       Final Holdings: {r.get('final_holdings', 0)}")
    print(f"       Final Value:  {r['final_value']:>10.0f}")
    print(f"       Fees:         {r.get('fees', 0):>8.0f}")
    print(f"       Benchmark:    {r['benchmark']:+.2f}%")

# By excess
by_ex = sorted(good, key=lambda x: -x["excess"])
print(f"\n{'='*70}")
print("TOP 10 BY EXCESS RETURN")
print("=" * 70)
for r in by_ex[:10]:
    print(f"  {r['label']:30s}: Excess={r['excess']:>+7.2f}% Ret={r['total_return']:>+7.2f}% DD={r['max_drawdown']:>5.1f}% Trades={r['trades']:4d} Hold={r['final_holdings']:2d}")

# Save
output = {
    "best_total_return": good[0]["total_return"],
    "best_drawdown": good[0]["max_drawdown"],
    "best_excess": good[0]["excess"],
    "best_trades": good[0]["trades"],
    "best_label": good[0]["label"],
    "top15": [{k:v for k,v in r.items() if k != 'config'} for r in good[:15]],
    "total_tested": len(good),
}
out_path = PROJECT_ROOT / "backtest" / "reports" / "optimization_phase5.json"
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False, indent=2)
print(f"\nSaved to {out_path}")

# Print all results
print(f"\n{'='*70}")
print("ALL RESULTS")
print("=" * 70)
for r in sorted(good, key=lambda x: -x["total_return"]):
    show(r)