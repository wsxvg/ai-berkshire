#!/usr/bin/env python3
"""精简实验：只跑13个关键回测（约3.7小时）
砍掉已证明无用的P1(corr/cooldown/cash/tp/sl)"""
import sys, json, time, copy
from pathlib import Path
from collections import defaultdict

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))
REPORTS = PROJECT / "backtest" / "reports"
REPORTS.mkdir(parents=True, exist_ok=True)

from backtest.engine.backtest import run_backtest

# 冠军基线
BASE = json.loads((PROJECT / "data" / "evolution" / "best_config.json").read_text("utf-8"))["config"]

RANKING_PATH = REPORTS / "leader_exclude_lists.json"

def load_ranking():
    if RANKING_PATH.exists():
        return json.loads(RANKING_PATH.read_text("utf-8"))
    return []

def get_top_n_uids(n):
    ranking = load_ranking()
    if not ranking: return []
    sorted_r = sorted(ranking, key=lambda x: x.get("total_return", 0), reverse=True)
    top = set(str(r["uid"]) for r in sorted_r[:n])
    all_uids = set(str(r["uid"]) for r in sorted_r)
    return list(all_uids - top)

def run_single(name, overrides):
    cfg = copy.deepcopy(BASE)
    cfg.update(overrides)
    t0 = time.time()
    print(f"\n  [RUN] {name}", flush=True)
    try:
        result = run_backtest(cfg)
        elapsed = time.time() - t0
        ret = result.get("total_return", 0)
        dd = result.get("max_drawdown", 0)
        trades = result.get("trade_count", 0)
        print(f"  -> {name}: ret={ret:.2f}% dd={dd:.2f}% trades={trades} ({elapsed:.0f}s)", flush=True)
        return {"name": name, "return": round(ret, 2), "dd": round(dd, 2),
                "trades": trades, "time_sec": round(elapsed, 0),
                "daily_values": result.get("daily_values", []),
                "trades_list": result.get("trades", [])}
    except Exception as e:
        elapsed = time.time() - t0
        print(f"  -> {name}: ERROR {e} ({elapsed:.0f}s)", flush=True)
        return {"name": name, "error": str(e)}

def save(name, results):
    path = REPORTS / name
    compact = [{k: v for k, v in r.items() if k not in ("daily_values", "trades_list")} for r in results]
    path.write_text(json.dumps(compact, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  保存: {path}", flush=True)

# ═══════════════════════════════════════════════════════════
# 实验列表（13个）
# ═══════════════════════════════════════════════════════════

def run_all():
    all_results = {}
    t_total = time.time()
    
    # ── 步骤1: sec_pct梯度 (3个) ──
    print("\n" + "="*60)
    print("# 步骤1: sec_pct 梯度")
    print("="*60, flush=True)
    s1 = []
    for sp in [0, 30, 50]:
        s1.append(run_single(f"champion+sec_{sp}", {"max_sector_pct": sp}))
    save("final_combo_exhaustive.json", s1)
    all_results["step1"] = s1

    # ── 步骤4.5: 全周期+三段式 (5个) ──
    print("\n" + "="*60)
    print("# 步骤4.5: 全周期验证")
    print("="*60, flush=True)
    s45 = []
    s45.append(run_single("champion_full_2023_2026",
        {"start_date": "2023-07-01", "end_date": "2026-07-01", "min_consensus": 2}))
    for label, sd, ed in [("A_bear", "2023-07-01", "2024-06-30"),
                          ("B_recovery", "2024-07-01", "2025-06-30"),
                          ("C_bull", "2025-07-01", "2026-07-01")]:
        s45.append(run_single(f"seg_{label}", {"start_date": sd, "end_date": ed}))
    # 最差回撤窗口从全周期结果提取
    full = s45[0]
    dvs = full.get("daily_values", [])
    if dvs:
        peak = dvs[0].get("total", 0)
        max_dd = 0; dd_start = ""; dd_end = ""; peak_date = dvs[0].get("date", "")
        for dv in dvs:
            t = dv.get("total", 0)
            if t > peak: peak = t; peak_date = dv.get("date", "")
            dd = (peak - t) / peak * 100 if peak > 0 else 0
            if dd > max_dd: max_dd = dd; dd_start = peak_date; dd_end = dv.get("date", "")
        print(f"\n  最差回撤: {max_dd:.2f}% 从 {dd_start} 到 {dd_end}", flush=True)
        s45.append({"name": "max_dd_window", "dd_pct": round(max_dd, 2), "start": dd_start, "end": dd_end})
    save("p45_full_cycle.json", s45)
    all_results["step45"] = s45

    # ── 步骤5: 过拟合检测 (3个) ──
    print("\n" + "="*60)
    print("# 步骤5: 过拟合检测")
    print("="*60, flush=True)
    s5 = []
    # 5.1 2025only
    s5.append(run_single("champion_2025only", {"start_date": "2025-01-05", "end_date": "2025-12-31"}))
    s5.append(run_single("baseline_2025only",
        {"exclude_uids": [], "fund_type_filter": "all", "max_sector_pct": 100,
         "start_date": "2025-01-05", "end_date": "2025-12-31"}))
    # 5.2 去赢家
    champ = run_single("champion_for_winner", {})
    s5.append(champ)
    trades_list = champ.get("trades_list", [])
    if trades_list:
        fpnl = defaultdict(float)
        for t in trades_list:
            code = t.get("code", "")
            if code == "CASH": continue
            action = t.get("action", "")
            amt = t.get("amount", 0)
            fee = t.get("fee", 0)
            if action in ("sell", "sell_all"): fpnl[code] += amt - fee
            elif action == "buy": fpnl[code] -= amt + fee
        if fpnl:
            top1 = max(fpnl.items(), key=lambda x: x[1])
            total_profit = sum(v for v in fpnl.values() if v > 0)
            pct = top1[1] / total_profit * 100 if total_profit > 0 else 0
            print(f"  TOP1 winner: {top1[0]} profit={top1[1]:.0f} ({pct:.1f}% of total)", flush=True)
            s5.append({"name": "p52_winner_analysis", "top1_code": top1[0],
                       "top1_profit": round(top1[1], 2), "top1_pct": round(pct, 1)})
    save("p9_overfit.json", s5)
    all_results["step5"] = s5

    elapsed = time.time() - t_total
    print(f"\n{'='*60}")
    print(f"  全部完成! 总耗时 {elapsed/60:.1f} 分钟")
    print(f"{'='*60}", flush=True)
    
    # 汇总
    summary = []
    for step, results in all_results.items():
        for r in results:
            if "return" in r:
                summary.append({"step": step, "name": r["name"], "return": r["return"], "dd": r["dd"], "trades": r["trades"]})
    save("experiment_summary.json", summary)
    return all_results

if __name__ == "__main__":
    run_all()
