#!/usr/bin/env python3
"""7月实盘模拟: 用冠军配置完整跑 2026-07-01 ~ 2026-07-22。

不简化任何参数，与回测完全一致的配置。
"""
import json, sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))
sys.path.insert(0, str(PROJECT / "backtest"))

from backtest.engine.backtest import run_backtest

# 加载冠军配置（完整，不简化）
cfg = json.loads((PROJECT / "data" / "evolution" / "best_config.json").read_text("utf-8"))
config = cfg["config"]

# 只改日期，其余参数完全不动
config["start_date"] = "2026-07-01"
config["end_date"] = "2026-07-22"
config["initial_cash"] = 10000

print(f"=== 7月实盘模拟: E_rnd0077 冠军策略 (完整配置) ===")
print(f"期间: 2026-07-01 ~ 2026-07-22")
print(f"初始资金: 10,000")
print()

result = run_backtest(config)

print(f"\n{'='*50}")
print(f"7月模拟结果:")
print(f"{'='*50}")
print(f"总收益: {result['total_return']:+.2f}%")
print(f"最大回撤: {result['max_drawdown']:.2f}%")
print(f"交易次数: {result['trade_count']}")
print(f"最终持仓: {result['final_holdings']} 只")
print(f"基准(沪深300): {result.get('benchmark_return', 0):+.2f}%")
print(f"超额收益: {result['total_return'] - result.get('benchmark_return', 0):+.2f}%")
print(f"总费用: {result.get('total_fees', 0):.2f}")
