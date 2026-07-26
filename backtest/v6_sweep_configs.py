#!/usr/bin/env python3
"""
V6 策略配置生成器 — 基金级逆向买入 + 参数组合优化

V5发现：
- 冠军contrarian0.03+kc0.40: 99.8%收益, 但仅19笔交易(3年!)
- 根因: contrarian_buy_drop检查沪深300单日跌幅, 3年只有约15-20天跌超3%
- V6新增fund_drop_buy: 检查每只候选基金自身N日跌幅, 大幅增加交易机会

V6策略：
1. fund_drop_buy 网格测试（跌幅×天数×kelly）
2. fund_drop_buy + equal_alloc 组合
3. fund_drop_buy + max_sector_count 组合
4. 基线参照 + V5冠军复现
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
# 第1组: fund_drop_buy 跌幅阈值×回看天数 网格 (24)
# 测试不同跌幅阈值和回看天数, 找最佳组合
# ═══════════════════════════════════════════════════════════
for drop in [0.02, 0.03, 0.05, 0.08]:
    for days in [3, 5, 10, 20, 30]:
        add(f"V6_A_drop{drop}_d{days}", {
            "fund_drop_buy": drop,
            "fund_drop_days": days,
            "kelly_cap": 0.40,  # V5冠军的kelly
        })
# 补充极端值
for drop in [0.01, 0.10, 0.15]:
    for days in [5, 10]:
        add(f"V6_A_drop{drop}_d{days}", {
            "fund_drop_buy": drop,
            "fund_drop_days": days,
            "kelly_cap": 0.40,
        })

# ═══════════════════════════════════════════════════════════
# 第2组: fund_drop_buy × kelly_cap 精细网格 (16)
# 固定days=5, 测试不同drop×kelly
# ═══════════════════════════════════════════════════════════
for drop in [0.02, 0.03, 0.05, 0.08]:
    for kc in [0.35, 0.45, 0.50, 0.60]:
        add(f"V6_B_drop{drop}_d5_kc{kc}", {
            "fund_drop_buy": drop,
            "fund_drop_days": 5,
            "kelly_cap": kc,
        })

# ═══════════════════════════════════════════════════════════
# 第3组: fund_drop_buy + equal_alloc (8)
# 逆向选基 + 等权分配 = 降低集中风险
# ═══════════════════════════════════════════════════════════
for drop in [0.02, 0.03, 0.05, 0.08]:
    for days in [5, 10]:
        add(f"V6_C_drop{drop}_d{days}_equal", {
            "fund_drop_buy": drop,
            "fund_drop_days": days,
            "kelly_cap": 0.40,
            "equal_allocate": True,
        })

# ═══════════════════════════════════════════════════════════
# 第4组: fund_drop_buy + max_sector_count (6)
# 逆向选基 + 板块分散
# ═══════════════════════════════════════════════════════════
for drop in [0.03, 0.05, 0.08]:
    for msc in [2, 3]:
        add(f"V6_D_drop{drop}_d5_sec{msc}", {
            "fund_drop_buy": drop,
            "fund_drop_days": 5,
            "kelly_cap": 0.40,
            "max_sector_count": msc,
        })

# ═══════════════════════════════════════════════════════════
# 第5组: fund_drop_buy + RSI买入 (双重过滤) (6)
# 基金跌幅 + RSI超卖 = 更强逆向信号
# ═══════════════════════════════════════════════════════════
for drop in [0.03, 0.05, 0.08]:
    for rsi in [40, 50]:
        add(f"V6_E_drop{drop}_d5_rsi{rsi}", {
            "fund_drop_buy": drop,
            "fund_drop_days": 5,
            "kelly_cap": 0.40,
            "rsi_buy_max": rsi,
        })

# ═══════════════════════════════════════════════════════════
# 第6组: fund_drop_buy + smart_swap变体 (6)
# ═══════════════════════════════════════════════════════════
for drop in [0.03, 0.05]:
    add(f"V6_F_drop{drop}_d5_swap2_h60", {
        "fund_drop_buy": drop, "fund_drop_days": 5, "kelly_cap": 0.40,
        "smart_swap_margin": 2.0, "smart_swap_min_hold_days": 60,
    })
    add(f"V6_F_drop{drop}_d5_swap05_h15", {
        "fund_drop_buy": drop, "fund_drop_days": 5, "kelly_cap": 0.40,
        "smart_swap_margin": 0.5, "smart_swap_min_hold_days": 15,
    })
    add(f"V6_F_drop{drop}_d5_noswap", {
        "fund_drop_buy": drop, "fund_drop_days": 5, "kelly_cap": 0.40,
        "smart_swap": False,
    })

# ═══════════════════════════════════════════════════════════
# 第7组: 三参数组合 — 甜蜜点搜索 (10)
# ═══════════════════════════════════════════════════════════
# drop + kelly + equal
for drop in [0.03, 0.05, 0.08]:
    for kc in [0.45, 0.50]:
        add(f"V6_G_drop{drop}_d5_kc{kc}_equal", {
            "fund_drop_buy": drop, "fund_drop_days": 5, "kelly_cap": kc,
            "equal_allocate": True,
        })
# drop + kelly + sector
for drop in [0.05, 0.08]:
    for kc in [0.45, 0.50]:
        add(f"V6_H_drop{drop}_d5_kc{kc}_sec3", {
            "fund_drop_buy": drop, "fund_drop_days": 5, "kelly_cap": kc,
            "max_sector_count": 3,
        })

# ═══════════════════════════════════════════════════════════
# 第8组: 旧contrarian + 新fund_drop 双重过滤 (4)
# 市场大跌 + 基金大跌 = 极端抄底
# ═══════════════════════════════════════════════════════════
for fdrop in [0.03, 0.05]:
    add(f"V6_I_contra0.02_fdrop{fdrop}", {
        "contrarian_buy_drop": 0.02, "fund_drop_buy": fdrop,
        "fund_drop_days": 5, "kelly_cap": 0.40,
        "equal_allocate": True,
    })
    add(f"V6_I_contra0.03_fdrop{fdrop}", {
        "contrarian_buy_drop": 0.03, "fund_drop_buy": fdrop,
        "fund_drop_days": 5, "kelly_cap": 0.40,
    })

# ═══════════════════════════════════════════════════════════
# 第0组: 基线参照 (5)
# ═══════════════════════════════════════════════════════════
add("V6_Z0_baseline", {})  # 基线
add("V6_Z1_v5_champ", {"contrarian_buy_drop": 0.03, "kelly_cap": 0.40})  # V5冠军
add("V6_Z2_v4_champ", {"contrarian_buy_drop": 0.03})  # V4冠军
add("V6_Z3_equal", {"equal_allocate": True})  # V4最佳风险
add("V6_Z4_baseline_kc040", {"kelly_cap": 0.40})  # 基线+高仓位

# ═══════════════════════════════════════════════════════════
# 输出
# ═══════════════════════════════════════════════════════════
print(f"V6 策略总数: {len(STRATEGIES)}")

# 去重检查
names = [s["name"] for s in STRATEGIES]
dups = set([n for n in names if names.count(n) > 1])
if dups:
    print(f"WARNING: 重复策略名: {dups}")
    # 去重
    seen = set()
    unique = []
    for s in STRATEGIES:
        if s["name"] not in seen:
            seen.add(s["name"])
            unique.append(s)
    STRATEGIES = unique
    print(f"去重后: {len(STRATEGIES)}")
else:
    print("无重复策略名")

# 保存
out_path = Path(__file__).parent / "v6_sweep_configs.json"
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(STRATEGIES, f, ensure_ascii=False, indent=2)
print(f"已保存到: {out_path}")

# 参数覆盖统计
param_counts = {}
for s in STRATEGIES:
    for k in s["config"]:
        if k not in ("start_date", "end_date", "initial_cash", "monthly_injection", "weights"):
            param_counts[k] = param_counts.get(k, 0) + 1
print(f"\n变体参数覆盖:")
for k, v in sorted(param_counts.items(), key=lambda x: -x[1]):
    if v < len(STRATEGIES):  # 只显示非全量的
        print(f"  {k}: {v}次")
