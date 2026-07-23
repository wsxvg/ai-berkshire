#!/usr/bin/env python3
"""散户2个月实盘模拟。

解决三个核心问题:
1. 大佬无限子弹 → 散户月定投2000，初始5000
2. 金额规模差异 → 散户小额，无滑点，费率正常
3. 大佬买入时间 vs 我们实际买入时间 → 用最近2个月数据验证

用法:
  # 等Phase 1完成后，用Top50策略跑2个月模拟
  python backtest/retail_simulation.py --input backtest/results_revalidation/top50.json

  # 也可以指定日期范围
  python backtest/retail_simulation.py --start 2026-05-23 --end 2026-07-23

  # 只跑散户策略
  python backtest/retail_simulation.py --retail-only
"""
import json, sys, time, argparse
from pathlib import Path
from copy import deepcopy

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))

from backtest.engine.backtest import run_backtest
from backtest.run_all_strategies import RETAIL_STRATEGIES, RETAIL_BASE, run_one


def run_retail_sim(start_date, end_date, strategies, initial_cash=5000, monthly_injection=2000):
    """运行散户模拟。"""
    results = []
    for name, desc, config, base in strategies:
        b = deepcopy(base)
        b.update(config)
        b["start_date"] = start_date
        b["end_date"] = end_date
        b["initial_cash"] = config.get("initial_cash", initial_cash)
        b["monthly_injection"] = config.get("monthly_injection", monthly_injection)

        t0 = time.time()
        try:
            r = run_backtest(b, clear_cache=(len(results) == 0))
            elapsed = time.time() - t0

            from datetime import datetime
            d1 = datetime.strptime(start_date, "%Y-%m-%d")
            d2 = datetime.strptime(end_date, "%Y-%m-%d")
            days = max((d2 - d1).days, 1)
            years = days / 365.25
            ann = ((1 + r["total_return"] / 100) ** (1 / years) - 1) * 100 if years > 0 else 0

            total_invested = b["initial_cash"] + r.get("monthly_injections", 0)
            actual_profit = r["final_value"] - total_invested

            result = {
                "name": name,
                "desc": desc,
                "return_pct": r["total_return"],
                "annualized_pct": round(ann, 1),
                "final_value": round(r["final_value"], 2),
                "total_invested": total_invested,
                "actual_profit": round(actual_profit, 2),
                "max_drawdown": r["max_drawdown"],
                "trades": r["trade_count"],
                "holdings": r["final_holdings"],
                "sharpe": round(r["total_return"] / max(r["max_drawdown"], 1), 2),
                "fees": round(r.get("total_fees", 0), 2),
                "injected": r.get("monthly_injections", 0),
                "elapsed_sec": round(elapsed, 1),
                "config": b,
            }
            results.append(result)
            print(f"  {name:30s} ret={r['total_return']:+6.2f}% profit={actual_profit:+8.0f} "
                  f"trades={r['trade_count']:3d} dd={r['max_drawdown']:5.2f}% "
                  f"invested={total_invested} final={r['final_value']:.0f} ({elapsed:.0f}s)")
        except Exception as e:
            import traceback
            print(f"  {name:30s} FAILED: {e}")
            traceback.print_exc()

    return results


def main():
    parser = argparse.ArgumentParser(description="散户2个月实盘模拟")
    parser.add_argument("--start", type=str, default="2026-05-23", help="开始日期")
    parser.add_argument("--end", type=str, default="2026-07-23", help="结束日期")
    parser.add_argument("--input", type=str, default=None, help="Phase 1 top50.json路径")
    parser.add_argument("--retail-only", action="store_true", help="只跑散户策略")
    parser.add_argument("--output", type=str, default="backtest/results_revalidation/retail_sim.json")
    parser.add_argument("--initial-cash", type=int, default=5000, help="初始资金")
    parser.add_argument("--monthly-injection", type=int, default=2000, help="每月定投金额")
    args = parser.parse_args()

    strategies = []

    # 1. 散户策略系列
    for s in RETAIL_STRATEGIES:
        base = deepcopy(RETAIL_BASE)
        strategies.append((s["name"], s["desc"], s["config"], base))

    # 2. 如果指定了top50.json，也跑那些策略（用散户资金规模）
    if args.input and not args.retail_only:
        top50_path = Path(args.input)
        if top50_path.exists():
            data = json.loads(top50_path.read_text(encoding="utf-8"))
            top_strategies = data.get("top50", data.get("strategies", []))
            print(f"从 {top50_path} 加载 {len(top_strategies)} 个策略")
            for s in top_strategies[:20]:  # 只取前20，避免太多
                cfg = s.get("config", s)
                name = f"Top_{s.get('name', 'unknown')[:20]}"
                base = deepcopy(RETAIL_BASE)
                strategies.append((name, "Phase1 Top策略(散户资金)", cfg, base))
        else:
            print(f"⚠ 文件不存在: {top50_path}")

    # 3. 基础策略也用散户资金跑
    if not args.retail_only and not args.input:
        from backtest.run_all_strategies import BASE_STRATEGIES, BASE
        for s in BASE_STRATEGIES[:6]:  # 取前6个基础策略
            base = deepcopy(BASE)
            base["initial_cash"] = args.initial_cash
            base["monthly_injection"] = args.monthly_injection
            strategies.append((f"基础_{s['name']}", s["desc"], s["config"], base))

    print(f"\n{'='*80}")
    print(f"散户实盘模拟: {args.start} ~ {args.end} ({len(strategies)} 个策略)")
    print(f"初始资金: {args.initial_cash} | 每月定投: {args.monthly_injection}")
    print(f"{'='*80}\n")

    results = run_retail_sim(args.start, args.end, strategies,
                             initial_cash=args.initial_cash,
                             monthly_injection=args.monthly_injection)

    # 排序
    results.sort(key=lambda x: x["actual_profit"], reverse=True)

    # 保存
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({
            "strategies": results,
            "period": f"{args.start} ~ {args.end}",
            "initial_cash": args.initial_cash,
            "monthly_injection": args.monthly_injection,
        }, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*80}")
    print(f"散户模拟结果: {len(results)} 个策略")
    print(f"{'='*80}")
    print(f"{'策略':32s} {'收益率':>7s} {'绝对盈亏':>8s} {'投入':>6s} {'终值':>8s} {'交易':>4s} {'回撤':>6s}")
    print(f"{'-'*80}")
    for r in results:
        print(f"{r['name']:32s} {r['return_pct']:+6.2f}% {r['actual_profit']:+7.0f} "
              f"{r['total_invested']:5d} {r['final_value']:8.0f} "
              f"{r['trades']:3d} {r['max_drawdown']:5.2f}%")

    # 关键指标
    if results:
        best = results[0]
        worst = results[-1]
        print(f"\n最佳: {best['name']} 赚了 {best['actual_profit']:+.0f} 元 ({best['return_pct']:+.2f}%)")
        print(f"最差: {worst['name']} {'赚了' if worst['actual_profit'] > 0 else '亏了'} {abs(worst['actual_profit']):.0f} 元 ({worst['return_pct']:+.2f}%)")
        profitable = sum(1 for r in results if r["actual_profit"] > 0)
        print(f"盈亏比: {profitable}/{len(results)} 策略盈利")

    print(f"\n保存到 {out_path}")


if __name__ == "__main__":
    main()
