#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成大规模参数扫描测试配置"""
import json

# 基线配置（当前最优）
BASELINE = {
    "kelly_cap": 0.35,
    "momentum_sell": 1.5,
    "take_profit_pct": 100,
    "stop_loss_pct": -30,
    "max_position_pct": 40,
    "cash_reserve_pct": 0.05,
    "min_consensus": 2,
    "max_holdings": 0,
    "max_correlation": 0.6,
    "max_sector_pct": 40,
    "cooldown_profit_days": 10,
    "cooldown_loss_days": 30,
    "profit_mode": "step",
}

# 参数扫描范围
SWEEPS = {
    "kelly_cap": [0.10, 0.15, 0.20, 0.25, 0.30, 0.40, 0.45, 0.50],
    "momentum_sell": [0.5, 1.0, 2.0, 2.5, 3.0],
    "take_profit_pct": [30, 50, 70, 80, 90, 120, 150],
    "stop_loss_pct": [-10, -15, -20, -25, -35, -40, -50],
    "max_position_pct": [10, 15, 20, 25, 30, 35, 45, 50],
    "cash_reserve_pct": [0, 0.02, 0.03, 0.08, 0.10, 0.15, 0.20],
    "min_consensus": [1, 3, 4, 5],
    "max_holdings": [3, 5, 8, 10, 12, 15, 20],
    "max_correlation": [0.3, 0.4, 0.5, 0.7, 0.8, 0.9, 1.0],
    "max_sector_pct": [20, 25, 30, 35, 50, 60, 100],
    "cooldown_profit_days": [0, 5, 15, 20, 30],
    "cooldown_loss_days": [0, 10, 20, 45, 60],
}

# profit_mode 变体
PROFIT_MODES = ["all", "half", "quarter"]

# trailing_tp 组合
TRAILING_COMBOS = [
    (20, 5), (20, 8), (20, 12),
    (10, 5), (10, 8),
    (15, 8), (15, 5),
    (25, 10), (30, 8),
]

# RSI 阈值
RSI_THRESHOLDS = [65, 70, 75, 85]

# 有趣的组合
COMBOS = [
    {"kelly_cap": 0.40, "momentum_sell": 1.0},
    {"kelly_cap": 0.40, "momentum_sell": 2.0},
    {"kelly_cap": 0.30, "take_profit_pct": 80},
    {"kelly_cap": 0.45, "max_position_pct": 50},
    {"momentum_sell": 1.0, "stop_loss_pct": -15},
    {"momentum_sell": 2.0, "take_profit_pct": 150},
    {"momentum_sell": 1.0, "kelly_cap": 0.45},
    {"momentum_sell": 2.0, "kelly_cap": 0.30},
    {"max_position_pct": 50, "kelly_cap": 0.45},
    {"max_position_pct": 30, "kelly_cap": 0.30},
    {"cash_reserve_pct": 0.10, "max_position_pct": 30},
    {"cash_reserve_pct": 0.02, "kelly_cap": 0.40},
    {"take_profit_pct": 80, "profit_mode": "half"},
    {"take_profit_pct": 150, "momentum_sell": 2.0},
    {"stop_loss_pct": -15, "momentum_sell": 1.0},
    {"stop_loss_pct": -20, "max_position_pct": 50},
    {"max_holdings": 5, "kelly_cap": 0.45},
    {"max_holdings": 10, "max_position_pct": 30},
    {"max_correlation": 0.4, "max_holdings": 10},
    {"max_sector_pct": 30, "max_holdings": 10},
]

configs = {}
labels = {}

# 1. 单参数扫描
for param, values in SWEEPS.items():
    for v in values:
        name = f"PS_{param}_{str(v).replace('.','p').replace('-','m')}"
        configs[name] = {param: v}
        baseline_v = BASELINE.get(param, "")
        labels[name] = f"PS:{param}={v} (base={baseline_v})"

# 2. profit_mode 变体
for mode in PROFIT_MODES:
    name = f"PS_profit_mode_{mode}"
    configs[name] = {"profit_mode": mode}
    labels[name] = f"PS:profit_mode={mode} (base=step)"

# 3. trailing_tp 组合
for act, dd in TRAILING_COMBOS:
    name = f"PS_trail_act{act}_dd{dd}"
    configs[name] = {"trailing_tp_activate": act, "trailing_tp_drawdown": dd}
    labels[name] = f"PS:trail act={act}% dd={dd}%"

# 4. RSI 阈值
for rsi in RSI_THRESHOLDS:
    name = f"PS_rsi_block_{rsi}"
    configs[name] = {"block_overbought": True, "rsi_block_threshold": rsi}
    labels[name] = f"PS:RSI block>{rsi}"

# 5. 组合策略
for i, combo in enumerate(COMBOS):
    parts = "_".join(f"{k}{str(v).replace('.','p').replace('-','m')}" for k, v in combo.items())
    name = f"PC_{parts}"
    configs[name] = combo
    labels[name] = f"PC:" + ", ".join(f"{k}={v}" for k, v in combo.items())

# 输出
print(f"Total configs: {len(configs)}")

# 生成Python代码片段
with open("backtest/sweep_configs.py", "w", encoding="utf-8") as f:
    f.write("# Auto-generated parameter sweep configs\n")
    f.write(f"# Total: {len(configs)} tests\n\n")
    
    f.write("SWEEP_CONFIGS = ")
    f.write(json.dumps(configs, ensure_ascii=False, indent=4))
    f.write("\n\n")
    
    f.write("SWEEP_LABELS = ")
    f.write(json.dumps(labels, ensure_ascii=False, indent=4))
    f.write("\n")

print(f"Written to backtest/sweep_configs.py")
print(f"\nBreakdown:")
print(f"  Single param sweeps: {sum(len(v) for v in SWEEPS.values())}")
print(f"  profit_mode variants: {len(PROFIT_MODES)}")
print(f"  trailing_tp combos: {len(TRAILING_COMBOS)}")
print(f"  RSI thresholds: {len(RSI_THRESHOLDS)}")
print(f"  Combination strategies: {len(COMBOS)}")
print(f"  Total: {len(configs)}")
