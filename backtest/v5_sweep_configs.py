#!/usr/bin/env python3
"""
V5 精细优化策略配置生成器

V4发现：
- 冠军 contrarian0.03: 94.9%收益/13.7%DD/Sharpe6.92, 但仅26笔交易, 2个窗口空仓
- 最佳风险 equal_alloc: 60.5%收益/9.0%DD/Sharpe6.70, 但收益不够高
- 均衡 rsibuy40: 77.8%收益/18.1%DD/Sharpe4.30, 5窗口全正

V4的盲区：所有参数都是单变量测试, 没有测试最佳参数的组合！

V5策略：围绕冠军策略做精细网格 + 关键参数组合, 寻找"高收益+低回撤"甜蜜点。
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

# ═══════════════════════════════════════════════════════════
# 第1组: contrarian阈值×kelly_cap 精细网格 (20)
# 冠军用contrarian0.03+kc0.35, 测试更细的阈值和更高仓位
# ═══════════════════════════════════════════════════════════
for drop in [0.005, 0.01, 0.015, 0.025]:
    for kc in [0.35, 0.40, 0.45, 0.50]:
        add(f"V5_A_drop{drop}_kc{kc}", {"contrarian_buy_drop": drop, "kelly_cap": kc})
# 已有0.02和0.03, 补充它们的kelly变体
for drop in [0.02, 0.03]:
    for kc in [0.40, 0.45, 0.50]:
        add(f"V5_A_drop{drop}_kc{kc}", {"contrarian_buy_drop": drop, "kelly_cap": kc})
# 0.03+0.35是冠军, 不重复

# ═══════════════════════════════════════════════════════════
# 第2组: contrarian + equal_allocate 组合 (6)
# 冠军高收益但集中持仓, equal_alloc低DD, 组合可能两全
# ═══════════════════════════════════════════════════════════
for drop in [0.01, 0.015, 0.02, 0.025, 0.03]:
    add(f"V5_B_drop{drop}_equal", {"contrarian_buy_drop": drop, "equal_allocate": True})
# equal_alloc + kelly提升
add("V5_B_equal_kc0.45", {"equal_allocate": True, "kelly_cap": 0.45})
add("V5_B_equal_kc0.50", {"equal_allocate": True, "kelly_cap": 0.50})

# ═══════════════════════════════════════════════════════════
# 第3组: contrarian + max_sector_count 风控 (6)
# 冠军回撤13.7%, 加板块限制可能进一步降低
# ═══════════════════════════════════════════════════════════
for drop in [0.01, 0.02, 0.03]:
    for msc in [2, 3]:
        add(f"V5_C_drop{drop}_sec{msc}", {"contrarian_buy_drop": drop, "max_sector_count": msc})

# ═══════════════════════════════════════════════════════════
# 第4组: contrarian + smart_swap 变体 (6)
# 冠军用swap_margin=1.0/h30, 测试更激进换仓
# ═══════════════════════════════════════════════════════════
for drop in [0.01, 0.02, 0.03]:
    add(f"V5_D_drop{drop}_swap2_h60", {"contrarian_buy_drop": drop, "smart_swap_margin": 2.0, "smart_swap_min_hold_days": 60})
    add(f"V5_D_drop{drop}_swap0.5_h15", {"contrarian_buy_drop": drop, "smart_swap_margin": 0.5, "smart_swap_min_hold_days": 15})

# ═══════════════════════════════════════════════════════════
# 第5组: RSI买入 + kelly_cap 组合 (8)
# rsibuy40已有77.8%, 提升仓位可能更高
# ═══════════════════════════════════════════════════════════
for rsi in [35, 40, 45, 50]:
    for kc in [0.40, 0.50]:
        add(f"V5_E_rsi{rsi}_kc{kc}", {"rsi_buy_max": rsi, "kelly_cap": kc})

# ═══════════════════════════════════════════════════════════
# 第6组: RSI + equal_allocate 组合 (4)
# RSI选基 + 等权分配, 可能降低DD
# ═══════════════════════════════════════════════════════════
for rsi in [40, 45, 50]:
    add(f"V5_F_rsi{rsi}_equal", {"rsi_buy_max": rsi, "equal_allocate": True})
add("V5_F_rsi40_equal_kc0.5", {"rsi_buy_max": 40, "equal_allocate": True, "kelly_cap": 0.50})

# ═══════════════════════════════════════════════════════════
# 第7组: RSI + max_sector_count (4)
# ═══════════════════════════════════════════════════════════
for rsi in [40, 50]:
    for msc in [2, 3]:
        add(f"V5_G_rsi{rsi}_sec{msc}", {"rsi_buy_max": rsi, "max_sector_count": msc})

# ═══════════════════════════════════════════════════════════
# 第8组: RSI + contrarian 双重过滤 (4)
# RSI超卖 + 市场大跌, 极端逆向策略
# ═══════════════════════════════════════════════════════════
for rsi in [50, 60]:
    for drop in [0.005, 0.01]:
        add(f"V5_H_rsi{rsi}_drop{drop}", {"rsi_buy_max": rsi, "contrarian_buy_drop": drop})

# ═══════════════════════════════════════════════════════════
# 第9组: equal_alloc + 风控增强 (6)
# ═══════════════════════════════════════════════════════════
for msc in [2, 3]:
    add(f"V5_I_equal_sec{msc}", {"equal_allocate": True, "max_sector_count": msc})
add("V5_I_equal_corr0.8", {"equal_allocate": True, "max_correlation": 0.8})
add("V5_I_equal_rebal30", {"equal_allocate": True, "rebalance": True, "max_sector_pct": 30})
add("V5_I_equal_peakdd15", {"equal_allocate": True, "peak_drawdown_exit": 15})
add("V5_I_equal_trailstop15", {"equal_allocate": True, "trailing_stop_pct": 15})

# ═══════════════════════════════════════════════════════════
# 第10组: 三参数组合 — 最佳甜蜜点搜索 (15)
# ═══════════════════════════════════════════════════════════
# contrarian + kelly + equal_alloc
for drop in [0.015, 0.02, 0.03]:
    for kc in [0.45, 0.50]:
        add(f"V5_J_drop{drop}_kc{kc}_equal", {"contrarian_buy_drop": drop, "kelly_cap": kc, "equal_allocate": True})

# contrarian + kelly + sector
for drop in [0.02, 0.03]:
    for kc in [0.45, 0.50]:
        add(f"V5_K_drop{drop}_kc{kc}_sec3", {"contrarian_buy_drop": drop, "kelly_cap": kc, "max_sector_count": 3})

# rsi + kelly + equal_alloc
for rsi in [40, 45]:
    for kc in [0.45, 0.50]:
        add(f"V5_L_rsi{rsi}_kc{kc}_equal", {"rsi_buy_max": rsi, "kelly_cap": kc, "equal_allocate": True})

# equal_alloc + kelly + sector
add("V5_M_equal_kc0.5_sec3", {"equal_allocate": True, "kelly_cap": 0.50, "max_sector_count": 3})
add("V5_M_equal_kc0.45_sec2", {"equal_allocate": True, "kelly_cap": 0.45, "max_sector_count": 2})

# ═══════════════════════════════════════════════════════════
# 第11组: 冠军策略 + 风控增强 (8)
# 在冠军基础上加一个风控参数, 看能否降DD而不损收益
# ═══════════════════════════════════════════════════════════
add("V5_N_champ_rsisell70", {"contrarian_buy_drop": 0.03, "rsi_sell_threshold": 70})
add("V5_N_champ_peakdd15", {"contrarian_buy_drop": 0.03, "peak_drawdown_exit": 15})
add("V5_N_champ_trailstop15", {"contrarian_buy_drop": 0.03, "trailing_stop_pct": 15})
add("V5_N_champ_corr0.8", {"contrarian_buy_drop": 0.03, "max_correlation": 0.8})
add("V5_N_champ_sec3", {"contrarian_buy_drop": 0.03, "max_sector_count": 3})
add("V5_N_champ_rebal30", {"contrarian_buy_drop": 0.03, "rebalance": True, "max_sector_pct": 30})
add("V5_N_champ_ddbrk15", {"contrarian_buy_drop": 0.03, "portfolio_dd_breaker": 15, "portfolio_dd_pause_days": 5})
add("V5_N_champ_equal", {"contrarian_buy_drop": 0.03, "equal_allocate": True})

# ═══════════════════════════════════════════════════════════
# 第12组: 基线参照 (3)
# ═══════════════════════════════════════════════════════════
add("V5_Z0_baseline", {})  # V4冠军基线
add("V5_Z1_champion", {"contrarian_buy_drop": 0.03})  # 冠军复现
add("V5_Z2_equal_alloc", {"equal_allocate": True})  # 最佳风险复现

# ═══════════════════════════════════════════════════════════
# 输出
# ═══════════════════════════════════════════════════════════
print(f"V5 策略总数: {len(STRATEGIES)}")

# 去重检查
names = [s["name"] for s in STRATEGIES]
dups = [n for n in names if names.count(n) > 1]
if dups:
    print(f"WARNING: 重复策略名: {set(dups)}")
else:
    print("无重复策略名")

# 统计参数覆盖
param_counts = {}
for s in STRATEGIES:
    for k in s["config"]:
        if k not in ("start_date", "end_date", "initial_cash", "monthly_injection"):
            param_counts[k] = param_counts.get(k, 0) + 1

print(f"\n参数覆盖:")
for k, v in sorted(param_counts.items(), key=lambda x: -x[1]):
    if k not in ("weights",):
        print(f"  {k}: {v}次")

# 保存
out_path = Path(__file__).parent / "v5_sweep_configs.json"
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(STRATEGIES, f, ensure_ascii=False, indent=2)
print(f"\n已保存到: {out_path}")
