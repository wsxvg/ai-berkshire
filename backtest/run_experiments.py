#!/usr/bin/env python3
"""P0-P9 综合回测实验 — 在 30 天影子期内并行跑完

用法:
    py -3.10 backtest/run_experiments.py           # 跑全部
    py -3.10 backtest/run_experiments.py --only P0  # 只跑 P0
    py -3.10 backtest/run_experiments.py --only P0,P1,P2  # 跑指定组
"""
import sys, json, time, copy, argparse, os
from pathlib import Path
from datetime import datetime, timedelta

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))
REPORTS_DIR = PROJECT / "backtest" / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

from backtest.engine.backtest import run_backtest

# ── 冠军配置基线 ──
BASE = {
    "start_date": "2025-01-05", "end_date": "2026-07-01",
    "initial_cash": 100000, "monthly_injection": 0,
    "weights": {"quality": 25, "cost": 20, "manager": 20, "momentum": 15, "smart_money": 20},
    "min_score": 0.0, "min_consensus": 2,
    "max_position_pct": 25, "cash_reserve_pct": 0.10,
    "cooldown_days": 0, "take_profit_pct": 50, "stop_loss_pct": -30,
    "trailing_tp_activate": 0, "trailing_tp_drawdown": 10,
    "dynamic_ranking": False, "ranking_window": 90,
    "kelly_cap": 0.2, "momentum_sell": 2.0,
    "profit_mode": "half", "no_stop_loss": False,
    "use_weighted_consensus": False, "cost_penalty": 0, "limit_boost": 0,
    "top_n": 0, "top_n_pct": 0, "consensus_priority": False,
    "net_signal": False, "max_sector_pct": 40, "max_qdii_pct": 100,
    "rebalance": True, "monthly_injection": 0,
    "fund_type_filter": "active", "sell_consensus": 0,
    "cooldown_profit_days": 10, "cooldown_loss_days": 30,
    "max_correlation": 0, "ml_signal": False, "ml_weight": 1.0,
    "ml_retrain_days": 30, "timing_filter": False,
    "block_overbought": False, "bear_market_no_buy": False,
    "min_score_bull": 0.0, "min_score_neutral": 0.0, "min_score_bear": 0.0,
    "downtrend_penalty": 0.5, "risk_free_rate": 0.025,
    "slippage_pct": 0.0, "verbose_ranking": False,
    "ranking_half_life": 45,
    "exclude_uids": ["14345330", "550027", "8670487", "3032839", "2690580",
                     "10951797", "183856", "1094463", "10542838", "2804244"],
}

# 噪音剔除梯度需要排除的 UID（TOP30=排除后47个, TOP60=排除17个等）
# 从 leader_pnl_ranking.json 按收益排序，TOP_N = 保留前 N 个
RANKING_PATH = REPORTS_DIR / "leader_pnl_ranking.json"

def load_ranking():
    if RANKING_PATH.exists():
        return json.loads(RANKING_PATH.read_text("utf-8"))
    return []

def get_top_n_uids(n):
    """获取排名前 N 的 UID（其余排除）"""
    ranking = load_ranking()
    if not ranking:
        return []
    # 按收益降序排序
    sorted_r = sorted(ranking, key=lambda x: x.get("total_return", 0), reverse=True)
    top_uids = set(str(r["uid"]) for r in sorted_r[:n])
    all_uids = set(str(r["uid"]) for r in sorted_r)
    exclude = all_uids - top_uids
    return list(exclude)

def get_exclude_neg():
    """排除收益为负的大佬"""
    ranking = load_ranking()
    return [str(r["uid"]) for r in ranking if r.get("total_return", 0) < 0]

def run_single(name, config_overrides, group="default"):
    """跑单个策略"""
    cfg = copy.deepcopy(BASE)
    cfg.update(config_overrides)
    t0 = time.time()
    print(f"\n{'='*60}")
    print(f"  [RUN] {name} ({group})")
    print(f"{'='*60}")
    try:
        result = run_backtest(cfg)
        elapsed = time.time() - t0
        ret = result.get("total_return", 0)
        dd = result.get("max_drawdown", 0)
        trades = result.get("trade_count", 0)
        print(f"  -> {name}: return={ret:.2f}% dd={dd:.2f}% trades={trades} ({elapsed:.0f}s)")
        return {
            "name": name, "group": group,
            "return": round(ret, 2), "dd": round(dd, 2),
            "trades": trades, "time_sec": round(elapsed, 0),
        }
    except Exception as e:
        elapsed = time.time() - t0
        print(f"  -> {name}: ERROR {e} ({elapsed:.0f}s)")
        return {"name": name, "group": group, "error": str(e), "time_sec": round(elapsed, 0)}

def run_group(group_name, experiments):
    """跑一组实验"""
    results = []
    for name, overrides in experiments:
        results.append(run_single(name, overrides, group_name))
    return results


# ═══════════════════════════════════════════════════════════
# P0: 组合精搜
# ═══════════════════════════════════════════════════════════

def run_p0():
    """P0: TOP_35/TOP_45 梯度补测 + 组件隔离测试"""
    results = []

    # P0.1: 补测 TOP_35 和 TOP_45
    for n in [35, 45]:
        exclude = get_top_n_uids(n)
        results.append(run_single(f"TOP_{n}", {"exclude_uids": exclude, "fund_type_filter": "all", "max_sector_pct": 100}, "P0.1_梯度补测"))

    # P0.2: 纯组件隔离测试
    # 冠军 = TOP60 + active + sec40
    top60_exclude = get_top_n_uids(60)

    component_tests = [
        ("K_active_only", {"fund_type_filter": "active", "exclude_uids": [], "max_sector_pct": 100}),
        ("K_sec40_only", {"max_sector_pct": 40, "exclude_uids": [], "fund_type_filter": "all"}),
        ("K_active+sec40", {"fund_type_filter": "active", "max_sector_pct": 40, "exclude_uids": []}),
        ("TOP30_sec40", {"exclude_uids": get_top_n_uids(30), "max_sector_pct": 40, "fund_type_filter": "all"}),
        ("TOP60_sec40", {"exclude_uids": top60_exclude, "max_sector_pct": 40, "fund_type_filter": "all"}),
        ("TOP60_active", {"exclude_uids": top60_exclude, "fund_type_filter": "active", "max_sector_pct": 100}),
        ("TOP60_active+sec40", {"exclude_uids": top60_exclude, "fund_type_filter": "active", "max_sector_pct": 40}),
    ]
    for name, overrides in component_tests:
        results.append(run_single(name, overrides, "P0.2_组件隔离"))

    return results


# ═══════════════════════════════════════════════════════════
# P1: 缺失策略验证
# ═══════════════════════════════════════════════════════════

def run_p1():
    """P1: max_correlation / cooldown_days / cash_reserve 测试"""
    top60_exclude = get_top_n_uids(60)
    champion = {"exclude_uids": top60_exclude, "fund_type_filter": "active", "max_sector_pct": 40}

    results = []

    # P1.1: max_correlation
    for corr in [0.85, 0.80]:
        results.append(run_single(f"champion+corr_{corr}", {**champion, "max_correlation": corr}, "P1.1_correlation"))

    # P1.2: cooldown_days
    for cd in [5, 10, 15]:
        results.append(run_single(f"champion+cooldown_{cd}", {**champion, "cooldown_days": cd}, "P1.2_cooldown"))

    # P1.3: cash_reserve_pct
    for cr in [0.05, 0.15, 0.20]:
        results.append(run_single(f"champion+cash_{cr}", {**champion, "cash_reserve_pct": cr}, "P1.3_cash_reserve"))

    return results


# ═══════════════════════════════════════════════════════════
# P2: 冠军一致性验证
# ═══════════════════════════════════════════════════════════

def run_p2():
    """P2: 跑两次确认 + 分期 + 对比基准"""
    top60_exclude = get_top_n_uids(60)
    champion = {"exclude_uids": top60_exclude, "fund_type_filter": "active", "max_sector_pct": 40}

    results = []

    # P2.1: 跑两次确认稳定
    results.append(run_single("champion_run1", champion, "P2.1_稳定"))
    results.append(run_single("champion_run2", champion, "P2.1_稳定"))

    # P2.2: 分期验证
    results.append(run_single("champion_2025H1", {**champion, "start_date": "2025-01-05", "end_date": "2025-09-30"}, "P2.2_分期"))
    results.append(run_single("champion_2025H2", {**champion, "start_date": "2025-10-01", "end_date": "2026-07-01"}, "P2.2_分期"))
    results.append(run_single("baseline_2025H1", {"exclude_uids": [], "fund_type_filter": "all", "max_sector_pct": 100, "start_date": "2025-01-05", "end_date": "2025-09-30"}, "P2.2_分期"))
    results.append(run_single("baseline_2025H2", {"exclude_uids": [], "fund_type_filter": "all", "max_sector_pct": 100, "start_date": "2025-10-01", "end_date": "2026-07-01"}, "P2.2_分期"))

    return results


# ═══════════════════════════════════════════════════════════
# P3: 冠军风险面（数据提取，不需要额外回测）
# ═══════════════════════════════════════════════════════════

def run_p3():
    """P3: 从冠军回测结果提取风险指标"""
    top60_exclude = get_top_n_uids(60)
    champion = {"exclude_uids": top60_exclude, "fund_type_filter": "active", "max_sector_pct": 40}

    # 跑冠军获取完整数据
    result = run_single("champion_risk", champion, "P3_风险面")
    if "error" in result:
        return [result]

    # 从 run_backtest 返回值中提取额外数据
    # run_backtest 返回的 result 包含 trades, daily_values 等
    # 但由于 run_single 只保留了基本指标，我们需要重新跑一次获取完整数据
    # 这里先记录基本结果，后续用脚本从 daily_values 提取

    return [result]


# ═══════════════════════════════════════════════════════════
# P9: 过拟合检测
# ═══════════════════════════════════════════════════════════

def run_p9():
    """P9: 2025单独 / 去赢家 / 温和市场"""
    top60_exclude = get_top_n_uids(60)
    champion = {"exclude_uids": top60_exclude, "fund_type_filter": "active", "max_sector_pct": 40}

    results = []

    # P9.1: 只跑 2025 年
    results.append(run_single("champion_2025only", {**champion, "start_date": "2025-01-05", "end_date": "2025-12-31"}, "P9.1_2025年"))
    results.append(run_single("baseline_2025only", {"exclude_uids": [], "fund_type_filter": "all", "max_sector_pct": 100, "start_date": "2025-01-05", "end_date": "2025-12-31"}, "P9.1_2025年"))

    # P9.2: 去掉交易量最大的基金（近似去赢家）
    # 通过查看回测的 trades，找到利润贡献最大的基金
    # 这里先跑冠军，然后从结果中提取
    results.append(run_single("champion_for_winner_removal", champion, "P9.2_去赢家"))

    # P9.3: 温和市场模拟（通过调整参数模拟）
    # 难以直接模拟"涨幅减半"，改用 2025 H1（较温和期）作为代理
    results.append(run_single("champion_2025Q1Q2", {**champion, "start_date": "2025-01-05", "end_date": "2025-06-30"}, "P9.3_温和市场"))
    results.append(run_single("baseline_2025Q1Q2", {"exclude_uids": [], "fund_type_filter": "all", "max_sector_pct": 100, "start_date": "2025-01-05", "end_date": "2025-06-30"}, "P9.3_温和市场"))

    return results


# ═══════════════════════════════════════════════════════════
# P2.3: 基准对比表
# ═══════════════════════════════════════════════════════════

def run_p2_benchmark():
    """冠军 vs 沪深300 vs 纳斯达克 QDII"""
    top60 = get_top_n_uids(60)
    champion = {**BASE, "exclude_uids": top60, "fund_type_filter": "active", "max_sector_pct": 40}
    baseline = {**BASE, "exclude_uids": [], "fund_type_filter": "all", "max_sector_pct": 100}

    # 跑冠军和基线
    champ_r = run_single("champion", champion, "P2.3_基准对比")
    base_r = run_single("baseline", baseline, "P2.3_基准对比")

    # 从 fund_charts 计算 CSI300 和纳斯达克 QDII
    fund_charts_path = PROJECT / "data" / "fund_charts.json"
    if fund_charts_path.exists():
        charts = json.loads(fund_charts_path.read_text("utf-8"))
    else:
        charts = {}

    def calc_benchmark(code, start, end):
        pts = charts.get(code, [])
        if not pts:
            return None
        bm_start = None
        bm_end = None
        for p in pts:
            d = p.get("xAxis", "")
            y = float(p.get("yAxis", 0))
            if d == start:
                bm_start = y
            if d == end:
                bm_end = y
        if bm_start is None:
            for p in pts:
                if p.get("xAxis", "") >= start:
                    bm_start = float(p.get("yAxis", 0))
                    break
        if bm_end is None:
            for p in reversed(pts):
                if p.get("xAxis", "") <= end:
                    bm_end = float(p.get("yAxis", 0))
                    break
        if bm_start is not None and bm_end is not None:
            return ((100 + bm_end) / (100 + bm_start) - 1) * 100
        return None

    start = BASE["start_date"]
    end = BASE["end_date"]
    csi300 = calc_benchmark("110020", start, end)
    nasdaq_834 = calc_benchmark("000834", start, end)
    nasdaq_42 = calc_benchmark("270042", start, end)

    comparison = {
        "period": f"{start} ~ {end}",
        "champion": champ_r.get("return"),
        "baseline": base_r.get("return"),
        "csi300_110020": csi300,
        "nasdaq_000834": nasdaq_834,
        "nasdaq_270042": nasdaq_42,
    }

    print(f"\n{'='*60}")
    print(f"  P2.3 基准对比")
    print(f"{'='*60}")
    print(f"  冠军:     {comparison['champion']:.2f}%")
    print(f"  基线:     {comparison['baseline']:.2f}%")
    if csi300 is not None:
        print(f"  沪深300:  {csi300:.2f}%")
    if nasdaq_834 is not None:
        print(f"  纳指834:  {nasdaq_834:.2f}%")
    if nasdaq_42 is not None:
        print(f"  纳指042:  {nasdaq_42:.2f}%")

    (REPORTS_DIR / "benchmark_comparison.json").write_text(
        json.dumps(comparison, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  保存: {REPORTS_DIR / 'benchmark_comparison.json'}")
    return [champ_r, base_r]


# ═══════════════════════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════════════════════

def main():
    _ap = argparse.ArgumentParser()
    _ap.add_argument("--only", default=None, help="只跑指定组 (如 P0,P1,P2)")
    _args = _ap.parse_args()

    # P6+P7+P8+P5.1: 引擎拓展实验
    def run_p678():
        """P6 ATR 仓位 + P7 对冲 + P8 质量过滤 + P5.1 动态止撞"""
        top60 = get_top_n_uids(60)
        champion = {"exclude_uids": top60, "fund_type_filter": "active", "max_sector_pct": 40}
        results = []
        results.append(run_single("champion+atr", {**champion, "use_atr_sizing": True, "atr_target_risk": 0.15}, "P6_ATR"))
        results.append(run_single("champion+hedge", {**champion, "hedge_mode": True, "hedge_qdii_threshold": 60}, "P7_Hedge"))
        results.append(run_single("champion+quality", {**champion, "quality_filter": True}, "P8_Quality"))
        results.append(run_single("champion+dyn_sl", {**champion, "dynamic_stop_loss": True}, "P5.1_DynSL"))
        results.append(run_single("champion+all_ext", {**champion, "use_atr_sizing": True, "atr_target_risk": 0.15, "hedge_mode": True, "hedge_qdii_threshold": 60, "quality_filter": True, "dynamic_stop_loss": True}, "P678_All"))
        return results

    groups = {
        "P0": ("P0_梯度+组件隔离", run_p0),
        "P1": ("P1_缺失策略", run_p1),
        "P2": ("P2_一致性", run_p2),
        "P3": ("P3_风险面", run_p3),
        "P678": ("P678_拓展方向", run_p678),
        "P9": ("P9_过拟合", run_p9),
    }

    if _args.only:
        keys = [k.strip().upper() for k in _args.only.split(",")]
    else:
        keys = list(groups.keys())

    all_results = {}
    t0 = time.time()

    for key in keys:
        if key not in groups:
            print(f"[WARN] 未知组: {key}")
            continue
        label, func = groups[key]
        print(f"\n{'#'*60}")
        print(f"# 开始 {label}")
        print(f"{'#'*60}")
        results = func()
        all_results[key] = results
        # 立即保存
        (REPORTS_DIR / f"{key.lower()}_experiments.json").write_text(
            json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n  保存: {REPORTS_DIR / f'{key.lower()}_experiments.json'}")

    elapsed = time.time() - t0
    print(f"\n{'='*60}")
    print(f"  全部完成! 总耗时 {elapsed/60:.1f} 分钟")
    print(f"{'='*60}")

    # 汇总表
    print(f"\n{'='*80}")
    print(f"  {'实验名':<35} {'收益%':>8} {'回撤%':>8} {'交易':>6}")
    print(f"{'='*80}")
    for key, results in all_results.items():
        for r in results:
            if "return" in r:
                print(f"  {r['name']:<35} {r['return']:>8.2f} {r['dd']:>8.2f} {r['trades']:>6}")
            else:
                print(f"  {r['name']:<35} {'ERROR':>8}")

    # 保存汇总
    (REPORTS_DIR / "all_experiments_summary.json").write_text(
        json.dumps(all_results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n汇总已保存: {REPORTS_DIR / 'all_experiments_summary.json'}")


if __name__ == "__main__":
    main()
