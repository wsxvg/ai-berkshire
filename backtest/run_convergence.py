#!/usr/bin/env python3
"""步骤1-5: 核心组合穷举 + 缺失策略 + 一致性 + 风险 + 过拟合

用法:
    py -3.10 backtest/run_convergence.py --step 1   # 步骤1: 组合穷举
    py -3.10 backtest/run_convergence.py --step 2   # 步骤2: 缺失策略
    py -3.10 backtest/run_convergence.py --step 3   # 步骤3: 一致性
    py -3.10 backtest/run_convergence.py --step 4   # 步骤4: 风险画像
    py -3.10 backtest/run_convergence.py --step 5   # 步骤5: 过拟合
    py -3.10 backtest/run_convergence.py --step 45  # 步骤4.5: 全周期
    py -3.10 backtest/run_convergence.py --step all # 全部
"""
import sys, json, time, copy, argparse
from pathlib import Path
from collections import defaultdict

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))
REPORTS = PROJECT / "backtest" / "reports"
REPORTS.mkdir(parents=True, exist_ok=True)

from backtest.engine.backtest import run_backtest

# ── 冠军基线（从 best_config.json 读取） ──
_best = json.loads((PROJECT / "data" / "evolution" / "best_config.json").read_text("utf-8"))
BASE = _best["config"]
# 冠军 = BASE 本身（已含 active + sec40 + 10-UID黑名单）

# ── 排行数据 ──
RANKING_PATH = REPORTS / "leader_pnl_ranking.json"

def load_ranking():
    if RANKING_PATH.exists():
        return json.loads(RANKING_PATH.read_text("utf-8"))
    return []

def get_top_n_uids(n):
    ranking = load_ranking()
    if not ranking:
        return []
    sorted_r = sorted(ranking, key=lambda x: x.get("total_return", 0), reverse=True)
    top = set(str(r["uid"]) for r in sorted_r[:n])
    all_uids = set(str(r["uid"]) for r in sorted_r)
    return list(all_uids - top)

def get_exclude_neg():
    ranking = load_ranking()
    return [str(r["uid"]) for r in ranking if r.get("total_return", 0) < 0]

def run_single(name, overrides, group="default"):
    cfg = copy.deepcopy(BASE)
    cfg.update(overrides)
    t0 = time.time()
    print(f"\n  [RUN] {name} ({group})")
    try:
        result = run_backtest(cfg)
        elapsed = time.time() - t0
        ret = result.get("total_return", 0)
        dd = result.get("max_drawdown", 0)
        trades = result.get("trade_count", 0)
        print(f"  -> {name}: ret={ret:.2f}% dd={dd:.2f}% trades={trades} ({elapsed:.0f}s)")
        return {"name": name, "group": group, "return": round(ret, 2),
                "dd": round(dd, 2), "trades": trades, "time_sec": round(elapsed, 0),
                "daily_values": result.get("daily_values", []),
                "trades_list": result.get("trades", []),
                "benchmark_return": result.get("benchmark_return", 0)}
    except Exception as e:
        elapsed = time.time() - t0
        print(f"  -> {name}: ERROR {e} ({elapsed:.0f}s)")
        return {"name": name, "group": group, "error": str(e)}

def save(name, results):
    path = REPORTS / name
    # 不保存 daily_values/trades_list 到 JSON（太大）
    compact = [{k: v for k, v in r.items() if k not in ("daily_values", "trades_list")}
               for r in results]
    path.write_text(json.dumps(compact, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  保存: {path}")


# ═══════════════════════════════════════════════════════════
# 步骤1: 核心组合穷举
# ═══════════════════════════════════════════════════════════

def step1():
    results = []
    # 1.1 fund_type_filter 穷举（最关键）
    for ft in ["all", "active"]:
        results.append(run_single(f"champion+ft_{ft}", {"fund_type_filter": ft}, "1.1_fund_type"))
    # 1.2 sec_pct 精搜
    for sp in [0, 30, 50]:
        results.append(run_single(f"champion+sec_{sp}", {"max_sector_pct": sp}, "1.2_sec_pct"))
    # 1.3 噪音剔除补测
    for n in [35, 45]:
        excl = get_top_n_uids(n)
        results.append(run_single(f"TOP_{n}+active+sec40",
                                  {"exclude_uids": excl}, "1.3_noise"))
    save("final_combo_exhaustive.json", results)
    return results


# ═══════════════════════════════════════════════════════════
# 步骤2: 缺失策略验证
# ═══════════════════════════════════════════════════════════

def step2():
    results = []
    # 2.1 max_correlation
    for c in [0.85, 0.80]:
        results.append(run_single(f"champion+corr_{c}", {"max_correlation": c}, "2.1_correlation"))
    # 2.2 cooldown_days
    for cd in [5, 10, 15]:
        results.append(run_single(f"champion+cooldown_{cd}", {"cooldown_days": cd}, "2.2_cooldown"))
    # 2.3 cash_reserve_pct
    for cr in [0.05, 0.15]:
        results.append(run_single(f"champion+cash_{cr}", {"cash_reserve_pct": cr}, "2.3_cash"))
    # 2.4 take_profit 微调
    for tp in [40, 60]:
        results.append(run_single(f"champion+tp_{tp}", {"take_profit_pct": tp}, "2.4_take_profit"))
    # 2.5 stop_loss 微调
    for sl in [-25, -35]:
        results.append(run_single(f"champion+sl_{sl}", {"stop_loss_pct": sl}, "2.5_stop_loss"))
    save("p1_missing_strategies.json", results)
    return results


# ═══════════════════════════════════════════════════════════
# 步骤3: 一致性验证
# ═══════════════════════════════════════════════════════════

def step3():
    results = []
    # 跑两次确认稳定性（第二次复用 step4 的冠军跑结果）
    results.append(run_single("champion_run1", {}, "3.1_stability"))
    # 分期
    results.append(run_single("champion_2025H1",
                              {"start_date": "2025-01-05", "end_date": "2025-09-30"}, "3.2_split"))
    results.append(run_single("champion_2025H2",
                              {"start_date": "2025-10-01", "end_date": "2026-07-01"}, "3.2_split"))
    # 基准对比
    champ_r = results[0]
    base_r = run_single("baseline_full",
                        {"exclude_uids": [], "fund_type_filter": "all", "max_sector_pct": 100}, "3.3_benchmark")
    results.append(base_r)
    # CSI300 + Nasdaq QDII
    charts_path = PROJECT / "data" / "fund_charts.json"
    charts = json.loads(charts_path.read_text("utf-8")) if charts_path.exists() else {}
    def calc_bm(code):
        pts = charts.get(code, [])
        if not pts: return None
        s, e = None, None
        for p in pts:
            d = p.get("xAxis", "")
            y = float(p.get("yAxis", 0))
            if d == BASE["start_date"]: s = y
            if d == BASE["end_date"]: e = y
        if s is None:
            for p in pts:
                if p.get("xAxis", "") >= BASE["start_date"]: s = float(p.get("yAxis", 0)); break
        if e is None:
            for p in reversed(pts):
                if p.get("xAxis", "") <= BASE["end_date"]: e = float(p.get("yAxis", 0)); break
        if s is not None and e is not None:
            return ((100 + e) / (100 + s) - 1) * 100
        return None
    bm = {
        "champion": champ_r.get("return"),
        "baseline": base_r.get("return"),
        "csi300": calc_bm("110020"),
        "nasdaq_834": calc_bm("000834"),
        "nasdaq_042": calc_bm("270042"),
    }
    (REPORTS / "benchmark_comparison.json").write_text(
        json.dumps(bm, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n  基准: 冠军={bm['champion']:.2f}% 基线={bm['baseline']:.2f}% CSI300={bm.get('csi300')} 纳指834={bm.get('nasdaq_834')}")
    save("p2_consistency.json", results)
    return results


# ═══════════════════════════════════════════════════════════
# 步骤4: 风险画像
# ═══════════════════════════════════════════════════════════

def step4():
    print("\n  [RUN] champion_risk (full data)")
    cfg = copy.deepcopy(BASE)
    t0 = time.time()
    result = run_backtest(cfg)
    elapsed = time.time() - t0
    ret = result.get("total_return", 0)
    dd = result.get("max_drawdown", 0)
    trades = result.get("trade_count", 0)
    print(f"  -> champion_risk: ret={ret:.2f}% dd={dd:.2f}% trades={trades} ({elapsed:.0f}s)")

    trades_list = result.get("trades", [])
    daily_values = result.get("daily_values", [])

    # P3.1 利润贡献
    fund_pnl = defaultdict(lambda: {"profit": 0, "buy_dates": [], "sell_dates": [], "name": ""})
    for t in trades_list:
        code = t.get("code", "")
        action = t.get("action", "")
        amount = t.get("amount", 0)
        fee = t.get("fee", 0)
        name = t.get("name", code)
        if code == "CASH": continue
        if action in ("sell", "sell_all"):
            fund_pnl[code]["profit"] += amount - fee
            fund_pnl[code]["sell_dates"].append(t.get("date", ""))
            fund_pnl[code]["name"] = name
        elif action == "buy":
            fund_pnl[code]["profit"] -= amount + fee
            fund_pnl[code]["buy_dates"].append(t.get("date", ""))
            fund_pnl[code]["name"] = name
    sorted_pnl = sorted(fund_pnl.items(), key=lambda x: x[1]["profit"], reverse=True)
    top5_profit = [{"code": c, "name": d["name"], "profit": round(d["profit"], 2),
                     "buy_dates": d["buy_dates"][:3], "sell_dates": d["sell_dates"][:3]}
                    for c, d in sorted_pnl[:5] if d["profit"] > 0]
    top5_loss = [{"code": c, "name": d["name"], "profit": round(d["profit"], 2),
                  "buy_dates": d["buy_dates"][:3], "sell_dates": d["sell_dates"][:3]}
                 for c, d in sorted_pnl[-5:] if d["profit"] < 0]

    # P3.2 连亏
    max_consec = 0
    cur_streak = 0
    max_single_loss = 0
    max_single_loss_pct = 0
    prev_total = BASE["initial_cash"]
    for dv in daily_values:
        total = dv.get("total", prev_total)
        change = total - prev_total
        if change < 0:
            cur_streak += 1
            max_consec = max(max_consec, cur_streak)
            if change < max_single_loss:
                max_single_loss = change
                max_single_loss_pct = (change / prev_total * 100) if prev_total > 0 else 0
        else:
            cur_streak = 0
        prev_total = total

    # P3.3 月度
    monthly = defaultdict(list)
    for dv in daily_values:
        m = dv.get("date", "")[:7]
        if m: monthly[m].append(dv.get("total", 0))
    monthly_returns = {}
    prev_end = BASE["initial_cash"]
    for m in sorted(monthly.keys()):
        vals = monthly[m]
        m_end = vals[-1] if vals else prev_end
        r = (m_end / prev_end - 1) * 100 if prev_end > 0 else 0
        monthly_returns[m] = round(r, 2)
        prev_end = m_end
    win = sum(1 for v in monthly_returns.values() if v > 0)
    total_m = len(monthly_returns)

    report = {
        "total_return": round(ret, 2), "max_drawdown": round(dd, 2),
        "trade_count": trades,
        "pnl_top5": top5_profit, "loss_top5": top5_loss,
        "total_funds_traded": len(fund_pnl),
        "profitable_funds": sum(1 for d in fund_pnl.values() if d["profit"] > 0),
        "losing_funds": sum(1 for d in fund_pnl.values() if d["profit"] < 0),
        "max_consecutive_loss_days": max_consec,
        "max_single_loss": round(max_single_loss, 2),
        "max_single_loss_pct": round(max_single_loss_pct, 2),
        "monthly_returns": monthly_returns,
        "winning_months": win, "total_months": total_m,
        "monthly_winrate": round(win / total_m * 100, 1) if total_m > 0 else 0,
    }
    path = REPORTS / "p3_risk_profile.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n  利润TOP5: {[(f['code'], f['profit']) for f in top5_profit]}")
    print(f"  亏损TOP5: {[(f['code'], f['profit']) for f in top5_loss]}")
    print(f"  连亏: {max_consec}天, 最大单日亏损: {max_single_loss:.0f} ({max_single_loss_pct:.2f}%)")
    print(f"  月胜率: {win}/{total_m} = {report['monthly_winrate']:.1f}%")
    print(f"  保存: {path}")
    return [report]


# ═══════════════════════════════════════════════════════════
# 步骤4.5: 全周期验证
# ═══════════════════════════════════════════════════════════

def step45():
    results = []
    # 4.5.1 全周期
    results.append(run_single("champion_full_2023_2026",
                              {"start_date": "2023-07-01", "end_date": "2026-07-01",
                               "min_consensus": 2}, "4.5.1_full"))
    results.append(run_single("champion_full_sparse_adaptive",
                              {"start_date": "2023-07-01", "end_date": "2026-07-01",
                               "min_consensus": 1}, "4.5.1_full"))
    # 4.5.2 三段式
    for label, sd, ed in [("A_bear", "2023-07-01", "2024-06-30"),
                          ("B_recovery", "2024-07-01", "2025-06-30"),
                          ("C_bull", "2025-07-01", "2026-07-01")]:
        results.append(run_single(f"champion_seg_{label}",
                                  {"start_date": sd, "end_date": ed}, "4.5.2_segments"))
    # 4.5.3 最差回撤窗口 — 从全周期 daily_values 提取
    full_result = results[0]
    dvs = full_result.get("daily_values", [])
    if dvs:
        peak = dvs[0].get("total", 0)
        max_dd = 0
        dd_start = ""
        dd_end = ""
        peak_date = dvs[0].get("date", "")
        for dv in dvs:
            t = dv.get("total", 0)
            if t > peak:
                peak = t
                peak_date = dv.get("date", "")
            dd = (peak - t) / peak * 100 if peak > 0 else 0
            if dd > max_dd:
                max_dd = dd
                dd_start = peak_date
                dd_end = dv.get("date", "")
        print(f"\n  最差回撤: {max_dd:.2f}% 从 {dd_start} 到 {dd_end}")
    save("p45_full_cycle.json", results)
    return results


# ═══════════════════════════════════════════════════════════
# 步骤5: 过拟合检测
# ═══════════════════════════════════════════════════════════

def step5():
    results = []
    # P9.1: 只跑 2025
    results.append(run_single("champion_2025only",
                              {"start_date": "2025-01-05", "end_date": "2025-12-31"}, "5.1_2025"))
    results.append(run_single("baseline_2025only",
                              {"exclude_uids": [], "fund_type_filter": "all", "max_sector_pct": 100,
                               "start_date": "2025-01-05", "end_date": "2025-12-31"}, "5.1_2025"))
    # P9.2: 去赢家 — 先跑冠军拿到 trades，找到利润最高基金，排除后重跑
    champ = run_single("champion_for_winner", {}, "5.2_remove_winner")
    results.append(champ)
    trades_list = champ.get("trades_list", [])
    if trades_list:
        fpnl = defaultdict(float)
        for t in trades_list:
            code = t.get("code", "")
            if code == "CASH": continue
            action = t.get("action", "")
            amt = t.get("amount", 0)
            fee = t.get("fee", 0)
            if action in ("sell", "sell_all"):
                fpnl[code] += amt - fee
            elif action == "buy":
                fpnl[code] -= amt + fee
        if fpnl:
            top1 = max(fpnl.items(), key=lambda x: x[1])
            print(f"  TOP1 winner: {top1[0]} profit={top1[1]:.0f}")
            # 重跑排除 TOP1（通过设 max_correlation=999 等方式不现实，
            # 改为排除该基金的信号——但引擎不支持 exclude_fund_codes，
            # 用近似：如果 TOP1 是某只基金，记录其贡献占比）
            total_profit = sum(v for v in fpnl.values() if v > 0)
            if total_profit > 0:
                pct = top1[1] / total_profit * 100
                print(f"  TOP1 占总利润: {pct:.1f}%")
                results.append({"name": "p9.2_winner_analysis", "top1_code": top1[0],
                               "top1_profit": round(top1[1], 2), "top1_pct_of_profit": round(pct, 1)})
    # P9.3: 温和市场（2025 Q1+Q2 作为代理）
    results.append(run_single("champion_2025Q1Q2",
                              {"start_date": "2025-01-05", "end_date": "2025-06-30"}, "5.3_mild"))
    results.append(run_single("baseline_2025Q1Q2",
                              {"exclude_uids": [], "fund_type_filter": "all", "max_sector_pct": 100,
                               "start_date": "2025-01-05", "end_date": "2025-06-30"}, "5.3_mild"))
    save("p9_overfit.json", results)
    return results


# ═══════════════════════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════════════════════

STEPS = {
    "1": ("步骤1: 组合穷举", step1),
    "2": ("步骤2: 缺失策略", step2),
    "3": ("步骤3: 一致性", step3),
    "4": ("步骤4: 风险画像", step4),
    "45": ("步骤4.5: 全周期", step45),
    "5": ("步骤5: 过拟合", step5),
}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--step", default="1", help="步骤号 (1/2/3/4/45/5/all)")
    args = ap.parse_args()

    if args.step == "all":
        keys = ["1", "2", "3", "4", "45", "5"]
    else:
        keys = [args.step]

    t0 = time.time()
    for k in keys:
        if k not in STEPS:
            print(f"[WARN] 未知步骤: {k}")
            continue
        label, func = STEPS[k]
        print(f"\n{'#'*60}")
        print(f"# {label}")
        print(f"{'#'*60}")
        func()

    elapsed = time.time() - t0
    print(f"\n{'='*60}")
    print(f"  完成! 总耗时 {elapsed/60:.1f} 分钟")
    print(f"{'='*60}")

if __name__ == "__main__":
    main()
