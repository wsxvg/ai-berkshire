"""聚焦策略扫描配置生成器

设计原则:
1. 基于J买入持有冠军策略(+41.85%)和已知失败策略(Y5过拟合)
2. 只调核心参数，不堆砌复杂逻辑
3. 每个维度独立扫描+少量组合，避免维度灾难
4. 总量~250个策略（不是2187个），7-8小时20路并行可完成
5. 防过拟合：滚动窗口验证+严格通过标准
"""
import json
from copy import deepcopy

# J买入持有冠军的基础配置（已知最优基线）
J_BASE = {
    "min_score": 3.3, "no_stop_loss": True, "take_profit_pct": 1000,
    "profit_mode": "half", "cost_penalty": 0, "min_consensus": 2,
    "fund_type_filter": "all", "momentum_sell": 0,
}

# 无脑跟投基础（min_score=0，纯信号驱动）
K_BASE = {
    "min_score": 0.0, "stop_loss_pct": -30, "take_profit_pct": 50,
    "profit_mode": "half", "cost_penalty": 0, "min_consensus": 2,
    "fund_type_filter": "all",
}

configs = []

# ═══ A: 买入持有变体（J冠军为基础）═══
# 核心发现：买了不卖是最优策略。测试不同共识门槛和基金类型
for mc in [1, 2, 3, 4, 5]:
    for ft in ["all", "active", "passive"]:
        for ms in [0.0, 3.3]:
            name = f"A_mc{mc}_{ft}_ms{ms}"
            cfg = deepcopy(J_BASE)
            cfg["min_consensus"] = mc
            cfg["fund_type_filter"] = ft
            cfg["min_score"] = ms
            configs.append({"name": name, "desc": f"买入持有 mc={mc} ft={ft} ms={ms}", "config": cfg})

# ═══ B: 止损变体（测试不同止损幅度）═══
for sl in [-5, -8, -10, -15, -20, -30, -50]:
    name = f"B_sl{sl}"
    cfg = deepcopy(J_BASE)
    cfg["no_stop_loss"] = False
    cfg["stop_loss_pct"] = sl
    cfg["take_profit_pct"] = 1000  # 仍然不主动止盈
    configs.append({"name": name, "desc": f"止损{sl}% 买入持有", "config": cfg})

# ═══ C: 止盈变体（测试不同止盈幅度）═══
for tp in [15, 20, 30, 40, 50, 80, 120]:
    name = f"C_tp{tp}"
    cfg = deepcopy(J_BASE)
    cfg["no_stop_loss"] = True
    cfg["take_profit_pct"] = tp
    configs.append({"name": name, "desc": f"止盈{tp}% 无止损", "config": cfg})

# ═══ D: 共识门槛+止损组合 ═══
for mc in [2, 3, 4]:
    for sl in [-10, -20, -30]:
        for tp in [30, 50, 1000]:
            name = f"D_mc{mc}_sl{sl}_tp{tp}"
            cfg = deepcopy(J_BASE)
            cfg["min_consensus"] = mc
            cfg["no_stop_loss"] = False
            cfg["stop_loss_pct"] = sl
            cfg["take_profit_pct"] = tp
            configs.append({"name": name, "desc": f"mc={mc} sl={sl} tp={tp}", "config": cfg})

# ═══ E: 仓位管理变体 ═══
for mh in [0, 3, 5, 8, 10, 15]:
    for kc in [0, 0.15, 0.25, 0.35]:
        name = f"E_mh{mh}_kc{kc}"
        cfg = deepcopy(J_BASE)
        cfg["max_holdings"] = mh
        cfg["kelly_cap"] = kc
        configs.append({"name": name, "desc": f"限仓{mh} kelly={kc}", "config": cfg})

# ═══ F: 聪明钱信号变体（加权共识/净信号）═══
for wc in [True, False]:
    for ns in [True, False]:
        for sc in [0, 2, 3]:
            for ac in [True, False]:
                name = f"F_wc{int(wc)}_ns{int(ns)}_sc{sc}_ac{int(ac)}"
                cfg = deepcopy(K_BASE)
                cfg["use_weighted_consensus"] = wc
                cfg["net_signal"] = ns
                cfg["sell_consensus"] = sc
                cfg["adaptive_consensus"] = ac
                cfg["no_stop_loss"] = True
                cfg["take_profit_pct"] = 1000
                configs.append({"name": name, "desc": f"加权{wc} 净信号{ns} 卖共识{sc} 自适应{ac}", "config": cfg})

# ═══ G: profit_mode变体 ═══
for pm in ["half", "quarter", "step", "all"]:
    for ms in [0.0, 3.3]:
        name = f"G_{pm}_ms{ms}"
        cfg = deepcopy(J_BASE)
        cfg["profit_mode"] = pm
        cfg["min_score"] = ms
        configs.append({"name": name, "desc": f"profit_mode={pm} ms={ms}", "config": cfg})

# ═══ H: 动量卖出变体 ═══
for msell in [0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0]:
    name = f"H_msell{msell}"
    cfg = deepcopy(J_BASE)
    cfg["momentum_sell"] = msell
    configs.append({"name": name, "desc": f"动量卖出={msell}", "config": cfg})

# ═══ I: 滑点+费率模拟（更真实）═══
for slip in [0.0, 0.3, 0.5, 1.0]:
    for cp in [0, 0.5, 1.0]:
        name = f"I_slip{slip}_cp{cp}"
        cfg = deepcopy(J_BASE)
        cfg["slippage_pct"] = slip
        cfg["cost_penalty"] = cp
        configs.append({"name": name, "desc": f"滑点{slip}% 费率惩罚{cp}", "config": cfg})

# ═══ J: 冷却期变体（防止频繁买卖）═══
for cpd in [0, 5, 10, 20]:
    for cld in [0, 15, 30]:
        name = f"J_cpd{cpd}_cld{cld}"
        cfg = deepcopy(J_BASE)
        cfg["cooldown_profit_days"] = cpd
        cfg["cooldown_loss_days"] = cld
        configs.append({"name": name, "desc": f"止盈冷却{cpd}d 止损冷却{cld}d", "config": cfg})

# ═══ K: 综合最优组合（从上面各维度选最佳组合）═══
# 基于之前经验：低min_score + 买入持有 + 适度限仓
combos = [
    {"min_score": 0.0, "min_consensus": 2, "no_stop_loss": True, "take_profit_pct": 1000,
     "max_holdings": 5, "kelly_cap": 0.25, "fund_type_filter": "all"},
    {"min_score": 0.0, "min_consensus": 3, "no_stop_loss": True, "take_profit_pct": 1000,
     "max_holdings": 8, "kelly_cap": 0.30, "fund_type_filter": "all"},
    {"min_score": 0.0, "min_consensus": 2, "no_stop_loss": True, "take_profit_pct": 1000,
     "max_holdings": 0, "kelly_cap": 0, "fund_type_filter": "active"},
    {"min_score": 0.0, "min_consensus": 2, "no_stop_loss": True, "take_profit_pct": 1000,
     "max_holdings": 10, "kelly_cap": 0.35, "fund_type_filter": "all",
     "momentum_sell": 1.0},
    {"min_score": 0.0, "min_consensus": 2, "stop_loss_pct": -30, "take_profit_pct": 1000,
     "max_holdings": 5, "kelly_cap": 0.25, "fund_type_filter": "all"},
    {"min_score": 0.0, "min_consensus": 2, "no_stop_loss": True, "take_profit_pct": 50,
     "max_holdings": 5, "kelly_cap": 0.25, "fund_type_filter": "all",
     "profit_mode": "step"},
    {"min_score": 0.0, "min_consensus": 2, "no_stop_loss": True, "take_profit_pct": 1000,
     "max_holdings": 5, "kelly_cap": 0.25, "fund_type_filter": "all",
     "use_weighted_consensus": True, "adaptive_consensus": True},
    {"min_score": 0.0, "min_consensus": 2, "no_stop_loss": True, "take_profit_pct": 1000,
     "max_holdings": 5, "kelly_cap": 0.25, "fund_type_filter": "all",
     "net_signal": True, "sell_consensus": 2},
    {"min_score": 0.0, "min_consensus": 2, "no_stop_loss": True, "take_profit_pct": 1000,
     "max_holdings": 3, "kelly_cap": 0.30, "fund_type_filter": "all",
     "cooldown_profit_days": 10, "cooldown_loss_days": 30},
    {"min_score": 0.0, "min_consensus": 2, "no_stop_loss": True, "take_profit_pct": 1000,
     "max_holdings": 0, "kelly_cap": 0, "fund_type_filter": "all",
     "slippage_pct": 0.5, "cost_penalty": 0.5},
]
for i, cfg in enumerate(combos):
    name = f"K_combo{i+1}"
    configs.append({"name": name, "desc": f"综合最优组合{i+1}", "config": cfg})

# ═══ L: 散户定投变体（月投2000-5000）═══
for mi in [1000, 2000, 3000, 5000]:
    for mh in [3, 5, 8]:
        name = f"L_mi{mi}_mh{mh}"
        cfg = deepcopy(J_BASE)
        cfg["min_score"] = 0.0
        cfg["monthly_injection"] = mi
        cfg["max_holdings"] = mh
        cfg["kelly_cap"] = 0.25
        configs.append({"name": name, "desc": f"月投{mi} 限仓{mh}", "config": cfg})

# 去重
seen = set()
unique_configs = []
for c in configs:
    key = json.dumps(c["config"], sort_keys=True)
    if key not in seen:
        seen.add(key)
        unique_configs.append(c)

print(f"总策略数: {len(unique_configs)} (去重前: {len(configs)})")

# 保存
with open("backtest/focused_sweep_configs.json", "w", encoding="utf-8") as f:
    json.dump(unique_configs, f, ensure_ascii=False, indent=2)
print(f"已保存到 backtest/focused_sweep_configs.json")

# 打印分类统计
categories = {}
for c in unique_configs:
    cat = c["name"][0]
    categories[cat] = categories.get(cat, 0) + 1
print("\n分类统计:")
for cat in sorted(categories.keys()):
    print(f"  {cat}: {categories[cat]}个")
