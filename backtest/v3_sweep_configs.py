#!/usr/bin/env python3
"""
V3策略扫描配置生成器：在bug修复后的冠军策略基础上，系统测试止盈/止损/kelly_cap调优。

基础策略: V2冠军 V2_E_mh0_kc0.35_swap_dynmh (bug修复后)
测试维度:
  A. 止盈: tp=10/15/20/30/50 × profit_mode=half/all
  B. 移动止盈: trailing_tp_activate=5/10/15/20 × drawdown=5/8/10
  C. 止盈+移动止盈组合
  D. 止损: sl=-10/-15/-20
  E. 止损+止盈组合
  F. 动态止损
  G. kelly_cap: 0.15/0.20/0.25/0.30/0.40/0.45
  H. kelly_cap+止盈组合
  I. 阶梯止盈
  J. 最优组合
"""
import json, copy, os
from pathlib import Path

BASE = {
    "start_date": "2023-07-17",
    "end_date": "2026-07-24",
    "initial_cash": 10000,
    "monthly_injection": 0,
    "weights": {"quality": 25, "cost": 20, "manager": 20, "momentum": 15, "smart_money": 20},
    "min_score": 3.3,
    "no_stop_loss": True,
    "take_profit_pct": 1000,
    "profit_mode": "half",
    "cost_penalty": 0,
    "min_consensus": 2,
    "fund_type_filter": "all",
    "momentum_sell": 0,
    "max_candidates_per_day": 0,
    "max_holdings": 8,
    "kelly_cap": 0.35,
    "smart_swap": True,
    "smart_swap_margin": 1.0,
    "smart_swap_min_hold_days": 30,
    "dynamic_max_holdings": True,
    "max_holdings_bull_mult": 1.5,
    "max_holdings_bear_mult": 0.6,
}

STRATEGIES = []

def add(name, config_overrides):
    cfg = copy.deepcopy(BASE)
    cfg.update(config_overrides)
    STRATEGIES.append({"name": name, "desc": "", "config": cfg})

# === A组：基线 ===
add("V3_A0_baseline", {})

# === B组：止盈参数 ===
for tp in [10, 15, 20, 30, 50]:
    add(f"V3_B_tp{tp}_half", {"take_profit_pct": tp, "profit_mode": "half"})
    add(f"V3_B_tp{tp}_all", {"take_profit_pct": tp, "profit_mode": "all"})

# === C组：移动止盈 ===
for act in [5, 10, 15, 20]:
    for dd in [5, 8, 10]:
        if dd < act:
            add(f"V3_C_trail{act}_{dd}", {"trailing_tp_activate": act, "trailing_tp_drawdown": dd})

# === D组：止盈+移动止盈组合 ===
for tp in [10, 15, 20]:
    for act, dd in [(5, 5), (10, 8)]:
        add(f"V3_D_tp{tp}_trail{act}_{dd}", {
            "take_profit_pct": tp, "profit_mode": "half",
            "trailing_tp_activate": act, "trailing_tp_drawdown": dd,
        })

# === E组：止损 ===
for sl in [-10, -15, -20]:
    add(f"V3_E_sl{abs(sl)}", {"no_stop_loss": False, "stop_loss_pct": sl})

# === F组：止损+止盈组合 ===
for sl in [-10, -15, -20]:
    for tp in [10, 15, 20]:
        add(f"V3_F_sl{abs(sl)}_tp{tp}", {
            "no_stop_loss": False, "stop_loss_pct": sl,
            "take_profit_pct": tp, "profit_mode": "half",
        })

# === G组：动态止损 ===
add("V3_G_dynsl15", {"no_stop_loss": False, "dynamic_stop_loss": True, "stop_loss_pct": -15})
add("V3_G_dynsl20", {"no_stop_loss": False, "dynamic_stop_loss": True, "stop_loss_pct": -20})

# === H组：kelly_cap调优 ===
for kc in [0.15, 0.20, 0.25, 0.30, 0.40, 0.45]:
    add(f"V3_H_kc{kc}", {"kelly_cap": kc})

# === I组：kelly_cap+止盈组合 ===
for kc in [0.20, 0.25, 0.30, 0.40]:
    for tp in [10, 15, 20]:
        add(f"V3_I_kc{kc}_tp{tp}", {
            "kelly_cap": kc, "take_profit_pct": tp, "profit_mode": "half",
        })

# === J组：阶梯止盈 ===
add("V3_J_step10_20_30", {
    "step_take_profit": True,
    "step_tp_levels": [[10, 0.3], [20, 0.3], [30, 0.4]],
    "take_profit_pct": 1000,
})
add("V3_J_step15_30_50", {
    "step_take_profit": True,
    "step_tp_levels": [[15, 0.3], [30, 0.3], [50, 0.4]],
    "take_profit_pct": 1000,
})

# === K组：止损+止盈+移动止盈三合一 ===
for sl in [-10, -15]:
    for tp in [10, 15]:
        add(f"V3_K_sl{abs(sl)}_tp{tp}_trail10_8", {
            "no_stop_loss": False, "stop_loss_pct": sl,
            "take_profit_pct": tp, "profit_mode": "half",
            "trailing_tp_activate": 10, "trailing_tp_drawdown": 8,
        })

# === L组：止损+kelly_cap+止盈三合一 ===
for sl in [-10, -15]:
    for kc in [0.25, 0.30]:
        for tp in [10, 15]:
            add(f"V3_L_sl{abs(sl)}_kc{kc}_tp{tp}", {
                "no_stop_loss": False, "stop_loss_pct": sl,
                "kelly_cap": kc, "take_profit_pct": tp, "profit_mode": "half",
            })

OUTPUT = Path(__file__).resolve().parent / "v3_sweep_configs.json"
with open(OUTPUT, "w", encoding="utf-8") as f:
    json.dump(STRATEGIES, f, ensure_ascii=False, indent=2)

print(f"Generated {len(STRATEGIES)} V3 sweep configs")
print(f"Output: {OUTPUT}")

# 统计各组数量
groups = {}
for s in STRATEGIES:
    g = s["name"].split("_")[1]
    groups[g] = groups.get(g, 0) + 1
for g in sorted(groups):
    print(f"  {g}组: {groups[g]}个")
