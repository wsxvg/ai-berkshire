#!/usr/bin/env python3
"""回测入口：简化版五维评分回测。

先拉数据，再跑回测。

用法：
    python -m backtest.run                    # 完整运行
    python -m backtest.run --skip-fetch       # 跳过数据拉取
    python -m backtest.run --weights 25 20 20 15 20  # 自定义权重
"""
import sys, json, argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

BACKTEST_DIR = Path(__file__).parent
DATA_DIR = BACKTEST_DIR / "data"
REPORTS_DIR = BACKTEST_DIR / "reports"


def main():
    parser = argparse.ArgumentParser(description="AI Berkshire 五维评分回测")
    parser.add_argument("--skip-fetch", action="store_true", help="跳过数据拉取")
    parser.add_argument("--start", default="2026-01-05", help="回测开始日期")
    parser.add_argument("--end", default="2026-06-30", help="回测结束日期")
    parser.add_argument("--cash", type=float, default=10000, help="初始资金")
    parser.add_argument("--weights", type=float, nargs=5,
                        default=[25, 20, 20, 15, 20],
                        help="五维权重: 质量 成本 经理 动量 聪明钱")
    parser.add_argument("--min-score", type=float, default=3.3,
                        help="最低评分（低于此不买）")
    args = parser.parse_args()

    # ── Step 1: 数据准备 ──
    if not args.skip_fetch:
        print("=" * 50)
        print("Step 1: 拉取历史数据")
        print("=" * 50)
        from backtest.data.fetch_historical import main as fetch_main
        fetch_main()
    else:
        print("跳过数据拉取")

    # ── Step 2: 回测 ──
    print("\n" + "=" * 50)
    print("Step 2: 运行回测")
    print("=" * 50)

    config = {
        "start_date": args.start,
        "end_date": args.end,
        "initial_cash": args.cash,
        "min_score": args.min_score,
        "weights": {
            "quality": args.weights[0],
            "cost": args.weights[1],
            "manager": args.weights[2],
            "momentum": args.weights[3],
            "smart_money": args.weights[4],
        },
    }

    from backtest.engine.backtest import run_backtest
    result = run_backtest(config)

    # ── Step 3: 保存结果 ──
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_file = REPORTS_DIR / f"backtest_{args.start}_{args.end}.json"
    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n结果已保存到: {report_file}")

    # ── 对比不同权重组合（如果未指定） ──
    if len(sys.argv) <= 1:
        print("\n" + "=" * 50)
        print("Step 3: 权重对比测试")
        print("=" * 50)

        weight_combos = [
            ("默认 25/20/20/15/20", [25, 20, 20, 15, 20]),
            ("均权 20/20/20/20/20", [20, 20, 20, 20, 20]),
            ("重质量 35/15/20/15/15", [35, 15, 20, 15, 15]),
            ("重聪明钱 20/15/15/15/35", [20, 15, 15, 15, 35]),
            ("轻聪明钱 30/20/20/20/10", [30, 20, 20, 20, 10]),
        ]

        for name, w in weight_combos:
            if w == args.weights:
                continue
            c2 = dict(config)
            c2["weights"] = {
                "quality": w[0], "cost": w[1], "manager": w[2],
                "momentum": w[3], "smart_money": w[4],
            }
            r2 = run_backtest(c2)
            print(f"  {name}: 收益={r2['total_return']:+.2f}% "
                  f"回撤={r2['max_drawdown']:.2f}% "
                  f"交易={r2['trade_count']}次")

    print("\nBacktest complete!")


if __name__ == "__main__":
    main()