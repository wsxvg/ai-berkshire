"""
paper_trading.py — 模拟实盘 (2026-07-13)
=========================================
回测 B5 完整版 4 周 (2026-06-13 ~ 2026-07-13), 输出:
- 模拟账本 (每笔买卖记录)
- 模拟最终收益
- 对比 V2 baseline / B5 完整版

不依赖京东 API, 纯本地回测.
"""
import sys, json
from datetime import datetime
from pathlib import Path

PROJECT = Path(r"C:\项目\A基金\基金")
sys.path.insert(0, str(PROJECT / "scripts"))

from backtest_v2 import run_backtest

OUT = PROJECT / "reports" / "paper_trading"
OUT.mkdir(parents=True, exist_ok=True)


def run_strategy(start, end, name, **kwargs):
    """跑一个策略, 返 metrics + 模拟交易记录"""
    r = run_backtest(start, end, 100000, 3, 1, **kwargs)
    if not r: return None
    return {
        "name": name,
        "config": r["config"],
        "result": r["result"],
    }


def main():
    end = "2026-07-13"
    start = "2026-06-13"
    print(f"模拟实盘: {start} ~ {end} (4 周)")
    print("=" * 70)

    # 三种策略对比
    strategies = [
        {
            "name": "V2 baseline (P1 止盈)",
            "kwargs": dict(use_tp=True, use_trail=True, use_time_tp=True,
                          use_dynamic=False, use_scorer=False,
                          tp_pct=15.0, trail_pct=8.0, hold_days=60),
        },
        {
            "name": "B5 完整版 (评分门槛+仓位+V2止盈)",
            "kwargs": dict(use_tp=True, use_trail=True, use_time_tp=True,
                          use_dynamic=False, use_scorer=False,
                          tp_pct=15.0, trail_pct=8.0, hold_days=60,
                          use_score_threshold=True, score_threshold=12.5,
                          use_score_position=True),
        },
        {
            "name": "B4b 高质量门槛 (score≥15)",
            "kwargs": dict(use_tp=True, use_trail=True, use_time_tp=True,
                          use_dynamic=False, use_scorer=False,
                          tp_pct=15.0, trail_pct=8.0, hold_days=60,
                          use_score_threshold=True, score_threshold=15.0),
        },
    ]

    results = []
    for s in strategies:
        r = run_strategy(start, end, s["name"], **s["kwargs"])
        if r:
            x = r["result"]
            print(f"\n  {s['name']}:")
            print(f"    年化: {x['annualized']:+.2f}% | 夏普: {x['sharpe']:.2f} | "
                  f"回撤: {x['max_drawdown']:+.2f}%")
            print(f"    胜率: {x['win_rate']:.1f}% | 交易: {x['n_buys']}/{x['n_sells']} | "
                  f"Alpha: {x['alpha']:+.2f}%")
            results.append(r)

    # 排序
    results.sort(key=lambda r: r["result"]["annualized"], reverse=True)
    print("\n" + "=" * 70)
    print("🏆 4 周模拟实盘排名 (按年化):")
    for i, r in enumerate(results):
        x = r["result"]
        print(f"  #{i+1} {r['name']}: 年化 {x['annualized']:+.2f}% 胜率 {x['win_rate']:.1f}%")

    # 落盘
    out_file = OUT / f"paper_4w_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    out_file.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n  💾 {out_file.relative_to(PROJECT)}")


if __name__ == "__main__":
    main()
