#!/usr/bin/env python3
"""滚动窗口回测 + 防过拟合验证。

对给定策略在多个时间窗口上运行回测，检查一致性和稳健性。
只有跨窗口表现一致的策略才被认为是"非过拟合"的。

用法:
  # 对 top50.json 中的策略做滚动窗口验证
  python backtest/rolling_window.py --input results_revalidation/top50.json --output results_revalidation/rolling_window.json

  # 分片模式（GitHub Actions 并行）
  python backtest/rolling_window.py --input top50.json --chunk 0 --total 20
"""
import json, sys, time, argparse, statistics
from pathlib import Path
from copy import deepcopy

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))

from backtest.engine.backtest import run_backtest

# ── 滚动窗口定义 ──
# 5个1年期窗口（6个月步进）+ 全量3年期
ROLLING_WINDOWS = [
    ("W1_2023H2", "2023-07-17", "2024-07-17"),
    ("W2_2024H1", "2024-01-17", "2025-01-17"),
    ("W3_2024H2", "2024-07-17", "2025-07-17"),
    ("W4_2025H1", "2025-01-17", "2026-01-17"),
    ("W5_2025H2", "2025-07-17", "2026-07-17"),
    ("FULL_3Y",   "2023-07-17", "2026-07-17"),
]

# ── 防过拟合标准 ──
ANTI_OVERFIT_CRITERIA = {
    "min_return_per_window": -15.0,     # 每个窗口收益不低于 -15%
    "max_drawdown_per_window": 40.0,    # 每个窗口最大回撤不超过 40%
    "min_positive_windows": 4,          # 至少 4/5 个1年期窗口为正收益
    "max_return_stddev": 25.0,          # 窗口间收益标准差不超过 25%
    "min_full_period_return": 10.0,     # 全量3年收益至少 10%
    "min_full_period_sharpe": 0.5,      # 全量3年夏普至少 0.5
    "max_worst_window_loss": -20.0,     # 最差窗口收益不低于 -20%
}


def run_single_window(config, start_date, end_date):
    """在单个窗口上运行回测，返回结果。"""
    cfg = deepcopy(config)
    cfg["start_date"] = start_date
    cfg["end_date"] = end_date
    try:
        r = run_backtest(cfg, clear_cache=False)  # 滚动窗口复用缓存
        days = 0
        from datetime import datetime
        try:
            d1 = datetime.strptime(start_date, "%Y-%m-%d")
            d2 = datetime.strptime(end_date, "%Y-%m-%d")
            days = (d2 - d1).days
        except Exception:
            days = 365
        years = max(days / 365.25, 0.1)
        ann = ((1 + r["total_return"] / 100) ** (1 / years) - 1) * 100
        return {
            "return": r["total_return"],
            "annualized": ann,
            "dd": r["max_drawdown"],
            "trades": r["trade_count"],
            "sharpe": r["total_return"] / max(r["max_drawdown"], 1),
        }
    except Exception as e:
        print(f"    FAILED: {e}")
        return None


def validate_anti_overfit(window_results):
    """检查策略是否通过防过拟合标准。

    window_results: {window_name: {return, dd, sharpe, ...}}
    返回: (pass: bool, issues: [str], score: float)
    """
    issues = []
    criteria = ANTI_OVERFIT_CRITERIA

    # 只看1年期窗口（排除 FULL_3Y）
    yearly_windows = {k: v for k, v in window_results.items() if k != "FULL_3Y"}
    full = window_results.get("FULL_3Y", {})

    # 检查1: 每个窗口收益不低于阈值
    for name, r in yearly_windows.items():
        if r["return"] < criteria["min_return_per_window"]:
            issues.append(f"{name}: return={r['return']:.1f}% < {criteria['min_return_per_window']}%")

    # 检查2: 每个窗口回撤不超过阈值
    for name, r in yearly_windows.items():
        if r["dd"] > criteria["max_drawdown_per_window"]:
            issues.append(f"{name}: dd={r['dd']:.1f}% > {criteria['max_drawdown_per_window']}%")

    # 检查3: 至少 N 个正收益窗口
    positive_count = sum(1 for r in yearly_windows.values() if r["return"] > 0)
    if positive_count < criteria["min_positive_windows"]:
        issues.append(f"positive_windows={positive_count} < {criteria['min_positive_windows']}")

    # 检查4: 窗口间收益标准差
    returns = [r["return"] for r in yearly_windows.values()]
    if len(returns) >= 2:
        stddev = statistics.stdev(returns)
        if stddev > criteria["max_return_stddev"]:
            issues.append(f"return_stddev={stddev:.1f}% > {criteria['max_return_stddev']}%")

    # 检查5: 全量收益
    if full.get("return", 0) < criteria["min_full_period_return"]:
        issues.append(f"full_return={full.get('return', 0):.1f}% < {criteria['min_full_period_return']}%")

    # 检查6: 全量夏普
    if full.get("sharpe", 0) < criteria["min_full_period_sharpe"]:
        issues.append(f"full_sharpe={full.get('sharpe', 0):.2f} < {criteria['min_full_period_sharpe']}")

    # 检查7: 最差窗口
    worst_return = min(r["return"] for r in yearly_windows.values()) if yearly_windows else 0
    if worst_return < criteria["max_worst_window_loss"]:
        issues.append(f"worst_window={worst_return:.1f}% < {criteria['max_worst_window_loss']}%")

    # 综合评分: 全量收益 * 一致性系数
    consistency = 1.0
    if yearly_windows:
        avg_return = statistics.mean(r["return"] for r in yearly_windows.values())
        if len(returns) >= 2:
            stddev = statistics.stdev(returns)
            consistency = max(0.1, 1.0 - stddev / 50.0)  # stddev=0→1.0, stddev=50→0.0
        min_return = min(r["return"] for r in yearly_windows.values())
        # 最差窗口惩罚: 如果最差窗口为负，降低一致性
        if min_return < 0:
            consistency *= max(0.3, 1.0 + min_return / 50.0)  # -50%→0.3, 0%→1.0

    full_return = full.get("return", 0)
    anti_overfit_score = full_return * consistency

    passed = len(issues) == 0
    return passed, issues, anti_overfit_score


def main():
    parser = argparse.ArgumentParser(description="滚动窗口回测 + 防过拟合验证")
    parser.add_argument("--input", type=str, required=True, help="输入JSON文件（含策略列表）")
    parser.add_argument("--output", type=str, default="rolling_window.json", help="输出文件")
    parser.add_argument("--chunk", type=int, default=0, help="当前分片ID (0-based)")
    parser.add_argument("--total", type=int, default=1, help="总分片数")
    parser.add_argument("--top-n", type=int, default=0, help="只验证前N个策略（0=全部）")
    args = parser.parse_args()

    # 加载策略
    input_path = Path(args.input)
    if not input_path.is_absolute():
        input_path = PROJECT / "backtest" / input_path
    data = json.loads(input_path.read_text("utf-8"))

    # 提取策略列表
    if "strategies" in data:
        strategies = data["strategies"]
    elif "top20" in data:
        strategies = data["top20"]
    elif "top50" in data:
        strategies = data["top50"]
    elif isinstance(data, list):
        strategies = data
    else:
        print(f"无法识别的输入格式: {list(data.keys())}")
        return

    # 只验证前N个
    if args.top_n > 0:
        strategies = strategies[:args.top_n]

    # 分片
    if args.total > 1:
        chunk_size = (len(strategies) + args.total - 1) // args.total
        start_idx = args.chunk * chunk_size
        end_idx = min(start_idx + chunk_size, len(strategies))
        strategies = strategies[start_idx:end_idx]
        print(f"分片 {args.chunk}/{args.total}: 策略 [{start_idx}:{end_idx}] = {len(strategies)} 个")

    print(f"\n{'='*70}")
    print(f"滚动窗口回测: {len(strategies)} 个策略 × {len(ROLLING_WINDOWS)} 个窗口")
    print(f"窗口: {[w[0] for w in ROLLING_WINDOWS]}")
    print(f"{'='*70}\n")

    results = []
    t_start = time.time()

    for i, s in enumerate(strategies):
        name = s.get("name", f"strategy_{i}")
        config = s.get("config", s)  # 兼容两种格式

        print(f"\n[{i+1}/{len(strategies)}] {name}")
        window_results = {}
        for win_name, start_d, end_d in ROLLING_WINDOWS:
            t0 = time.time()
            r = run_single_window(config, start_d, end_d)
            elapsed = time.time() - t0
            if r:
                window_results[win_name] = r
                print(f"  {win_name}: ret={r['return']:+7.2f}% dd={r['dd']:6.2f}% "
                      f"sharpe={r['sharpe']:5.2f} trades={r['trades']:3d} ({elapsed:.0f}s)")
            else:
                print(f"  {win_name}: FAILED")

        if not window_results:
            continue

        # 防过拟合验证
        passed, issues, ao_score = validate_anti_overfit(window_results)

        # 计算一致性指标
        yearly_returns = [r["return"] for k, r in window_results.items() if k != "FULL_3Y"]
        yearly_dds = [r["dd"] for k, r in window_results.items() if k != "FULL_3Y"]
        full = window_results.get("FULL_3Y", {})

        result = {
            "name": name,
            "desc": s.get("desc", ""),
            "config": config,
            "windows": window_results,
            "full_return": full.get("return", 0),
            "full_dd": full.get("dd", 0),
            "full_sharpe": full.get("sharpe", 0),
            "avg_yearly_return": statistics.mean(yearly_returns) if yearly_returns else 0,
            "std_yearly_return": statistics.stdev(yearly_returns) if len(yearly_returns) >= 2 else 0,
            "min_yearly_return": min(yearly_returns) if yearly_returns else 0,
            "max_yearly_return": max(yearly_returns) if yearly_returns else 0,
            "avg_yearly_dd": statistics.mean(yearly_dds) if yearly_dds else 0,
            "max_yearly_dd": max(yearly_dds) if yearly_dds else 0,
            "positive_windows": sum(1 for r in yearly_returns if r > 0),
            "anti_overfit_passed": passed,
            "anti_overfit_issues": issues,
            "anti_overfit_score": ao_score,
        }
        results.append(result)

        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"  → {status} | AO_score={ao_score:.2f} | "
              f"avg={result['avg_yearly_return']:+.1f}% std={result['std_yearly_return']:.1f}% "
              f"min={result['min_yearly_return']:+.1f}%")
        if issues:
            for iss in issues[:3]:
                print(f"    ⚠ {iss}")

    elapsed_total = time.time() - t_start

    # 按防过拟合分数排序
    results.sort(key=lambda x: x["anti_overfit_score"], reverse=True)

    # 打印最终排行
    print(f"\n{'='*70}")
    print(f"滚动窗口回测完成: {len(results)}/{len(strategies)} 成功, 耗时 {elapsed_total:.0f}s")
    print(f"{'='*70}")
    print(f"{'策略':42s} {'全量收益':>8s} {'年均':>6s} {'标准差':>6s} {'最差':>6s} {'AO分':>6s} {'状态':>6s}")
    print(f"{'-'*85}")
    for r in results[:30]:
        status = "PASS" if r["anti_overfit_passed"] else "FAIL"
        print(f"{r['name']:42s} {r['full_return']:>+7.2f}% {r['avg_yearly_return']:>+5.1f}% "
              f"{r['std_yearly_return']:>5.1f}% {r['min_yearly_return']:>+5.1f}% "
              f"{r['anti_overfit_score']:>5.1f} {status:>6s}")

    # 统计通过率
    passed_count = sum(1 for r in results if r["anti_overfit_passed"])
    print(f"\n防过拟合通过率: {passed_count}/{len(results)} ({passed_count/len(results)*100:.0f}%)")

    # 保存
    out_dir = PROJECT / "backtest" / "results_revalidation"
    out_dir.mkdir(parents=True, exist_ok=True)
    suffix = f"_chunk{args.chunk}" if args.total > 1 else ""
    out_file = out_dir / args.output.replace(".json", f"{suffix}.json")
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump({
            "strategies": results,
            "windows": [w[0] for w in ROLLING_WINDOWS],
            "criteria": ANTI_OVERFIT_CRITERIA,
            "total": len(strategies),
            "succeeded": len(results),
            "passed": passed_count,
            "elapsed_sec": elapsed_total,
        }, f, ensure_ascii=False, indent=2)
    print(f"\n保存到 {out_file}")


if __name__ == "__main__":
    main()
