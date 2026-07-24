"""聚焦策略扫描配置生成器 v2 — 525个策略

设计原则:
1. 基于J买入持有冠军策略(+41.85%)和已知失败策略(Y5过拟合)
2. 覆盖引擎全部61个参数维度+评分权重
3. 每个维度独立扫描+组合，防止过拟合
4. 525个策略，20路并行，~3小时可完成
5. 防过拟合：Phase 2 滚动窗口验证+7项标准

策略分类:
  A-L:   174个 — 基线策略（v1已有）
  M:      12个 — 移动止盈（trailing_tp）
  N:      12个 — 金字塔补仓（pyramiding）
  O:      12个 — 市场环境自适应（regime_specific）
  P:      12个 — 组合级风控（dd_breaker + dd_reduce）
  Q:      12个 — 分散化（correlation + sector + qdii）
  R:      10个 — 动态止损（dynamic_stop + ATR）
  S:      24个 — 散户资金模拟（initial_cash × slippage × holdings）
  T:      20个 — 定投深入（monthly_injection × holdings × kelly）
  U:      12个 — 滑点压力测试（0-2%）
  V:      15个 — 保守防御（严止损+高滑点+限仓+冷却）
  W:      15个 — 激进增长（无止损+低限仓+无冷却）
  X:      25个 — 终极组合（手工打造最佳组合）
  Y:       8个 — 最低持有天数（30-120天）
  Z:       6个 — 年交易上限（30-100次）
  AA:     10个 — 大佬加权（player_weights + exclude）
  AB:      8个 — 排名窗口（ranking_window × half_life）
  AC:     10个 — 市场风险过滤（market_risk + predictor + LGB）
  AD:     15个 — 技术指标叠加（MACD + Bollinger + MA + KDJ + vol_spike）
  AE:     10个 — 阶梯止盈（step_tp_levels）
  AF:     10个 — 凯利分数（kelly_fraction × equal_allocate）
  AG:     10个 — 现金储备（cash_reserve × max_position）
  AH:      8个 — 动量信号源（signal_source=momentum）
  AI:      8个 — QDII+行业限制（max_qdii + max_sector）
  AJ:     20个 — 极端组合（all-in/ultra-safe/max-diversify）
  AK:     30个 — 多维网格（consensus × kelly × holdings 系统网格）
  AL:     12个 — 评分权重变体（quality/cost/manager/momentum/smart_money）
"""
import json
from copy import deepcopy

# J买入持有冠军的基础配置（已知最优基线）
J_BASE = {
    "min_score": 3.3, "no_stop_loss": True, "take_profit_pct": 1000,
    "profit_mode": "half", "cost_penalty": 0, "min_consensus": 2,
    "fund_type_filter": "all", "momentum_sell": 0,
    "max_candidates_per_day": 0,  # 不限制（有跨策略评分缓存）
}

# 无脑跟投基础（min_score=0，纯信号驱动）
K_BASE = {
    "min_score": 0.0, "stop_loss_pct": -30, "take_profit_pct": 50,
    "profit_mode": "half", "cost_penalty": 0, "min_consensus": 2,
    "fund_type_filter": "all",
    "max_candidates_per_day": 0,  # 不限制（有跨策略评分缓存）
}

configs = []

# ═══ A: 买入持有变体（J冠军为基础）═══
for mc in [1, 2, 3, 4, 5]:
    for ft in ["all", "active", "passive"]:
        for ms in [0.0, 3.3]:
            name = f"A_mc{mc}_{ft}_ms{ms}"
            cfg = deepcopy(J_BASE)
            cfg["min_consensus"] = mc
            cfg["fund_type_filter"] = ft
            cfg["min_score"] = ms
            configs.append({"name": name, "desc": f"买入持有 mc={mc} ft={ft} ms={ms}", "config": cfg})

# ═══ B: 止损变体 ═══
for sl in [-5, -8, -10, -15, -20, -30, -50]:
    name = f"B_sl{sl}"
    cfg = deepcopy(J_BASE)
    cfg["no_stop_loss"] = False
    cfg["stop_loss_pct"] = sl
    cfg["take_profit_pct"] = 1000
    configs.append({"name": name, "desc": f"止损{sl}% 买入持有", "config": cfg})

# ═══ C: 止盈变体 ═══
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

# ═══ F: 聪明钱信号变体 ═══
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

# ═══ I: 滑点+费率模拟 ═══
for slip in [0.0, 0.3, 0.5, 1.0]:
    for cp in [0, 0.5, 1.0]:
        name = f"I_slip{slip}_cp{cp}"
        cfg = deepcopy(J_BASE)
        cfg["slippage_pct"] = slip
        cfg["cost_penalty"] = cp
        configs.append({"name": name, "desc": f"滑点{slip}% 费率惩罚{cp}", "config": cfg})

# ═══ J: 冷却期变体 ═══
for cpd in [0, 5, 10, 20]:
    for cld in [0, 15, 30]:
        name = f"J_cpd{cpd}_cld{cld}"
        cfg = deepcopy(J_BASE)
        cfg["cooldown_profit_days"] = cpd
        cfg["cooldown_loss_days"] = cld
        configs.append({"name": name, "desc": f"止盈冷却{cpd}d 止损冷却{cld}d", "config": cfg})

# ═══ K: 综合最优组合 ═══
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

# ═══ L: 散户定投变体 ═══
for mi in [1000, 2000, 3000, 5000]:
    for mh in [3, 5, 8]:
        name = f"L_mi{mi}_mh{mh}"
        cfg = deepcopy(J_BASE)
        cfg["min_score"] = 0.0
        cfg["monthly_injection"] = mi
        cfg["max_holdings"] = mh
        cfg["kelly_cap"] = 0.25
        configs.append({"name": name, "desc": f"月投{mi} 限仓{mh}", "config": cfg})

# ═══════════════════════════════════════════════════════
# v2 新增策略（M-AK）
# ═══════════════════════════════════════════════════════

# ═══ M: 移动止盈（trailing_tp）═══
# 盈利达激活阈值后，从高点回撤超过阈值则卖出锁利
for act in [10, 15, 20, 30]:
    for dd in [5, 8, 15]:
        name = f"M_trail_act{act}_dd{dd}"
        cfg = deepcopy(J_BASE)
        cfg["min_score"] = 0.0
        cfg["no_stop_loss"] = True
        cfg["take_profit_pct"] = 1000  # 不主动止盈，靠移动止盈
        cfg["trailing_tp_activate"] = act
        cfg["trailing_tp_drawdown"] = dd
        configs.append({"name": name, "desc": f"移动止盈 激活{act}% 回撤{dd}%", "config": cfg})

# ═══ N: 金字塔补仓（pyramiding）═══
# 浮亏5-15%且信号持续时越跌越买，系数递减
for tp in [1000, 50, 80]:
    for sl_flag in [True, False]:
        for mc in [2, 3]:
            name = f"N_pyr_tp{tp}_sl{int(sl_flag)}_mc{mc}"
            cfg = deepcopy(J_BASE)
            cfg["min_score"] = 0.0
            cfg["pyramiding_enabled"] = True
            cfg["take_profit_pct"] = tp
            cfg["no_stop_loss"] = sl_flag
            if not sl_flag:
                cfg["stop_loss_pct"] = -20
            cfg["min_consensus"] = mc
            cfg["max_holdings"] = 8
            cfg["kelly_cap"] = 0.25
            configs.append({"name": name, "desc": f"金字塔 tp={tp} 无止损={sl_flag} mc={mc}", "config": cfg})

# ═══ O: 市场环境自适应（regime_specific）═══
# 牛市宽松、熊市保守、中性适中
regime_combos = [
    # 牛市激进+熊市保守
    {"regime_specific": True, "no_stop_loss": True, "take_profit_pct": 1000,
     "take_profit_pct_bull": 1000, "take_profit_pct_bear": 30, "take_profit_pct_neutral": 50,
     "kelly_cap_bull": 0.35, "kelly_cap_bear": 0.15, "kelly_cap_neutral": 0.25,
     "min_score": 0.0, "min_consensus": 2, "max_holdings": 5},
    # 牛市止盈+熊市止损
    {"regime_specific": True, "no_stop_loss": False, "stop_loss_pct": -20,
     "take_profit_pct": 1000,
     "stop_loss_pct_bull": -30, "stop_loss_pct_bear": -10, "stop_loss_pct_neutral": -20,
     "take_profit_pct_bull": 1000, "take_profit_pct_bear": 20, "take_profit_pct_neutral": 50,
     "min_score": 0.0, "min_consensus": 2, "max_holdings": 5, "kelly_cap": 0.25},
    # 熊市不买入
    {"regime_specific": True, "bear_market_no_buy": True,
     "no_stop_loss": True, "take_profit_pct": 1000,
     "kelly_cap_bull": 0.30, "kelly_cap_bear": 0.10, "kelly_cap_neutral": 0.20,
     "min_score": 0.0, "min_consensus": 2, "max_holdings": 5},
    # 牛市移动止盈+熊市止损
    {"regime_specific": True, "no_stop_loss": False, "stop_loss_pct": -25,
     "take_profit_pct": 1000,
     "trailing_tp_activate": 20, "trailing_tp_drawdown": 10,
     "stop_loss_pct_bull": -30, "stop_loss_pct_bear": -15,
     "min_score": 0.0, "min_consensus": 2, "max_holdings": 8, "kelly_cap": 0.25},
    # 牛市金字塔+熊市保守
    {"regime_specific": True, "pyramiding_enabled": True,
     "no_stop_loss": True, "take_profit_pct": 1000,
     "kelly_cap_bull": 0.35, "kelly_cap_bear": 0.10, "kelly_cap_neutral": 0.25,
     "min_score": 0.0, "min_consensus": 2, "max_holdings": 5},
    # 中性严格+牛市宽松
    {"regime_specific": True, "no_stop_loss": True, "take_profit_pct": 1000,
     "min_score_bull": 0.0, "min_score_bear": 3.3, "min_score_neutral": 1.5,
     "kelly_cap_bull": 0.30, "kelly_cap_bear": 0.15, "kelly_cap_neutral": 0.20,
     "min_consensus": 2, "max_holdings": 8},
    # 仓位随行情变化
    {"regime_specific": True, "no_stop_loss": True, "take_profit_pct": 1000,
     "max_position_pct_bull": 35, "max_position_pct_bear": 15, "max_position_pct_neutral": 25,
     "cash_reserve_pct_bull": 0.05, "cash_reserve_pct_bear": 0.40, "cash_reserve_pct_neutral": 0.20,
     "min_score": 0.0, "min_consensus": 2, "max_holdings": 5, "kelly_cap": 0.25},
    # 全行情金字塔+移动止盈
    {"regime_specific": True, "pyramiding_enabled": True,
     "trailing_tp_activate": 15, "trailing_tp_drawdown": 8,
     "no_stop_loss": True, "take_profit_pct": 1000,
     "kelly_cap_bull": 0.30, "kelly_cap_bear": 0.15, "kelly_cap_neutral": 0.25,
     "min_score": 0.0, "min_consensus": 2, "max_holdings": 8},
    # 动态止损+行情自适应
    {"regime_specific": True, "dynamic_stop_loss": True,
     "no_stop_loss": False, "stop_loss_pct": -25, "take_profit_pct": 1000,
     "stop_loss_pct_bull": -30, "stop_loss_pct_bear": -10, "stop_loss_pct_neutral": -20,
     "min_score": 0.0, "min_consensus": 2, "max_holdings": 5, "kelly_cap": 0.25},
    # 冷却期行情自适应
    {"regime_specific": True, "no_stop_loss": True, "take_profit_pct": 1000,
     "cooldown_profit_days_bull": 5, "cooldown_profit_days_bear": 20, "cooldown_profit_days_neutral": 10,
     "cooldown_loss_days_bull": 15, "cooldown_loss_days_bear": 30, "cooldown_loss_days_neutral": 20,
     "min_score": 0.0, "min_consensus": 2, "max_holdings": 5, "kelly_cap": 0.25},
    # 止盈+止损+行情
    {"regime_specific": True, "no_stop_loss": False, "stop_loss_pct": -20,
     "take_profit_pct": 50,
     "take_profit_pct_bull": 80, "take_profit_pct_bear": 20, "take_profit_pct_neutral": 50,
     "stop_loss_pct_bull": -25, "stop_loss_pct_bear": -10, "stop_loss_pct_neutral": -20,
     "min_score": 0.0, "min_consensus": 2, "max_holdings": 8, "kelly_cap": 0.25},
    # profit_mode行情自适应
    {"regime_specific": True, "no_stop_loss": True, "take_profit_pct": 1000,
     "profit_mode_bull": "all", "profit_mode_bear": "quarter", "profit_mode_neutral": "half",
     "min_score": 0.0, "min_consensus": 2, "max_holdings": 5, "kelly_cap": 0.25},
]
for i, cfg in enumerate(regime_combos):
    name = f"O_regime{i+1}"
    configs.append({"name": name, "desc": f"行情自适应组合{i+1}", "config": cfg})

# ═══ P: 组合级风控（portfolio_dd_breaker + dd_reduce）═══
# 组合回撤>X%时清仓+暂停，或减仓不全清
p_combos = [
    {"portfolio_dd_breaker": 10, "portfolio_dd_pause_days": 5},
    {"portfolio_dd_breaker": 15, "portfolio_dd_pause_days": 5},
    {"portfolio_dd_breaker": 20, "portfolio_dd_pause_days": 10},
    {"portfolio_dd_breaker": 10, "portfolio_dd_pause_days": 10},
    {"portfolio_dd_reduce_pct": 1, "portfolio_dd_reduce_threshold": 8, "portfolio_dd_reduce_frac": 0.3},
    {"portfolio_dd_reduce_pct": 1, "portfolio_dd_reduce_threshold": 12, "portfolio_dd_reduce_frac": 0.5},
    {"portfolio_dd_breaker": 15, "portfolio_dd_pause_days": 5,
     "portfolio_dd_reduce_pct": 1, "portfolio_dd_reduce_threshold": 10, "portfolio_dd_reduce_frac": 0.3},
    {"portfolio_dd_breaker": 20, "portfolio_dd_pause_days": 10,
     "portfolio_dd_reduce_pct": 1, "portfolio_dd_reduce_threshold": 15, "portfolio_dd_reduce_frac": 0.5},
    # 配合止损
    {"portfolio_dd_breaker": 15, "portfolio_dd_pause_days": 5,
     "no_stop_loss": False, "stop_loss_pct": -20, "take_profit_pct": 1000},
    # 配合移动止盈
    {"portfolio_dd_breaker": 15, "portfolio_dd_pause_days": 5,
     "trailing_tp_activate": 20, "trailing_tp_drawdown": 10},
    # 配合金字塔
    {"portfolio_dd_breaker": 15, "portfolio_dd_pause_days": 5,
     "pyramiding_enabled": True},
    # 组合回撤+限仓
    {"portfolio_dd_breaker": 12, "portfolio_dd_pause_days": 7,
     "max_holdings": 5, "kelly_cap": 0.20},
]
for i, pc in enumerate(p_combos):
    name = f"P_risk{i+1}"
    cfg = deepcopy(J_BASE)
    cfg["min_score"] = 0.0
    cfg.update(pc)
    configs.append({"name": name, "desc": f"组合风控{i+1}: {list(pc.keys())[:2]}", "config": cfg})

# ═══ Q: 分散化（correlation + sector + qdii）═══
q_combos = [
    {"max_correlation": 0.3},
    {"max_correlation": 0.5},
    {"max_correlation": 0.7},
    {"max_correlation": 0.5, "max_sector_pct": 30},
    {"max_correlation": 0.5, "max_sector_pct": 40},
    {"max_correlation": 0.3, "max_qdii_pct": 30},
    {"max_correlation": 0.5, "max_qdii_pct": 50},
    {"max_sector_pct": 25, "max_qdii_pct": 30},
    {"max_sector_pct": 30, "max_qdii_pct": 40},
    {"max_correlation": 0.5, "rebalance": True},
    {"max_correlation": 0.3, "max_sector_pct": 30, "rebalance": True},
    {"max_correlation": 0.5, "max_sector_pct": 40, "max_qdii_pct": 50, "rebalance": True},
]
for i, qc in enumerate(q_combos):
    name = f"Q_div{i+1}"
    cfg = deepcopy(J_BASE)
    cfg["min_score"] = 0.0
    cfg["max_holdings"] = 8
    cfg["kelly_cap"] = 0.25
    cfg.update(qc)
    configs.append({"name": name, "desc": f"分散化{i+1}: {list(qc.keys())[:2]}", "config": cfg})

# ═══ R: 动态止损（dynamic_stop_loss + ATR）═══
r_combos = [
    {"dynamic_stop_loss": True, "no_stop_loss": False, "stop_loss_pct": -20, "take_profit_pct": 1000},
    {"dynamic_stop_loss": True, "no_stop_loss": False, "stop_loss_pct": -30, "take_profit_pct": 1000},
    {"dynamic_stop_loss": True, "no_stop_loss": False, "stop_loss_pct": -15, "take_profit_pct": 50},
    {"atr_stop_loss_mult": 2.0, "no_stop_loss": False, "stop_loss_pct": -25, "take_profit_pct": 1000},
    {"atr_stop_loss_mult": 3.0, "no_stop_loss": False, "stop_loss_pct": -25, "take_profit_pct": 1000},
    {"atr_stop_loss_mult": 1.5, "no_stop_loss": False, "stop_loss_pct": -20, "take_profit_pct": 50},
    {"dynamic_stop_loss": True, "atr_stop_loss_mult": 2.0, "no_stop_loss": False, "stop_loss_pct": -25, "take_profit_pct": 1000},
    # 动态止损+移动止盈
    {"dynamic_stop_loss": True, "no_stop_loss": False, "stop_loss_pct": -25, "take_profit_pct": 1000,
     "trailing_tp_activate": 20, "trailing_tp_drawdown": 10},
    # 动态止损+金字塔
    {"dynamic_stop_loss": True, "pyramiding_enabled": True, "no_stop_loss": False,
     "stop_loss_pct": -25, "take_profit_pct": 1000},
    # 动态止损+行情自适应
    {"dynamic_stop_loss": True, "regime_specific": True, "no_stop_loss": False,
     "stop_loss_pct": -25, "take_profit_pct": 1000,
     "stop_loss_pct_bull": -30, "stop_loss_pct_bear": -10, "stop_loss_pct_neutral": -20},
]
for i, rc in enumerate(r_combos):
    name = f"R_dyn{i+1}"
    cfg = deepcopy(J_BASE)
    cfg["min_score"] = 0.0
    cfg["max_holdings"] = 5
    cfg["kelly_cap"] = 0.25
    cfg.update(rc)
    configs.append({"name": name, "desc": f"动态止损{i+1}", "config": cfg})

# ═══ S: 散户资金模拟（initial_cash × slippage × holdings）═══
# 测试不同资金规模下策略是否仍然有效
for ic in [5000, 10000, 20000, 50000]:
    for slip in [0.0, 0.5, 1.0]:
        for mh in [5, 0]:
            if mh == 0 and slip > 0:
                continue  # 去重
            name = f"S_ic{ic}_slip{slip}_mh{mh}"
            cfg = deepcopy(J_BASE)
            cfg["min_score"] = 0.0
            cfg["initial_cash"] = ic
            cfg["slippage_pct"] = slip
            cfg["max_holdings"] = mh
            if mh > 0:
                cfg["kelly_cap"] = 0.25
            configs.append({"name": name, "desc": f"资金{ic} 滑点{slip}% 限仓{mh}", "config": cfg})

# ═══ T: 定投深入（monthly_injection × holdings × kelly）═══
# 散户每月工资定投，测试不同金额和限仓组合
for mi in [1000, 2000, 3000, 5000]:
    for mh in [3, 5, 8, 0]:
        for kc in [0.20, 0.30]:
            if mh == 0 and kc == 0.30:
                continue  # 去重
            name = f"T_mi{mi}_mh{mh}_kc{kc}"
            cfg = deepcopy(J_BASE)
            cfg["min_score"] = 0.0
            cfg["monthly_injection"] = mi
            cfg["max_holdings"] = mh
            cfg["kelly_cap"] = kc
            if mh == 0:
                cfg["kelly_cap"] = 0
            configs.append({"name": name, "desc": f"月投{mi} 限仓{mh} kelly={kc}", "config": cfg})

# ═══ U: 滑点压力测试（0-2%）═══
# 极端滑点下策略是否仍然有效
for slip in [0.0, 0.3, 0.5, 0.8, 1.0, 1.5, 2.0]:
    for base_name, base_cfg in [("J", J_BASE), ("K", K_BASE)]:
        if slip == 0.0 and base_name == "J":
            continue  # 去重（A类已覆盖）
        name = f"U_slip{slip}_{base_name}"
        cfg = deepcopy(base_cfg)
        cfg["slippage_pct"] = slip
        cfg["min_score"] = 0.0
        if base_name == "K":
            cfg["no_stop_loss"] = True
            cfg["take_profit_pct"] = 1000
        configs.append({"name": name, "desc": f"滑点{slip}% ({base_name}基础)", "config": cfg})

# ═══ V: 保守防御（严止损+高滑点+限仓+冷却）═══
# 极度保守的策略，适合风险厌恶型散户
v_combos = [
    {"no_stop_loss": False, "stop_loss_pct": -8, "take_profit_pct": 20,
     "slippage_pct": 1.0, "max_holdings": 5, "kelly_cap": 0.15,
     "min_holding_days": 90, "cooldown_profit_days": 15, "cooldown_loss_days": 30},
    {"no_stop_loss": False, "stop_loss_pct": -10, "take_profit_pct": 30,
     "slippage_pct": 0.8, "max_holdings": 3, "kelly_cap": 0.15,
     "min_holding_days": 60, "cooldown_profit_days": 10, "cooldown_loss_days": 20},
    {"no_stop_loss": False, "stop_loss_pct": -5, "take_profit_pct": 15,
     "slippage_pct": 1.0, "max_holdings": 3, "kelly_cap": 0.10,
     "min_holding_days": 120, "max_yearly_trades": 30},
    {"no_stop_loss": False, "stop_loss_pct": -10, "take_profit_pct": 50,
     "slippage_pct": 0.5, "max_holdings": 5, "kelly_cap": 0.20,
     "portfolio_dd_breaker": 10, "portfolio_dd_pause_days": 10},
    {"no_stop_loss": False, "stop_loss_pct": -15, "take_profit_pct": 30,
     "slippage_pct": 0.5, "max_holdings": 8, "kelly_cap": 0.20,
     "min_consensus": 3, "min_holding_days": 60},
    {"no_stop_loss": False, "stop_loss_pct": -8, "take_profit_pct": 1000,
     "slippage_pct": 0.8, "max_holdings": 5, "kelly_cap": 0.15,
     "trailing_tp_activate": 15, "trailing_tp_drawdown": 5},
    {"no_stop_loss": False, "stop_loss_pct": -10, "take_profit_pct": 1000,
     "slippage_pct": 1.0, "max_holdings": 3, "kelly_cap": 0.15,
     "dynamic_stop_loss": True, "portfolio_dd_breaker": 12},
    {"no_stop_loss": False, "stop_loss_pct": -12, "take_profit_pct": 40,
     "slippage_pct": 0.5, "max_holdings": 5, "kelly_cap": 0.20,
     "max_correlation": 0.5, "max_sector_pct": 30},
    {"no_stop_loss": False, "stop_loss_pct": -8, "take_profit_pct": 25,
     "slippage_pct": 0.8, "max_holdings": 5, "kelly_cap": 0.15,
     "profit_mode": "quarter", "min_holding_days": 90},
    {"no_stop_loss": False, "stop_loss_pct": -10, "take_profit_pct": 30,
     "slippage_pct": 0.5, "max_holdings": 5, "kelly_cap": 0.20,
     "regime_specific": True, "stop_loss_pct_bear": -5, "stop_loss_pct_bull": -15},
    {"no_stop_loss": False, "stop_loss_pct": -15, "take_profit_pct": 1000,
     "slippage_pct": 0.5, "max_holdings": 8, "kelly_cap": 0.25,
     "step_take_profit": True, "min_holding_days": 60},
    {"no_stop_loss": False, "stop_loss_pct": -10, "take_profit_pct": 50,
     "slippage_pct": 1.0, "max_holdings": 5, "kelly_cap": 0.15,
     "min_consensus": 3, "net_signal": True, "cooldown_loss_days": 30},
    {"no_stop_loss": False, "stop_loss_pct": -8, "take_profit_pct": 30,
     "slippage_pct": 0.8, "max_holdings": 3, "kelly_cap": 0.10,
     "use_weighted_consensus": True, "min_holding_days": 90, "max_yearly_trades": 30},
    {"no_stop_loss": False, "stop_loss_pct": -12, "take_profit_pct": 1000,
     "slippage_pct": 0.5, "max_holdings": 5, "kelly_cap": 0.20,
     "atr_stop_loss_mult": 2.0, "min_holding_days": 60},
    {"no_stop_loss": False, "stop_loss_pct": -10, "take_profit_pct": 40,
     "slippage_pct": 0.5, "max_holdings": 5, "kelly_cap": 0.20,
     "momentum_sell": 1.5, "min_holding_days": 60, "cooldown_profit_days": 10},
]
for i, vc in enumerate(v_combos):
    name = f"V_cons{i+1}"
    cfg = deepcopy(J_BASE)
    cfg["min_score"] = 0.0
    cfg.update(vc)
    configs.append({"name": name, "desc": f"保守防御{i+1}", "config": cfg})

# ═══ W: 激进增长（无止损+低限仓+无冷却）═══
# 极度激进的策略，最大化收益
w_combos = [
    {"no_stop_loss": True, "take_profit_pct": 1000, "min_consensus": 1, "max_holdings": 0},
    {"no_stop_loss": True, "take_profit_pct": 1000, "min_consensus": 1, "max_holdings": 0,
     "kelly_cap": 0.40, "max_position_pct": 50, "cash_reserve_pct": 0.0},
    {"no_stop_loss": True, "take_profit_pct": 1000, "min_consensus": 1, "max_holdings": 0,
     "kelly_cap": 0.50, "max_single_buy_pct": 0.50, "cash_reserve_pct": 0.0},
    {"no_stop_loss": True, "take_profit_pct": 1000, "min_consensus": 2, "max_holdings": 0,
     "kelly_cap": 0.40, "max_position_pct": 40},
    {"no_stop_loss": True, "take_profit_pct": 1000, "min_consensus": 1, "max_holdings": 3,
     "kelly_cap": 0.50, "max_position_pct": 50},
    {"no_stop_loss": True, "take_profit_pct": 1000, "min_consensus": 1, "max_holdings": 0,
     "pyramiding_enabled": True, "kelly_cap": 0.40},
    {"no_stop_loss": True, "take_profit_pct": 1000, "min_consensus": 1, "max_holdings": 0,
     "kelly_fraction": 1.0, "kelly_cap": 0.40},
    {"no_stop_loss": True, "take_profit_pct": 1000, "min_consensus": 1, "max_holdings": 5,
     "kelly_cap": 0.35, "monthly_injection": 5000},
    {"no_stop_loss": True, "take_profit_pct": 1000, "min_consensus": 1, "max_holdings": 0,
     "min_holding_days": 0, "max_yearly_trades": 200},
    {"no_stop_loss": True, "take_profit_pct": 1000, "min_consensus": 1, "max_holdings": 0,
     "equal_allocate": False, "kelly_cap": 0.40, "max_position_pct": 50},
    {"no_stop_loss": True, "take_profit_pct": 2000, "min_consensus": 1, "max_holdings": 0,
     "kelly_cap": 0.35, "profit_mode": "all"},
    {"no_stop_loss": True, "take_profit_pct": 1000, "min_consensus": 1, "max_holdings": 0,
     "use_weighted_consensus": True, "adaptive_consensus": True, "kelly_cap": 0.35},
    {"no_stop_loss": True, "take_profit_pct": 1000, "min_consensus": 1, "max_holdings": 3,
     "kelly_cap": 0.40, "max_position_pct": 50, "pyramiding_enabled": True},
    {"no_stop_loss": True, "take_profit_pct": 1000, "min_consensus": 2, "max_holdings": 0,
     "kelly_cap": 0.35, "fund_type_filter": "active", "kelly_fraction": 0.75},
    {"no_stop_loss": True, "take_profit_pct": 1000, "min_consensus": 1, "max_holdings": 0,
     "kelly_cap": 0.35, "max_position_pct": 40, "cash_reserve_pct": 0.0,
     "monthly_injection": 3000},
]
for i, wc in enumerate(w_combos):
    name = f"W_aggr{i+1}"
    cfg = deepcopy(J_BASE)
    cfg["min_score"] = 0.0
    cfg.update(wc)
    configs.append({"name": name, "desc": f"激进增长{i+1}", "config": cfg})

# ═══ X: 终极组合（手工打造最佳组合）═══
# 综合多个维度的最佳实践
x_combos = [
    # 买入持有+移动止盈+限仓
    {"min_score": 0.0, "no_stop_loss": True, "take_profit_pct": 1000,
     "trailing_tp_activate": 20, "trailing_tp_drawdown": 10,
     "max_holdings": 5, "kelly_cap": 0.25, "min_consensus": 2},
    # 买入持有+金字塔+限仓
    {"min_score": 0.0, "no_stop_loss": True, "take_profit_pct": 1000,
     "pyramiding_enabled": True,
     "max_holdings": 5, "kelly_cap": 0.25, "min_consensus": 2},
    # 买入持有+组合风控+限仓
    {"min_score": 0.0, "no_stop_loss": True, "take_profit_pct": 1000,
     "portfolio_dd_breaker": 15, "portfolio_dd_pause_days": 5,
     "max_holdings": 5, "kelly_cap": 0.25, "min_consensus": 2},
    # 买入持有+分散化+限仓
    {"min_score": 0.0, "no_stop_loss": True, "take_profit_pct": 1000,
     "max_correlation": 0.5, "max_sector_pct": 40,
     "max_holdings": 8, "kelly_cap": 0.25, "min_consensus": 2},
    # 买入持有+行情自适应+限仓
    {"min_score": 0.0, "regime_specific": True,
     "no_stop_loss": True, "take_profit_pct": 1000,
     "kelly_cap_bull": 0.30, "kelly_cap_bear": 0.15, "kelly_cap_neutral": 0.25,
     "max_holdings": 5, "min_consensus": 2},
    # 买入持有+定投+限仓
    {"min_score": 0.0, "no_stop_loss": True, "take_profit_pct": 1000,
     "monthly_injection": 2000, "max_holdings": 5, "kelly_cap": 0.25, "min_consensus": 2},
    # 买入持有+滑点+限仓
    {"min_score": 0.0, "no_stop_loss": True, "take_profit_pct": 1000,
     "slippage_pct": 0.5, "cost_penalty": 0.5,
     "max_holdings": 5, "kelly_cap": 0.25, "min_consensus": 2},
    # 金字塔+移动止盈+行情
    {"min_score": 0.0, "regime_specific": True,
     "pyramiding_enabled": True,
     "trailing_tp_activate": 15, "trailing_tp_drawdown": 8,
     "no_stop_loss": True, "take_profit_pct": 1000,
     "kelly_cap_bull": 0.30, "kelly_cap_bear": 0.15, "kelly_cap_neutral": 0.25,
     "max_holdings": 8, "min_consensus": 2},
    # 买入持有+冷却+限仓
    {"min_score": 0.0, "no_stop_loss": True, "take_profit_pct": 1000,
     "cooldown_profit_days": 10, "cooldown_loss_days": 30,
     "max_holdings": 5, "kelly_cap": 0.25, "min_consensus": 2},
    # 买入持有+自适应共识+加权
    {"min_score": 0.0, "no_stop_loss": True, "take_profit_pct": 1000,
     "use_weighted_consensus": True, "adaptive_consensus": True,
     "max_holdings": 5, "kelly_cap": 0.25, "min_consensus": 2},
    # 买入持有+净信号+卖共识
    {"min_score": 0.0, "no_stop_loss": True, "take_profit_pct": 1000,
     "net_signal": True, "sell_consensus": 2,
     "max_holdings": 5, "kelly_cap": 0.25, "min_consensus": 2},
    # 买入持有+阶梯止盈
    {"min_score": 0.0, "no_stop_loss": True, "take_profit_pct": 1000,
     "step_take_profit": True,
     "max_holdings": 5, "kelly_cap": 0.25, "min_consensus": 2},
    # 保守+行情+金字塔
    {"min_score": 0.0, "regime_specific": True,
     "pyramiding_enabled": True,
     "no_stop_loss": False, "stop_loss_pct": -20, "take_profit_pct": 1000,
     "stop_loss_pct_bull": -25, "stop_loss_pct_bear": -10,
     "max_holdings": 5, "kelly_cap": 0.25, "min_consensus": 2},
    # 买入持有+组合风控+分散化
    {"min_score": 0.0, "no_stop_loss": True, "take_profit_pct": 1000,
     "portfolio_dd_breaker": 15, "portfolio_dd_pause_days": 5,
     "max_correlation": 0.5, "max_sector_pct": 40,
     "max_holdings": 8, "kelly_cap": 0.25, "min_consensus": 2},
    # 买入持有+移动止盈+金字塔+行情
    {"min_score": 0.0, "regime_specific": True,
     "pyramiding_enabled": True,
     "trailing_tp_activate": 20, "trailing_tp_drawdown": 10,
     "no_stop_loss": True, "take_profit_pct": 1000,
     "max_holdings": 5, "kelly_cap": 0.25, "min_consensus": 2},
    # 定投+移动止盈+限仓
    {"min_score": 0.0, "no_stop_loss": True, "take_profit_pct": 1000,
     "monthly_injection": 3000, "trailing_tp_activate": 20, "trailing_tp_drawdown": 10,
     "max_holdings": 5, "kelly_cap": 0.25, "min_consensus": 2},
    # 定投+金字塔+限仓
    {"min_score": 0.0, "no_stop_loss": True, "take_profit_pct": 1000,
     "monthly_injection": 3000, "pyramiding_enabled": True,
     "max_holdings": 5, "kelly_cap": 0.25, "min_consensus": 2},
    # 定投+行情+限仓
    {"min_score": 0.0, "regime_specific": True,
     "no_stop_loss": True, "take_profit_pct": 1000,
     "monthly_injection": 3000,
     "kelly_cap_bull": 0.30, "kelly_cap_bear": 0.15, "kelly_cap_neutral": 0.25,
     "max_holdings": 5, "min_consensus": 2},
    # 激进+移动止盈+组合风控
    {"min_score": 0.0, "no_stop_loss": True, "take_profit_pct": 1000,
     "trailing_tp_activate": 30, "trailing_tp_drawdown": 15,
     "portfolio_dd_breaker": 20, "portfolio_dd_pause_days": 5,
     "max_holdings": 3, "kelly_cap": 0.35, "min_consensus": 1},
    # 保守+定投+分散化
    {"min_score": 0.0, "no_stop_loss": False, "stop_loss_pct": -15, "take_profit_pct": 50,
     "monthly_injection": 2000, "max_correlation": 0.5, "max_sector_pct": 30,
     "max_holdings": 5, "kelly_cap": 0.20, "min_consensus": 3,
     "slippage_pct": 0.5, "min_holding_days": 60},
    # 全功能组合
    {"min_score": 0.0, "regime_specific": True,
     "pyramiding_enabled": True,
     "trailing_tp_activate": 20, "trailing_tp_drawdown": 10,
     "portfolio_dd_breaker": 15, "portfolio_dd_pause_days": 5,
     "max_correlation": 0.5, "max_sector_pct": 40,
     "no_stop_loss": True, "take_profit_pct": 1000,
     "max_holdings": 8, "kelly_cap": 0.25, "min_consensus": 2,
     "monthly_injection": 2000, "slippage_pct": 0.3,
     "use_weighted_consensus": True, "adaptive_consensus": True},
    # 买入持有+技术过滤
    {"min_score": 0.0, "no_stop_loss": True, "take_profit_pct": 1000,
     "weekly_macd_divergence": True, "yearly_ma_filter": True,
     "max_holdings": 5, "kelly_cap": 0.25, "min_consensus": 2},
    # 买入持有+布林带
    {"min_score": 0.0, "no_stop_loss": True, "take_profit_pct": 1000,
     "weekly_bollinger_adjust": True,
     "max_holdings": 5, "kelly_cap": 0.25, "min_consensus": 2},
    # 买入持有+ATR止损+移动止盈
    {"min_score": 0.0, "no_stop_loss": False, "stop_loss_pct": -25, "take_profit_pct": 1000,
     "atr_stop_loss_mult": 2.0,
     "trailing_tp_activate": 20, "trailing_tp_drawdown": 10,
     "max_holdings": 5, "kelly_cap": 0.25, "min_consensus": 2},
    # 买入持有+凯利分数+等额分配
    {"min_score": 0.0, "no_stop_loss": True, "take_profit_pct": 1000,
     "kelly_fraction": 0.75, "equal_allocate": True,
     "max_holdings": 5, "kelly_cap": 0.25, "min_consensus": 2},
]
for i, xc in enumerate(x_combos):
    name = f"X_ult{i+1}"
    configs.append({"name": name, "desc": f"终极组合{i+1}", "config": xc})

# ═══ Y: 最低持有天数 ═══
for mhd in [30, 60, 90, 120]:
    for base_name, base_cfg in [("J", J_BASE), ("K", K_BASE)]:
        name = f"Y_mhd{mhd}_{base_name}"
        cfg = deepcopy(base_cfg)
        cfg["min_score"] = 0.0
        cfg["min_holding_days"] = mhd
        if base_name == "K":
            cfg["no_stop_loss"] = True
            cfg["take_profit_pct"] = 1000
        configs.append({"name": name, "desc": f"最低持有{mhd}天 ({base_name})", "config": cfg})

# ═══ Z: 年交易上限 ═══
for myt in [30, 50, 100]:
    for base_name, base_cfg in [("J", J_BASE), ("K", K_BASE)]:
        name = f"Z_myt{myt}_{base_name}"
        cfg = deepcopy(base_cfg)
        cfg["min_score"] = 0.0
        cfg["max_yearly_trades"] = myt
        if base_name == "K":
            cfg["no_stop_loss"] = True
            cfg["take_profit_pct"] = 1000
        configs.append({"name": name, "desc": f"年交易上限{myt} ({base_name})", "config": cfg})

# ═══ AA: 大佬加权（player_weights + exclude）═══
# 需要配合run_backtest._rank_weights使用，这里只设config标志
aa_combos = [
    {"use_weighted_consensus": True, "min_consensus": 2, "no_stop_loss": True, "take_profit_pct": 1000,
     "max_holdings": 5, "kelly_cap": 0.25, "min_score": 0.0},
    {"use_weighted_consensus": True, "weighted_consensus_threshold": 1.5, "no_stop_loss": True,
     "take_profit_pct": 1000, "max_holdings": 5, "kelly_cap": 0.25, "min_score": 0.0},
    {"use_weighted_consensus": True, "weighted_consensus_threshold": 2.0, "no_stop_loss": True,
     "take_profit_pct": 1000, "max_holdings": 8, "kelly_cap": 0.25, "min_score": 0.0},
    {"use_weighted_consensus": True, "weighted_consensus_threshold": 3.0, "no_stop_loss": True,
     "take_profit_pct": 1000, "max_holdings": 0, "kelly_cap": 0, "min_score": 0.0},
    {"use_weighted_consensus": True, "adaptive_consensus": True, "net_signal": True,
     "no_stop_loss": True, "take_profit_pct": 1000,
     "max_holdings": 5, "kelly_cap": 0.25, "min_score": 0.0},
    {"use_weighted_consensus": True, "net_signal": True, "net_signal_diff": 2,
     "no_stop_loss": True, "take_profit_pct": 1000,
     "max_holdings": 5, "kelly_cap": 0.25, "min_score": 0.0},
    {"use_weighted_consensus": True, "net_signal": True, "net_signal_ratio": 2,
     "no_stop_loss": True, "take_profit_pct": 1000,
     "max_holdings": 5, "kelly_cap": 0.25, "min_score": 0.0},
    {"use_weighted_consensus": True, "net_signal": True, "net_signal_diff": 3,
     "no_stop_loss": True, "take_profit_pct": 1000,
     "max_holdings": 8, "kelly_cap": 0.30, "min_score": 0.0},
    {"use_weighted_consensus": True, "adaptive_consensus": True, "net_signal": True,
     "sell_consensus": 2, "no_stop_loss": True, "take_profit_pct": 1000,
     "max_holdings": 5, "kelly_cap": 0.25, "min_score": 0.0},
    {"use_weighted_consensus": True, "weighted_consensus_threshold": 2.5,
     "net_signal": True, "net_signal_diff": 2,
     "no_stop_loss": True, "take_profit_pct": 1000,
     "max_holdings": 5, "kelly_cap": 0.25, "min_score": 0.0},
]
for i, ac in enumerate(aa_combos):
    name = f"AA_wt{i+1}"
    configs.append({"name": name, "desc": f"大佬加权{i+1}", "config": ac})

# ═══ AB: 排名窗口 ═══
for rw in [60, 90, 120, 180]:
    for hl in [30, 45]:
        if rw == 90 and hl == 45:
            continue  # 默认值，去重
        name = f"AB_rw{rw}_hl{hl}"
        cfg = deepcopy(J_BASE)
        cfg["min_score"] = 0.0
        cfg["ranking_window"] = rw
        cfg["ranking_half_life"] = hl
        cfg["use_weighted_consensus"] = True
        cfg["max_holdings"] = 5
        cfg["kelly_cap"] = 0.25
        configs.append({"name": name, "desc": f"排名窗口{rw}天 半衰期{hl}天", "config": cfg})

# ═══ AC: 市场风险过滤 ═══
ac_combos = [
    {"market_risk_filter": True, "market_risk_threshold": 60, "market_risk_caution": 30,
     "no_stop_loss": True, "take_profit_pct": 1000, "min_score": 0.0,
     "max_holdings": 5, "kelly_cap": 0.25, "min_consensus": 2},
    {"market_risk_filter": True, "market_risk_threshold": 50, "market_risk_caution": 25,
     "no_stop_loss": True, "take_profit_pct": 1000, "min_score": 0.0,
     "max_holdings": 5, "kelly_cap": 0.25, "min_consensus": 2},
    {"market_risk_filter": True, "market_risk_threshold": 70, "market_risk_caution": 40,
     "no_stop_loss": True, "take_profit_pct": 1000, "min_score": 0.0,
     "max_holdings": 5, "kelly_cap": 0.25, "min_consensus": 2},
    {"market_predictor": True, "predictor_prob_threshold": 0.6,
     "no_stop_loss": True, "take_profit_pct": 1000, "min_score": 0.0,
     "max_holdings": 5, "kelly_cap": 0.25, "min_consensus": 2},
    {"market_predictor": True, "predictor_prob_threshold": 0.5, "predictor_sell_threshold": 0.8,
     "no_stop_loss": True, "take_profit_pct": 1000, "min_score": 0.0,
     "max_holdings": 5, "kelly_cap": 0.25, "min_consensus": 2},
    {"lgb_predictor": True, "lgb_buy_stop_threshold": 0.7,
     "no_stop_loss": True, "take_profit_pct": 1000, "min_score": 0.0,
     "max_holdings": 5, "kelly_cap": 0.25, "min_consensus": 2},
    {"lgb_predictor": True, "lgb_buy_stop_threshold": 0.6, "lgb_sell_threshold": 0.8,
     "no_stop_loss": True, "take_profit_pct": 1000, "min_score": 0.0,
     "max_holdings": 5, "kelly_cap": 0.25, "min_consensus": 2},
    {"market_risk_filter": True, "market_risk_threshold": 60,
     "lgb_predictor": True, "lgb_buy_stop_threshold": 0.7,
     "no_stop_loss": True, "take_profit_pct": 1000, "min_score": 0.0,
     "max_holdings": 5, "kelly_cap": 0.25, "min_consensus": 2},
    {"market_risk_filter": True, "market_risk_threshold": 50,
     "portfolio_dd_breaker": 15, "portfolio_dd_pause_days": 5,
     "no_stop_loss": True, "take_profit_pct": 1000, "min_score": 0.0,
     "max_holdings": 5, "kelly_cap": 0.25, "min_consensus": 2},
    {"market_predictor": True, "predictor_prob_threshold": 0.6,
     "portfolio_dd_breaker": 15, "portfolio_dd_pause_days": 5,
     "no_stop_loss": True, "take_profit_pct": 1000, "min_score": 0.0,
     "max_holdings": 5, "kelly_cap": 0.25, "min_consensus": 2},
]
for i, acc in enumerate(ac_combos):
    name = f"AC_risk{i+1}"
    configs.append({"name": name, "desc": f"市场风险过滤{i+1}", "config": acc})

# ═══ AD: 技术指标叠加 ═══
ad_combos = [
    {"weekly_macd_divergence": True},
    {"weekly_bollinger_adjust": True},
    {"yearly_ma_filter": True},
    {"weekly_macd_divergence": True, "yearly_ma_filter": True},
    {"weekly_macd_divergence": True, "weekly_bollinger_adjust": True},
    {"weekly_bollinger_adjust": True, "yearly_ma_filter": True},
    {"weekly_macd_divergence": True, "weekly_bollinger_adjust": True, "yearly_ma_filter": True},
    {"kdj_sell_mode": "death_cross"},
    {"kdj_sell_mode": "overbought_exit"},
    {"vol_spike_mult": 2.0},
    {"vol_spike_mult": 3.0},
    {"vol_spike_mult": 4.0},
    {"weekly_macd_divergence": True, "kdj_sell_mode": "death_cross"},
    {"yearly_ma_filter": True, "vol_spike_mult": 3.0},
    {"weekly_macd_divergence": True, "weekly_bollinger_adjust": True,
     "kdj_sell_mode": "death_cross", "vol_spike_mult": 3.0},
]
for i, adc in enumerate(ad_combos):
    name = f"AD_tech{i+1}"
    cfg = deepcopy(J_BASE)
    cfg["min_score"] = 0.0
    cfg["no_stop_loss"] = True
    cfg["take_profit_pct"] = 1000
    cfg["max_holdings"] = 5
    cfg["kelly_cap"] = 0.25
    cfg.update(adc)
    configs.append({"name": name, "desc": f"技术指标{i+1}: {list(adc.keys())[:2]}", "config": cfg})

# ═══ AE: 阶梯止盈 ═══
ae_combos = [
    {"step_take_profit": True, "no_stop_loss": True, "take_profit_pct": 1000},
    {"step_take_profit": True, "step_tp_levels": [(20, 0.3), (40, 0.3), (60, 0.4)],
     "no_stop_loss": True, "take_profit_pct": 1000},
    {"step_take_profit": True, "step_tp_levels": [(15, 0.5), (30, 0.5)],
     "no_stop_loss": True, "take_profit_pct": 1000},
    {"step_take_profit": True, "step_tp_levels": [(25, 0.3), (50, 0.4), (100, 0.3)],
     "no_stop_loss": True, "take_profit_pct": 1000},
    {"step_take_profit": True, "no_stop_loss": False, "stop_loss_pct": -20, "take_profit_pct": 1000},
    {"step_take_profit": True, "trailing_tp_activate": 20, "trailing_tp_drawdown": 10,
     "no_stop_loss": True, "take_profit_pct": 1000},
    {"step_take_profit": True, "pyramiding_enabled": True,
     "no_stop_loss": True, "take_profit_pct": 1000},
    {"step_take_profit": True, "regime_specific": True,
     "no_stop_loss": True, "take_profit_pct": 1000,
     "kelly_cap_bull": 0.30, "kelly_cap_bear": 0.15, "kelly_cap_neutral": 0.25},
    {"step_take_profit": True, "portfolio_dd_breaker": 15, "portfolio_dd_pause_days": 5,
     "no_stop_loss": True, "take_profit_pct": 1000},
    {"step_take_profit": True, "monthly_injection": 2000,
     "no_stop_loss": True, "take_profit_pct": 1000,
     "max_holdings": 5, "kelly_cap": 0.25},
]
for i, aec in enumerate(ae_combos):
    name = f"AE_step{i+1}"
    cfg = deepcopy(J_BASE)
    cfg["min_score"] = 0.0
    cfg["max_holdings"] = 5
    cfg["kelly_cap"] = 0.25
    cfg.update(aec)
    configs.append({"name": name, "desc": f"阶梯止盈{i+1}", "config": cfg})

# ═══ AF: 凯利分数 ═══
for kf in [0.25, 0.5, 0.75, 1.0]:
    for ea in [True, False]:
        if kf == 0.5 and not ea:
            continue  # 默认值，去重
        name = f"AF_kf{kf}_ea{int(ea)}"
        cfg = deepcopy(J_BASE)
        cfg["min_score"] = 0.0
        cfg["kelly_fraction"] = kf
        cfg["equal_allocate"] = ea
        cfg["max_holdings"] = 5
        cfg["kelly_cap"] = 0.25
        configs.append({"name": name, "desc": f"凯利分数={kf} 等额={ea}", "config": cfg})

# ═══ AG: 现金储备 ═══
for cr in [0.05, 0.10, 0.20, 0.30, 0.40]:
    for mp in [15, 25, 35]:
        if cr == 0.10 and mp == 25:
            continue  # 接近默认值，去重
        name = f"AG_cr{cr}_mp{mp}"
        cfg = deepcopy(J_BASE)
        cfg["min_score"] = 0.0
        cfg["cash_reserve_pct"] = cr
        cfg["max_position_pct"] = mp
        cfg["max_holdings"] = 5
        cfg["kelly_cap"] = 0.25
        configs.append({"name": name, "desc": f"现金储备={cr} 最大仓位={mp}%", "config": cfg})

# ═══ AH: 动量信号源 ═══
ah_combos = [
    {"signal_source": "momentum", "momentum_lookback": 21, "momentum_top_n": 10,
     "momentum_rebalance_days": 21, "no_stop_loss": True, "take_profit_pct": 1000},
    {"signal_source": "momentum", "momentum_lookback": 63, "momentum_top_n": 10,
     "momentum_rebalance_days": 21, "no_stop_loss": True, "take_profit_pct": 1000},
    {"signal_source": "momentum", "momentum_lookback": 126, "momentum_top_n": 10,
     "momentum_rebalance_days": 42, "no_stop_loss": True, "take_profit_pct": 1000},
    {"signal_source": "momentum", "momentum_lookback": 63, "momentum_top_n": 5,
     "momentum_rebalance_days": 21, "no_stop_loss": True, "take_profit_pct": 1000},
    {"signal_source": "momentum", "momentum_lookback": 63, "momentum_top_n": 20,
     "momentum_rebalance_days": 42, "no_stop_loss": True, "take_profit_pct": 1000},
    {"signal_source": "momentum", "momentum_lookback": 126, "momentum_top_n": 20,
     "momentum_rebalance_days": 63, "no_stop_loss": True, "take_profit_pct": 1000},
    {"signal_source": "momentum", "momentum_lookback": 63, "momentum_top_n": 10,
     "momentum_rebalance_days": 21, "no_stop_loss": False, "stop_loss_pct": -20,
     "take_profit_pct": 50},
    {"signal_source": "momentum", "momentum_lookback": 126, "momentum_top_n": 10,
     "momentum_rebalance_days": 42, "no_stop_loss": True, "take_profit_pct": 1000,
     "trailing_tp_activate": 20, "trailing_tp_drawdown": 10},
]
for i, ahc in enumerate(ah_combos):
    name = f"AH_mom{i+1}"
    cfg = deepcopy(J_BASE)
    cfg["min_score"] = 0.0
    cfg["max_holdings"] = 10
    cfg["kelly_cap"] = 0.25
    cfg.update(ahc)
    configs.append({"name": name, "desc": f"动量信号{i+1}", "config": cfg})

# ═══ AI: QDII+行业限制 ═══
ai_combos = [
    {"max_qdii_pct": 20, "max_sector_pct": 30},
    {"max_qdii_pct": 30, "max_sector_pct": 40},
    {"max_qdii_pct": 50, "max_sector_pct": 50},
    {"max_qdii_pct": 30, "max_sector_pct": 30, "rebalance": True},
    {"max_qdii_pct": 50, "max_sector_pct": 40, "max_correlation": 0.5},
    {"max_qdii_pct": 20, "max_sector_pct": 25, "max_correlation": 0.3},
    {"max_qdii_pct": 0, "max_sector_pct": 30},  # 完全禁QDII
    {"max_qdii_pct": 100, "max_sector_pct": 25, "rebalance": True, "max_correlation": 0.5},
]
for i, aic in enumerate(ai_combos):
    name = f"AI_qdii{i+1}"
    cfg = deepcopy(J_BASE)
    cfg["min_score"] = 0.0
    cfg["max_holdings"] = 8
    cfg["kelly_cap"] = 0.25
    cfg.update(aic)
    configs.append({"name": name, "desc": f"QDII+行业{i+1}", "config": cfg})

# ═══ AJ: 极端组合 ═══
aj_combos = [
    # 全押：无任何限制
    {"min_score": 0.0, "no_stop_loss": True, "take_profit_pct": 10000,
     "min_consensus": 1, "max_holdings": 0, "kelly_cap": 0,
     "min_holding_days": 0, "max_yearly_trades": 999,
     "cash_reserve_pct": 0.0, "max_position_pct": 100,
     "max_single_buy_pct": 1.0, "kelly_fraction": 1.0},
    # 超保守：一切从严
    {"min_score": 3.3, "no_stop_loss": False, "stop_loss_pct": -5, "take_profit_pct": 10,
     "min_consensus": 5, "max_holdings": 3, "kelly_cap": 0.10,
     "min_holding_days": 120, "max_yearly_trades": 20,
     "cash_reserve_pct": 0.40, "max_position_pct": 15,
     "slippage_pct": 1.0, "cost_penalty": 1.0,
     "cooldown_profit_days": 20, "cooldown_loss_days": 60},
    # 最大分散化
    {"min_score": 0.0, "no_stop_loss": True, "take_profit_pct": 1000,
     "min_consensus": 1, "max_holdings": 15, "kelly_cap": 0.15,
     "max_correlation": 0.3, "max_sector_pct": 20, "max_qdii_pct": 20,
     "rebalance": True, "equal_allocate": True},
    # 纯被动指数
    {"min_score": 0.0, "no_stop_loss": True, "take_profit_pct": 1000,
     "fund_type_filter": "passive", "min_consensus": 1,
     "max_holdings": 10, "kelly_cap": 0.20},
    # 纯主动基金
    {"min_score": 0.0, "no_stop_loss": True, "take_profit_pct": 1000,
     "fund_type_filter": "active", "min_consensus": 2,
     "max_holdings": 5, "kelly_cap": 0.25},
    # 超高频交易
    {"min_score": 0.0, "no_stop_loss": True, "take_profit_pct": 1000,
     "min_consensus": 1, "max_holdings": 0, "kelly_cap": 0,
     "min_holding_days": 0, "max_yearly_trades": 500,
     "cooldown_profit_days": 0, "cooldown_loss_days": 0},
    # 超低频交易
    {"min_score": 0.0, "no_stop_loss": True, "take_profit_pct": 1000,
     "min_consensus": 3, "max_holdings": 5, "kelly_cap": 0.30,
     "min_holding_days": 180, "max_yearly_trades": 10,
     "cooldown_profit_days": 30, "cooldown_loss_days": 90},
    # 最大金字塔
    {"min_score": 0.0, "pyramiding_enabled": True,
     "no_stop_loss": True, "take_profit_pct": 1000,
     "min_consensus": 1, "max_holdings": 3, "kelly_cap": 0.40,
     "max_position_pct": 50, "cash_reserve_pct": 0.0},
    # 移动止盈极端
    {"min_score": 0.0, "no_stop_loss": True, "take_profit_pct": 1000,
     "trailing_tp_activate": 5, "trailing_tp_drawdown": 3,
     "min_consensus": 2, "max_holdings": 5, "kelly_cap": 0.25},
    # 移动止盈宽松
    {"min_score": 0.0, "no_stop_loss": True, "take_profit_pct": 1000,
     "trailing_tp_activate": 50, "trailing_tp_drawdown": 20,
     "min_consensus": 2, "max_holdings": 5, "kelly_cap": 0.25},
    # 组合风控极端
    {"min_score": 0.0, "no_stop_loss": True, "take_profit_pct": 1000,
     "portfolio_dd_breaker": 8, "portfolio_dd_pause_days": 15,
     "min_consensus": 2, "max_holdings": 5, "kelly_cap": 0.25},
    # 组合风控宽松
    {"min_score": 0.0, "no_stop_loss": True, "take_profit_pct": 1000,
     "portfolio_dd_breaker": 30, "portfolio_dd_pause_days": 3,
     "min_consensus": 2, "max_holdings": 5, "kelly_cap": 0.25},
    # 定投+全功能
    {"min_score": 0.0, "no_stop_loss": True, "take_profit_pct": 1000,
     "monthly_injection": 5000, "max_holdings": 3, "kelly_cap": 0.35,
     "pyramiding_enabled": True, "trailing_tp_activate": 20, "trailing_tp_drawdown": 10,
     "regime_specific": True, "kelly_cap_bull": 0.35, "kelly_cap_bear": 0.15,
     "kelly_cap_neutral": 0.25, "min_consensus": 2},
    # 定投+保守
    {"min_score": 0.0, "no_stop_loss": False, "stop_loss_pct": -10, "take_profit_pct": 30,
     "monthly_injection": 2000, "max_holdings": 3, "kelly_cap": 0.15,
     "min_holding_days": 90, "slippage_pct": 0.5, "min_consensus": 3},
    # 全技术指标
    {"min_score": 0.0, "no_stop_loss": False, "stop_loss_pct": -20, "take_profit_pct": 1000,
     "weekly_macd_divergence": True, "weekly_bollinger_adjust": True, "yearly_ma_filter": True,
     "kdj_sell_mode": "death_cross", "vol_spike_mult": 3.0,
     "max_holdings": 5, "kelly_cap": 0.25, "min_consensus": 2},
    # 市场预测+组合风控+行情
    {"min_score": 0.0, "regime_specific": True,
     "market_predictor": True, "predictor_prob_threshold": 0.6,
     "lgb_predictor": True, "lgb_buy_stop_threshold": 0.7,
     "portfolio_dd_breaker": 15, "portfolio_dd_pause_days": 5,
     "no_stop_loss": True, "take_profit_pct": 1000,
     "max_holdings": 5, "kelly_cap": 0.25, "min_consensus": 2},
    # 阶梯止盈+金字塔+行情
    {"min_score": 0.0, "regime_specific": True,
     "step_take_profit": True, "pyramiding_enabled": True,
     "no_stop_loss": True, "take_profit_pct": 1000,
     "kelly_cap_bull": 0.30, "kelly_cap_bear": 0.15, "kelly_cap_neutral": 0.25,
     "max_holdings": 8, "min_consensus": 2},
    # 动量+技术+风控
    {"min_score": 0.0, "signal_source": "momentum",
     "momentum_lookback": 63, "momentum_top_n": 10, "momentum_rebalance_days": 21,
     "no_stop_loss": False, "stop_loss_pct": -15, "take_profit_pct": 50,
     "trailing_tp_activate": 15, "trailing_tp_drawdown": 8,
     "portfolio_dd_breaker": 12, "portfolio_dd_pause_days": 5,
     "max_holdings": 10, "kelly_cap": 0.20},
    # 净信号+加权+移动止盈+分散
    {"min_score": 0.0, "use_weighted_consensus": True, "adaptive_consensus": True,
     "net_signal": True, "net_signal_diff": 2, "sell_consensus": 2,
     "no_stop_loss": True, "take_profit_pct": 1000,
     "trailing_tp_activate": 20, "trailing_tp_drawdown": 10,
     "max_correlation": 0.5, "max_sector_pct": 40,
     "max_holdings": 8, "kelly_cap": 0.25, "min_consensus": 2},
    # 定投+技术+行情+风控
    {"min_score": 0.0, "regime_specific": True,
     "monthly_injection": 3000,
     "weekly_macd_divergence": True, "yearly_ma_filter": True,
     "portfolio_dd_breaker": 15, "portfolio_dd_pause_days": 5,
     "no_stop_loss": True, "take_profit_pct": 1000,
     "kelly_cap_bull": 0.30, "kelly_cap_bear": 0.15, "kelly_cap_neutral": 0.25,
     "max_holdings": 5, "min_consensus": 2, "slippage_pct": 0.3},
]
for i, ajc in enumerate(aj_combos):
    name = f"AJ_ext{i+1}"
    configs.append({"name": name, "desc": f"极端组合{i+1}", "config": ajc})

# ═══ AK: 多维网格（consensus × kelly × holdings）═══
# 系统性扫描三个核心参数的交叉组合
for mc in [1, 2, 3]:
    for kc in [0, 0.15, 0.25, 0.35]:
        for mh in [0, 5, 10]:
            if mc == 2 and kc == 0 and mh == 0:
                continue  # 已在A类覆盖
            name = f"AK_mc{mc}_kc{kc}_mh{mh}"
            cfg = deepcopy(J_BASE)
            cfg["min_score"] = 0.0
            cfg["min_consensus"] = mc
            cfg["kelly_cap"] = kc
            cfg["max_holdings"] = mh
            configs.append({"name": name, "desc": f"网格 mc={mc} kc={kc} mh={mh}", "config": cfg})

# ═══ 统一注入候选数上限（防止mc=1策略评分爆炸）═══
for c in configs:
    if "max_candidates_per_day" not in c["config"]:
        c["config"]["max_candidates_per_day"] = 0  # 不限制（有跨策略评分缓存）

# ═══ AL: 评分权重变体（quality/cost/manager/momentum/smart_money）═══
# 缓存重构后各维度独立分数跨策略共享，仅加权总分不同 → 零额外计算成本
# 基线权重: Q25 C20 M20 Mo15 SM20（硬编码默认值）
al_weights = [
    ("balanced",     {"quality": 20, "cost": 20, "manager": 20, "momentum": 20, "smart_money": 20}, "等权"),
    ("mom_heavy",    {"quality": 15, "cost": 15, "manager": 10, "momentum": 35, "smart_money": 25}, "动量主导"),
    ("sm_heavy",     {"quality": 20, "cost": 15, "manager": 10, "momentum": 15, "smart_money": 40}, "聪明钱主导"),
    ("qual_heavy",   {"quality": 40, "cost": 20, "manager": 15, "momentum": 10, "smart_money": 15}, "质量主导"),
    ("cost_heavy",   {"quality": 25, "cost": 30, "manager": 15, "momentum": 10, "smart_money": 20}, "成本主导"),
    ("mgr_heavy",    {"quality": 20, "cost": 15, "manager": 35, "momentum": 15, "smart_money": 15}, "经理主导"),
    ("mom_sm",       {"quality": 15, "cost": 10, "manager": 5,  "momentum": 30, "smart_money": 40}, "动量+聪明钱"),
    ("qual_cost",    {"quality": 35, "cost": 30, "manager": 10, "momentum": 10, "smart_money": 15}, "质量+成本"),
    ("anti_mom",     {"quality": 30, "cost": 20, "manager": 20, "momentum": 5,  "smart_money": 25}, "弱动量"),
    ("sm_qual",      {"quality": 30, "cost": 15, "manager": 15, "momentum": 10, "smart_money": 30}, "聪明钱+质量"),
    # min_score=0 变体（纯信号驱动+不同权重）
    ("balanced_m0",  {"quality": 20, "cost": 20, "manager": 20, "momentum": 20, "smart_money": 20}, "等权+纯信号"),
    ("sm_heavy_m0",  {"quality": 20, "cost": 15, "manager": 10, "momentum": 15, "smart_money": 40}, "聪明钱主导+纯信号"),
]
for wname, w, desc in al_weights:
    cfg = deepcopy(J_BASE)
    cfg["weights"] = w
    if wname.endswith("_m0"):
        cfg["min_score"] = 0.0
    configs.append({"name": f"AL_{wname}", "desc": f"权重变体:{desc}", "config": cfg})

# ═══ 去重 ═══
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
    # 提取类别前缀（支持1-2个字母）
    name = c["name"]
    cat = ""
    for ch in name:
        if ch.isalpha():
            cat += ch
        else:
            break
    categories[cat] = categories.get(cat, 0) + 1
print("\n分类统计:")
for cat in sorted(categories.keys()):
    print(f"  {cat}: {categories[cat]}个")
print(f"\n  总计: {sum(categories.values())}个")
