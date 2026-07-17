#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P1 止盈参数扫描: tp_pct × trail_pct"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from backtest_v2 import run_backtest
import json
from datetime import datetime

results = []
configs = [
    # (tp, trail, label)
    (10, 5, "tp10 trail5"),
    (15, 6, "tp15 trail6"),
    (20, 8, "tp20 trail8 (默认)"),
    (25, 10, "tp25 trail10"),
    (30, 12, "tp30 trail12"),
    (15, 5, "tp15 trail5"),
    (20, 5, "tp20 trail5"),
    (20, 10, "tp20 trail10"),
    (25, 8, "tp25 trail8"),
    (15, 8, "tp15 trail8"),
    (35, 10, "tp35 trail10"),
    (40, 12, "tp40 trail12"),
]

print(f"{'配置':<25} {'年化':<10} {'夏普':<8} {'回撤':<10} {'胜率':<8} {'n_sells':<8} {'avg_tp_pnl':<10}")
print("=" * 100)

for tp, trail, label in configs:
    r = run_backtest(
        "2024-03-11", "2026-07-01", 100000, 3, 1,
        use_tp=True, use_trail=True, use_time_tp=True,
        use_dynamic=False, use_scorer=False,
        tp_pct=tp, trail_pct=trail, hold_days=60,
    )
    if r:
        res = r["result"]
        # 找 take_profit 的平均收益
        tp_pnl = 0
        tp_n = 0
        for s in r["trades"]["sells"]:
            if s.get("reason") == "take_profit":
                tp_pnl += s.get("pnl_pct", 0)
                tp_n += 1
        avg_tp = tp_pnl / tp_n if tp_n else 0
        print(f"{label:<25} {res['annualized']:>+8.2f}%  {res['sharpe']:>6.2f}  {res['max_drawdown']:>+8.2f}%  {res['win_rate']:>5.1f}%  {res['n_sells']:>5}     {avg_tp:>+7.2f}%")
        results.append({"label": label, "tp": tp, "trail": trail, **res, "avg_tp_pnl": round(avg_tp, 2)})

# 找最优 (按夏普)
best_sharpe = max(results, key=lambda x: x["sharpe"])
best_ann = max(results, key=lambda x: x["annualized"])
print(f"\n🏆 最优年化: {best_ann['label']}  ({best_ann['annualized']:+.2f}%)")
print(f"🏆 最优夏普: {best_sharpe['label']}  ({best_sharpe['sharpe']:.2f})")

# 落盘
ts = datetime.now().strftime("%Y%m%d_%H%M%S")
out = rf"C:\项目\A基金\基金\reports\grid_tp_{ts}.json"
with open(out, "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)
print(f"\n💾 {out}")
