#!/usr/bin/env python3
"""五维评分权重网格搜索 + 评分与涨跌关联性分析

解决用户的核心问题:
  "五维评分的标准是什么? 不同权重配比有没有回测过?
   能不能通过反推找出最好的配比?"

本脚本做三件事:

Part 1 — 评分与未来收益的关联性分析
  从回测引擎的 scores_history 中提取每只基金在每个交易日的五维评分,
  然后跟踪该基金在随后 N 天的实际涨跌,
  计算每个维度评分与未来收益的相关系数。
  → 回答"哪个维度真正有预测力"

Part 2 — 权重网格搜索
  系统性地遍历五维权重的不同组合,
  找到回测收益最高+回撤最低的配比。
  → 回答"最好的配比是什么"

Part 3 — 凯利分配参数扫描
  固定权重为最佳, 扫描 kelly_fraction / kelly_cap / max_single_buy_pct,
  找到最优仓位控制参数。

用法:
  python backtest/weight_optimizer.py --part 1        # 只跑关联性分析
  python backtest/weight_optimizer.py --part 2        # 只跑权重网格搜索
  python backtest/weight_optimizer.py --part 3        # 只跑凯利参数扫描
  python backtest/weight_optimizer.py --all            # 全部跑 (≈30分钟)
"""
import sys, json, itertools, time, statistics, argparse
from pathlib import Path
from collections import defaultdict

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))

from backtest.engine.backtest import run_backtest, score_fund_backtest, _bisect_valid
from tools.fund_scorer import _float


# ═══════════════════════════════════════════════════════
# Part 1: 评分与未来收益关联性分析
# ═══════════════════════════════════════════════════════

def analyze_score_return_correlation():
    """分析五维评分与未来收益的相关系数。

    方法:
    1. 在回测过程中, 对每个交易日的每只候选基金记录五维评分
    2. 跟踪该基金在评分后 5/10/20/40 个交易日的实际收益
    3. 计算 Pearson 相关系数

    输出: 每个维度在未来不同时间窗口下的预测力
    """
    print("\n" + "=" * 70)
    print("Part 1: 五维评分与未来收益关联性分析")
    print("=" * 70)

    # 加载数据
    DATA_DIR = PROJECT / "backtest" / "data"
    charts = json.loads((DATA_DIR / "fund_charts.json").read_text("utf-8"))
    trading_by_date = json.loads((DATA_DIR / "trading_by_date_fixed.json").read_text("utf-8"))

    name_map_path = PROJECT / "data" / "fund_name_map.json"
    name_map = json.loads(name_map_path.read_text("utf-8")) if name_map_path.exists() else {}
    name_to_code = {v: k for k, v in name_map.items()}

    # 基金规则和经理数据
    CACHE_DIR = PROJECT / "data" / "fund_cache"
    import glob
    def load_cache(prefix):
        d = {}
        for f in glob.glob(str(CACHE_DIR / f"{prefix}_*.json")):
            code = Path(f).stem.replace(f"{prefix}_", "", 1)
            try:
                d[code] = json.loads(open(f, encoding="utf-8").read())
            except:
                pass
        return d

    fund_rules = load_cache("trade_rules")
    fund_managers = load_cache("fund_manager")
    fund_profiles = load_cache("fund_profile")

    # 回测日期范围
    dates = sorted(trading_by_date.keys())
    start_date = "2025-01-05"
    end_date = "2026-07-01"
    backtest_dates = [d for d in dates if start_date <= d <= end_date]

    # 采样: 每隔 10 个交易日采样一次 (减少计算量)
    sample_dates = backtest_dates[::10]
    print(f"  采样日期: {len(sample_dates)} 天 (每10天取1天)")
    print(f"  日期范围: {sample_dates[0]} ~ {sample_dates[-1]}")

    # 未来收益窗口 (交易日)
    horizons = [5, 10, 20, 40]
    # 收集: {dim: {horizon: [(score, future_return), ...]}}
    correlation_data = {
        dim: {h: [] for h in horizons}
        for dim in ["quality", "cost", "manager", "momentum", "smart_money", "total"]
    }

    # 对每个采样日期, 收集所有有大佬买入信号的基金评分
    scored_count = 0
    for dt in sample_dates:
        # 获取当天的交易信号
        day_records = trading_by_date.get(dt, [])
        fund_signals = defaultdict(lambda: {"buy_count": 0})
        for r in day_records:
            fn = r.get("fund_name", "")
            act = r.get("action", "")
            if "买入" in act or "转换入" in act or "加仓" in act or "定投" in act:
                fund_signals[fn]["buy_count"] += 1

        # 对每只有信号的基金评分
        for fn, signal in fund_signals.items():
            if signal["buy_count"] < 2:
                continue

            # 找基金代码
            code = name_to_code.get(fn)
            if not code or code not in charts:
                continue

            pts = charts.get(code, [])
            if len(pts) < 20:
                continue

            try:
                fs = score_fund_backtest(
                    code, fn, charts, None,
                    fund_rules.get(code), fund_managers.get(code),
                    dt, trading_by_date,
                    profile=fund_profiles.get(code)
                )

                # 记录评分
                scores = {
                    "quality": fs.quality.score if fs.quality else 2.5,
                    "cost": fs.cost.score if fs.cost else 3.0,
                    "manager": fs.manager.score if fs.manager else 2.5,
                    "momentum": fs.momentum.score if fs.momentum else 2.5,
                    "smart_money": fs.smart_money.score if fs.smart_money else 2.5,
                    "total": fs.total,
                }

                # 计算未来收益
                valid = _bisect_valid(pts, dt)
                if len(valid) < 2:
                    continue
                cur_nav = (100 + _float(valid[-1].get("yAxis", 0))) / 100

                for h in horizons:
                    idx = len(valid)  # 当前点在 pts 中的位置
                    future_idx = idx + h
                    if future_idx < len(pts):
                        future_y = _float(pts[future_idx].get("yAxis", 0))
                        future_nav = (100 + future_y) / 100
                        future_ret = (future_nav / cur_nav - 1) * 100
                        for dim, sc in scores.items():
                            correlation_data[dim][h].append((sc, future_ret))

                scored_count += 1
            except Exception:
                continue

    print(f"  评分基金次数: {scored_count}")

    # 计算 Pearson 相关系数
    def pearson(pairs):
        if len(pairs) < 10:
            return 0.0, 0
        xs = [p[0] for p in pairs]
        ys = [p[1] for p in pairs]
        n = len(pairs)
        mx = sum(xs) / n
        my = sum(ys) / n
        sx = sum((x - mx) ** 2 for x in xs) ** 0.5
        sy = sum((y - my) ** 2 for y in ys) ** 0.5
        if sx == 0 or sy == 0:
            return 0.0, n
        cov = sum((x - mx) * (y - my) for x, y in pairs)
        return cov / (sx * sy), n

    # 输出结果
    print(f"\n  {'维度':<12}", end="")
    for h in horizons:
        print(f"  {h}日相关系数(样本数)", end="")
    print()
    print("  " + "-" * 80)

    results = {}
    for dim in ["quality", "cost", "manager", "momentum", "smart_money", "total"]:
        dim_name = {"quality": "质量", "cost": "成本", "manager": "经理",
                    "momentum": "动量", "smart_money": "聪明钱", "total": "总分"}.get(dim, dim)
        print(f"  {dim_name:<10}", end="")
        results[dim] = {}
        for h in horizons:
            pairs = correlation_data[dim][h]
            r, n = pearson(pairs)
            results[dim][h] = {"corr": round(r, 4), "samples": n}
            print(f"  r={r:>+.4f} (n={n:>4})", end="")
        print()

    # 分位数分析: 高分组 vs 低分组的实际收益
    print(f"\n  ── 分位数分析 (高分组 vs 低分组未来{horizons[-1]}日收益) ──")
    for dim in ["quality", "cost", "manager", "momentum", "smart_money", "total"]:
        dim_name = {"quality": "质量", "cost": "成本", "manager": "经理",
                    "momentum": "动量", "smart_money": "聪明钱", "total": "总分"}.get(dim, dim)
        pairs = correlation_data[dim][horizons[-1]]
        if len(pairs) < 20:
            continue
        pairs.sort(key=lambda x: x[0])
        n = len(pairs)
        top_q = pairs[int(n * 0.75):]  # 高分25%
        bot_q = pairs[:int(n * 0.25)]  # 低分25%
        top_avg = statistics.mean(p[1] for p in top_q) if top_q else 0
        bot_avg = statistics.mean(p[1] for p in bot_q) if bot_q else 0
        print(f"  {dim_name:<10}: 高分均值={top_avg:>+7.2f}%  低分均值={bot_avg:>+7.2f}%  差值={top_avg-bot_avg:>+7.2f}%")

    # 保存结果
    report_path = PROJECT / "backtest" / "reports" / "score_correlation_analysis.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n  结果已保存: {report_path}")

    return results


# ═══════════════════════════════════════════════════════
# Part 2: 权重网格搜索
# ═══════════════════════════════════════════════════════

def grid_search_weights():
    """系统性遍历五维权重组合, 找最优配比。"""
    print("\n" + "=" * 70)
    print("Part 2: 五维权重网格搜索")
    print("=" * 70)

    # 加载冠军配置作为基准
    best_config_path = PROJECT / "data" / "evolution" / "best_config.json"
    base_config = json.loads(best_config_path.read_text("utf-8"))
    base_cfg = dict(base_config.get("config", base_config))

    # 基准权重
    base_weights = base_cfg.get("weights", {"quality": 25, "cost": 20, "manager": 20, "momentum": 15, "smart_money": 20})

    # 网格定义: 每个维度的候选权重
    # 为了控制组合数量, 用粗网格先找大致方向, 再细网格精调
    # Phase 1: 粗网格 (每维 3 档: 低/中/高)
    grid_coarse = {
        "quality": [15, 25, 35],
        "cost": [10, 20, 30],
        "manager": [10, 20, 30],
        "momentum": [10, 15, 25],
        "smart_money": [15, 20, 30],
    }

    # 生成所有组合 (3^5 = 243 组合, 但过滤掉总和为0的)
    dims = list(grid_coarse.keys())
    all_combos = list(itertools.product(*[grid_coarse[d] for d in dims]))
    print(f"  粗网格组合数: {len(all_combos)}")
    print(f"  基准权重: {base_weights}")
    print(f"  基准收益: {base_config.get('performance', {}).get('total_return', 'N/A')}%")

    results = []
    best_return = -999
    best_cfg = None
    best_sharpe = -999
    best_sharpe_cfg = None

    for i, combo in enumerate(all_combos):
        weights = dict(zip(dims, combo))
        cfg = dict(base_cfg)
        cfg["weights"] = weights
        cfg["start_date"] = "2025-01-05"
        cfg["end_date"] = "2026-07-01"

        try:
            t0 = time.time()
            r = run_backtest(cfg)
            elapsed = time.time() - t0

            total_return = r.get("total_return", 0)
            max_dd = r.get("max_drawdown", 100)
            trades = r.get("trade_count", 0)
            sharpe = total_return / max(max_dd, 1) if max_dd > 0 else 0

            result = {
                "weights": weights,
                "return": round(total_return, 2),
                "dd": round(max_dd, 2),
                "sharpe": round(sharpe, 2),
                "trades": trades,
                "elapsed": round(elapsed, 1),
            }
            results.append(result)

            if total_return > best_return:
                best_return = total_return
                best_cfg = weights
            if sharpe > best_sharpe:
                best_sharpe = sharpe
                best_sharpe_cfg = weights

            if (i + 1) % 10 == 0 or total_return > 55:
                print(f"  [{i+1}/{len(all_combos)}] Q{weights['quality']}/C{weights['cost']}/M{weights['manager']}/Mo{weights['momentum']}/SM{weights['smart_money']} → {total_return:+.2f}% dd={max_dd:.1f}% sharpe={sharpe:.2f}")

        except Exception as e:
            print(f"  [{i+1}/{len(all_combos)}] FAIL: {e}")

    # 排序输出 Top 10
    results.sort(key=lambda x: x["return"], reverse=True)
    print(f"\n  ── Top 10 收益最高 ──")
    print(f"  {'排名':<4} {'质量':>4} {'成本':>4} {'经理':>4} {'动量':>4} {'聪明钱':>6} {'收益':>8} {'回撤':>6} {'夏普':>6} {'交易':>4}")
    for rank, r in enumerate(results[:10], 1):
        w = r["weights"]
        print(f"  {rank:<4} {w['quality']:>4} {w['cost']:>4} {w['manager']:>4} {w['momentum']:>4} {w['smart_money']:>6} {r['return']:>+7.2f}% {r['dd']:>5.2f}% {r['sharpe']:>6.2f} {r['trades']:>4}")

    results.sort(key=lambda x: x["sharpe"], reverse=True)
    print(f"\n  ── Top 10 夏普最高 ──")
    print(f"  {'排名':<4} {'质量':>4} {'成本':>4} {'经理':>4} {'动量':>4} {'聪明钱':>6} {'收益':>8} {'回撤':>6} {'夏普':>6} {'交易':>4}")
    for rank, r in enumerate(results[:10], 1):
        w = r["weights"]
        print(f"  {rank:<4} {w['quality']:>4} {w['cost']:>4} {w['manager']:>4} {w['momentum']:>4} {w['smart_money']:>6} {r['return']:>+7.2f}% {r['dd']:>5.2f}% {r['sharpe']:>6.2f} {r['trades']:>4}")

    # 保存结果
    report_path = PROJECT / "backtest" / "reports" / "weight_grid_search.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n  结果已保存: {report_path}")

    # Phase 2: 细网格 (基于 Phase 1 最佳方向)
    if best_cfg:
        print(f"\n  ── Phase 2: 细网格精调 (基于最佳方向 {best_cfg}) ──")
        grid_fine = {}
        for d in dims:
            base_v = best_cfg[d]
            grid_fine[d] = sorted(set([max(5, base_v - 5), base_v, min(40, base_v + 5)]))

        fine_combos = list(itertools.product(*[grid_fine[d] for d in dims]))
        print(f"  细网格组合数: {len(fine_combos)}")

        fine_results = []
        for i, combo in enumerate(fine_combos):
            weights = dict(zip(dims, combo))
            cfg = dict(base_cfg)
            cfg["weights"] = weights
            cfg["start_date"] = "2025-01-05"
            cfg["end_date"] = "2026-07-01"

            try:
                r = run_backtest(cfg)
                total_return = r.get("total_return", 0)
                max_dd = r.get("max_drawdown", 100)
                trades = r.get("trade_count", 0)
                sharpe = total_return / max(max_dd, 1) if max_dd > 0 else 0

                fine_results.append({
                    "weights": weights,
                    "return": round(total_return, 2),
                    "dd": round(max_dd, 2),
                    "sharpe": round(sharpe, 2),
                    "trades": trades,
                })

                if (i + 1) % 5 == 0:
                    print(f"  [{i+1}/{len(fine_combos)}] {weights} → {total_return:+.2f}% dd={max_dd:.1f}%")
            except Exception as e:
                pass

        fine_results.sort(key=lambda x: x["return"], reverse=True)
        print(f"\n  ── 细网格 Top 5 ──")
        for rank, r in enumerate(fine_results[:5], 1):
            w = r["weights"]
            print(f"  {rank}. Q{w['quality']}/C{w['cost']}/M{w['manager']}/Mo{w['momentum']}/SM{w['smart_money']} → {r['return']:+.2f}% dd={r['dd']:.2f}% sharpe={r['sharpe']:.2f}")

        fine_report_path = PROJECT / "backtest" / "reports" / "weight_grid_fine.json"
        fine_report_path.write_text(json.dumps(fine_results, ensure_ascii=False, indent=2), encoding="utf-8")

    return results


# ═══════════════════════════════════════════════════════
# Part 3: 凯利分配参数扫描
# ═══════════════════════════════════════════════════════

def scan_kelly_params():
    """固定权重为冠军配置, 扫描凯利分配参数。"""
    print("\n" + "=" * 70)
    print("Part 3: 凯利分配参数扫描")
    print("=" * 70)

    best_config_path = PROJECT / "data" / "evolution" / "best_config.json"
    base_cfg = json.loads(best_config_path.read_text("utf-8")).get("config", {})

    # 参数扫描范围
    kelly_caps = [0.25, 0.30, 0.35, 0.40, 0.50]
    kelly_fractions = [0.3, 0.5, 0.7, 1.0]
    max_single_buys = [0.20, 0.25, 0.30, 0.40]

    results = []
    total = len(kelly_caps) * len(kelly_fractions) * len(max_single_buys)
    print(f"  组合数: {total}")
    print(f"  基准: kelly_cap={base_cfg.get('kelly_cap')}, fraction=0.5, max_single_buy=0.30")

    idx = 0
    for kc in kelly_caps:
        for kf in kelly_fractions:
            for msb in max_single_buys:
                idx += 1
                cfg = dict(base_cfg)
                cfg["kelly_cap"] = kc
                cfg["kelly_fraction"] = kf
                cfg["max_single_buy_pct"] = msb
                cfg["start_date"] = "2025-01-05"
                cfg["end_date"] = "2026-07-01"

                try:
                    t0 = time.time()
                    r = run_backtest(cfg)
                    elapsed = time.time() - t0

                    total_return = r.get("total_return", 0)
                    max_dd = r.get("max_drawdown", 100)
                    trades = r.get("trade_count", 0)
                    sharpe = total_return / max(max_dd, 1) if max_dd > 0 else 0

                    result = {
                        "kelly_cap": kc,
                        "kelly_fraction": kf,
                        "max_single_buy_pct": msb,
                        "return": round(total_return, 2),
                        "dd": round(max_dd, 2),
                        "sharpe": round(sharpe, 2),
                        "trades": trades,
                        "elapsed": round(elapsed, 1),
                    }
                    results.append(result)

                    if total_return > 55 or sharpe > 2.0:
                        print(f"  [{idx}/{total}] kc={kc} kf={kf} msb={msb} → {total_return:+.2f}% dd={max_dd:.1f}% sharpe={sharpe:.2f}")
                except Exception as e:
                    print(f"  [{idx}/{total}] FAIL: {e}")

    results.sort(key=lambda x: x["return"], reverse=True)
    print(f"\n  ── Top 10 凯利参数 ──")
    print(f"  {'排名':<4} {'kelly_cap':>9} {'fraction':>8} {'max_buy':>7} {'收益':>8} {'回撤':>6} {'夏普':>6} {'交易':>4}")
    for rank, r in enumerate(results[:10], 1):
        print(f"  {rank:<4} {r['kelly_cap']:>9} {r['kelly_fraction']:>8} {r['max_single_buy_pct']:>7} {r['return']:>+7.2f}% {r['dd']:>5.2f}% {r['sharpe']:>6.2f} {r['trades']:>4}")

    report_path = PROJECT / "backtest" / "reports" / "kelly_param_scan.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n  结果已保存: {report_path}")

    return results


# ═══════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="五维权重优化+关联分析")
    parser.add_argument("--part", type=int, choices=[1, 2, 3], help="只运行指定部分")
    parser.add_argument("--all", action="store_true", help="全部运行")
    args = parser.parse_args()

    if args.all or args.part == 1:
        analyze_score_return_correlation()
    if args.all or args.part == 2:
        grid_search_weights()
    if args.all or args.part == 3:
        scan_kelly_params()


if __name__ == "__main__":
    main()
