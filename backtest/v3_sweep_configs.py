#!/usr/bin/env python3
"""
V3策略扫描配置生成器（大幅扩充版）：在bug修复后的冠军策略基础上，
细粒度测试止盈/止损/移动止盈/kelly_cap及其组合。

止盈: 5/8/10/12/15/18/20/25/30/40/50/60/80/100 % × half/all/quarter
止损: -5/-8/-10/-12/-15/-18/-20/-25/-30 %
移动止盈: activate=3/5/8/10/12/15/20/25/30 × drawdown=3/5/8/10/12/15
组合: TP×SL, TP×Trail, SL×Trail, TP×SL×Trail, KC×TP, KC×SL
"""
import json, copy
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

# === A组：基线（bug修复后冠军策略，不止盈不止损） ===
add("V3_A0_baseline", {})

# ── 细粒度参数表 ──
TP_LEVELS   = [5, 8, 10, 12, 15, 18, 20, 25, 30, 40, 50, 60, 80, 100]
SL_LEVELS   = [-5, -8, -10, -12, -15, -18, -20, -25, -30]
TRAIL_ACT   = [3, 5, 8, 10, 12, 15, 20, 25, 30]
TRAIL_DD    = [3, 5, 8, 10, 12, 15]
KC_LEVELS   = [0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50]
PROFIT_MODES = ["half", "all", "quarter"]

# === B组：止盈单参数扫描（42个） ===
for tp in TP_LEVELS:
    for pm in PROFIT_MODES:
        add(f"V3_B_tp{tp}_{pm}", {"take_profit_pct": tp, "profit_mode": pm})

# === C组：移动止盈单参数扫描 ===
for act in TRAIL_ACT:
    for dd in TRAIL_DD:
        if dd < act:  # 回撤阈值必须小于激活阈值
            add(f"V3_C_trail{act}_{dd}", {
                "trailing_tp_activate": act, "trailing_tp_drawdown": dd,
                "take_profit_pct": 1000,  # 不触发固定止盈，纯移动止盈
            })

# === D组：止损单参数扫描（9个） ===
for sl in SL_LEVELS:
    add(f"V3_E_sl{abs(sl)}", {"no_stop_loss": False, "stop_loss_pct": sl})

# === F组：止盈+止损组合（精选组合，避免爆炸） ===
TP_FOR_COMBO = [5, 8, 10, 12, 15, 18, 20, 25, 30, 40, 50]
SL_FOR_COMBO = [-5, -8, -10, -12, -15, -20, -25, -30]
for sl in SL_FOR_COMBO:
    for tp in TP_FOR_COMBO:
        add(f"V3_F_sl{abs(sl)}_tp{tp}", {
            "no_stop_loss": False, "stop_loss_pct": sl,
            "take_profit_pct": tp, "profit_mode": "half",
        })

# === G组：动态止损 ===
for sl in [-10, -15, -20, -25]:
    add(f"V3_G_dynsl{abs(sl)}", {
        "no_stop_loss": False, "dynamic_stop_loss": True, "stop_loss_pct": sl,
    })

# === H组：kelly_cap单参数扫描 ===
for kc in KC_LEVELS:
    add(f"V3_H_kc{kc}", {"kelly_cap": kc})

# === I组：kelly_cap+止盈组合 ===
KC_FOR_COMBO = [0.15, 0.20, 0.25, 0.30, 0.40]
TP_FOR_KC    = [8, 10, 12, 15, 20, 25, 30]
for kc in KC_FOR_COMBO:
    for tp in TP_FOR_KC:
        add(f"V3_I_kc{kc}_tp{tp}", {
            "kelly_cap": kc, "take_profit_pct": tp, "profit_mode": "half",
        })

# === J组：阶梯止盈（多种阶梯方案） ===
step_configs = [
    [[5, 0.3], [10, 0.3], [20, 0.4]],
    [[8, 0.3], [15, 0.3], [25, 0.4]],
    [[10, 0.3], [20, 0.3], [30, 0.4]],
    [[10, 0.5], [20, 0.3], [30, 0.2]],
    [[15, 0.3], [30, 0.3], [50, 0.4]],
    [[15, 0.5], [30, 0.3], [50, 0.2]],
    [[20, 0.3], [40, 0.3], [60, 0.4]],
    [[5, 0.2], [10, 0.2], [15, 0.2], [20, 0.2], [30, 0.2]],
    [[10, 0.25], [20, 0.25], [30, 0.25], [50, 0.25]],
]
for i, levels in enumerate(step_configs):
    add(f"V3_J_step_v{i+1}", {
        "step_take_profit": True,
        "step_tp_levels": levels,
        "take_profit_pct": 1000,
    })

# === K组：止盈+移动止盈组合 ===
TP_FOR_K = [8, 10, 12, 15, 20]
TRAIL_FOR_K = [(5, 3), (5, 5), (8, 5), (8, 8), (10, 5), (10, 8), (12, 8), (15, 10)]
for tp in TP_FOR_K:
    for act, dd in TRAIL_FOR_K:
        if dd < tp:  # 移动止盈回撤 < 固定止盈阈值，否则先触发固定止盈
            add(f"V3_K_tp{tp}_trail{act}_{dd}", {
                "take_profit_pct": tp, "profit_mode": "half",
                "trailing_tp_activate": act, "trailing_tp_drawdown": dd,
            })

# === L组：止损+移动止盈组合 ===
SL_FOR_L = [-8, -10, -15, -20]
for sl in SL_FOR_L:
    for act, dd in TRAIL_FOR_K:
        add(f"V3_L_sl{abs(sl)}_trail{act}_{dd}", {
            "no_stop_loss": False, "stop_loss_pct": sl,
            "trailing_tp_activate": act, "trailing_tp_drawdown": dd,
            "take_profit_pct": 1000,
        })

# === M组：止损+止盈+移动止盈三合一 ===
SL_FOR_M = [-8, -10, -15, -20]
TP_FOR_M = [10, 12, 15, 20]
TRAIL_FOR_M = [(5, 5), (8, 5), (10, 8)]
for sl in SL_FOR_M:
    for tp in TP_FOR_M:
        for act, dd in TRAIL_FOR_M:
            if dd < tp:
                add(f"V3_M_sl{abs(sl)}_tp{tp}_trail{act}_{dd}", {
                    "no_stop_loss": False, "stop_loss_pct": sl,
                    "take_profit_pct": tp, "profit_mode": "half",
                    "trailing_tp_activate": act, "trailing_tp_drawdown": dd,
                })

# === N组：止损+止盈+kelly_cap三合一 ===
SL_FOR_N = [-8, -10, -15]
TP_FOR_N = [8, 10, 12, 15, 20]
KC_FOR_N = [0.20, 0.25, 0.30]
for sl in SL_FOR_N:
    for tp in TP_FOR_N:
        for kc in KC_FOR_N:
            add(f"V3_N_sl{abs(sl)}_tp{tp}_kc{kc}", {
                "no_stop_loss": False, "stop_loss_pct": sl,
                "take_profit_pct": tp, "profit_mode": "half",
                "kelly_cap": kc,
            })

# === O组：peak_drawdown_exit（从高点回撤X%卖出） ===
for pdd in [5, 8, 10, 12, 15, 20, 25, 30]:
    add(f"V3_O_peakdd{pdd}", {
        "peak_drawdown_exit": pdd,
        "take_profit_pct": 1000,
    })

# === P组：peak_drawdown_reduce（回撤减半） ===
for pdr in [5, 8, 10, 12, 15, 20]:
    add(f"V3_P_peakdr{pdr}", {
        "peak_drawdown_reduce": pdr,
        "take_profit_pct": 1000,
    })

# === Q组：trailing_stop_pct（移动止损线） ===
for ts in [5, 8, 10, 12, 15, 20, 25, 30]:
    add(f"V3_Q_trailstop{ts}", {
        "trailing_stop_pct": ts,
        "take_profit_pct": 1000,
    })

OUTPUT = Path(__file__).resolve().parent / "v3_sweep_configs.json"
with open(OUTPUT, "w", encoding="utf-8") as f:
    json.dump(STRATEGIES, f, ensure_ascii=False, indent=2)

print(f"Generated {len(STRATEGIES)} V3 sweep configs")
print(f"Output: {OUTPUT}")

groups = {}
for s in STRATEGIES:
    g = s["name"].split("_")[1]
    groups[g] = groups.get(g, 0) + 1
for g in sorted(groups):
    print(f"  {g}组: {groups[g]}个")
