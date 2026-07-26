#!/usr/bin/env python3
"""
V4 策略扫描配置生成器（全面覆盖版）

在 bug 修复后的冠军策略基础上，系统覆盖引擎全部已实现参数。

V3 已测(412个): 止盈/止损/移动止盈/kelly_cap/阶梯止盈/peak_dd/trailing_stop 及其组合
V4 新增覆盖: 卖出策略(13种)/买入过滤(10种)/风控(5种)/仓位管理(6种)/
            成本频率(5种)/动态参数(5种)/市场择时(3种)/结构参数(5种)/
            评分权重(12种) + 精选组合

总计约 600+ 策略，覆盖引擎全部参数维度。
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
# 第0组: 基线（bug修复后冠军策略）
# ═══════════════════════════════════════════════════════════
add("V4_A0_baseline", {})

# ═══════════════════════════════════════════════════════════
# 第1组: V3核心参数继承（精选Top，不全量重复）
# ═══════════════════════════════════════════════════════════
# 止盈精选
for tp in [10, 15, 20, 25, 30, 40, 50]:
    add(f"V4_B1_tp{tp}", {"take_profit_pct": tp, "profit_mode": "half"})
# 止损精选
for sl in [-10, -15, -20, -25]:
    add(f"V4_B2_sl{abs(sl)}", {"no_stop_loss": False, "stop_loss_pct": sl})
# 止盈+止损组合精选
for sl in [-10, -15, -20]:
    for tp in [15, 20, 30]:
        add(f"V4_B3_sl{abs(sl)}_tp{tp}", {"no_stop_loss": False, "stop_loss_pct": sl, "take_profit_pct": tp})
# 移动止盈精选
for act, dd in [(5,3), (8,5), (10,5), (10,8), (15,10), (20,12)]:
    add(f"V4_B4_trail{act}_{dd}", {"trailing_tp_activate": act, "trailing_tp_drawdown": dd, "take_profit_pct": 1000})
# kelly_cap精选
for kc in [0.15, 0.20, 0.25, 0.30, 0.40, 0.50]:
    add(f"V4_B5_kc{kc}", {"kelly_cap": kc})
# 阶梯止盈精选
for i, levels in enumerate([[[5,0.3],[10,0.3],[20,0.4]], [[10,0.3],[20,0.3],[30,0.4]], [[10,0.5],[20,0.3],[30,0.2]], [[15,0.3],[30,0.3],[50,0.4]]]):
    add(f"V4_B6_step_v{i+1}", {"step_take_profit": True, "step_tp_levels": levels, "take_profit_pct": 1000})
# peak_dd精选
for pdd in [8, 10, 12, 15, 20]:
    add(f"V4_B7_peakdd{pdd}", {"peak_drawdown_exit": pdd, "take_profit_pct": 1000})
# trailing_stop精选
for ts in [8, 10, 12, 15, 20]:
    add(f"V4_B8_trailstop{ts}", {"trailing_stop_pct": ts, "take_profit_pct": 1000})

# ═══════════════════════════════════════════════════════════
# 第2组: 卖出策略（V3完全没测，13种×多参数）
# ═══════════════════════════════════════════════════════════

# 2.1 动量崩溃卖出
for ms in [1.0, 1.5, 2.0, 2.5, 3.0]:
    add(f"V4_C1_momsell{ms}", {"momentum_sell": ms})

# 2.2 动量崩溃+调整
for adj in [0.2, 0.3, 0.5]:
    add(f"V4_C2_momadj{adj}", {"momentum_sell": 2.0, "momentum_sell_adjust": adj})

# 2.3 大佬卖出信号
for sc in [2, 3, 4, 5]:
    add(f"V4_C3_sellcons{sc}", {"sell_consensus": sc})

# 2.4 KDJ死叉卖出
add("V4_C4_kdj_death", {"kdj_sell_mode": "death_cross"})
add("V4_C4_kdj_overbought", {"kdj_sell_mode": "overbought_exit"})

# 2.5 动量加速卖出
add("V4_C5_maccel_sell", {"maccel_sell": True})

# 2.6 RSI超买卖出
for rsi in [65, 70, 75, 80]:
    add(f"V4_C6_rsisell{rsi}", {"rsi_sell_threshold": rsi})

# 2.7 N日不创新高卖出
for days in [10, 15, 20, 30]:
    add(f"V4_C7_nohigh{days}", {"no_new_high_days": days})

# 2.8 均线死叉卖出
add("V4_C8_ma_death", {"ma_death_cross_sell": True})

# 2.9 时间止损
for days in [30, 60, 90, 120]:
    for min_profit in [0, 5, 10]:
        add(f"V4_C9_tstop{days}_p{min_profit}", {"time_stop_days": days, "time_stop_min_profit": min_profit})

# 2.10 盈利保护卖出（浮亏>10%且持有N天）
for days in [15, 30, 60]:
    add(f"V4_C10_losshold{days}", {"loss_hold_days": days})

# 2.11 动态移动止盈
add("V4_C11_tptrail_dyn", {"tp_trail_dynamic": True})

# 2.12 动量衰退卖出
for days in [5, 10, 15]:
    add(f"V4_C12_momdecay{days}", {"mom_decay_days": days})

# 2.13 MA50趋势破位卖出
add("V4_C13_ma50_exit", {"ma50_trend_exit": True})

# 2.14 波动率突增卖出
for mult in [2.0, 2.5, 3.0]:
    add(f"V4_C14_volspike{mult}", {"vol_spike_mult": mult})

# 2.15 ATR动态止损
for mult in [1.5, 2.0, 2.5, 3.0]:
    add(f"V4_C15_atr{mult}", {"atr_stop_loss_mult": mult})

# ═══════════════════════════════════════════════════════════
# 第3组: 买入过滤策略（V3完全没测，10种）
# ═══════════════════════════════════════════════════════════

# 3.1 MA20趋势买入
add("V4_D1_ma20_buy", {"ma20_trend_buy": True})

# 3.2 RSI超卖买入
for rsi in [30, 40, 50]:
    add(f"V4_D2_rsibuy{rsi}", {"rsi_buy_max": rsi})

# 3.3 动量突破买入
for days in [20, 40, 60]:
    add(f"V4_D3_breakout{days}", {"momentum_breakout_days": days})

# 3.4 KDJ买入过滤
add("V4_D4_kdj_block", {"kdj_buy_mode": "block_overbought"})
add("V4_D4_kdj_oversold", {"kdj_buy_mode": "oversold_only"})
add("V4_D4_kdj_golden", {"kdj_buy_mode": "golden_cross"})

# 3.5 MACD金叉买入
add("V4_D5_macd_buy", {"macd_golden_cross_buy": True})

# 3.6 相对强度买入
add("V4_D6_relstr", {"relative_strength_buy": True})

# 3.7 逆向买入（抄底）
for drop in [0.01, 0.02, 0.03]:
    add(f"V4_D7_contrarian{drop}", {"contrarian_buy_drop": drop})

# 3.8 动量加速预警（不买过热基金）
add("V4_D8_maccel_block", {"maccel_block": True})

# 3.9 超买阻塞
add("V4_D9_block_ob", {"block_overbought": True})

# 3.10 下降趋势惩罚
for pen in [0.3, 0.5, 0.8, 1.0]:
    add(f"V4_D10_downtrend{pen}", {"downtrend_penalty": pen})

# 3.11 熊市不买入
add("V4_D11_bear_nobuy", {"bear_no_buy": True})

# ═══════════════════════════════════════════════════════════
# 第4组: 风控策略（V3完全没测，5种）
# ═══════════════════════════════════════════════════════════

# 4.1 组合级回撤熔断
for brk in [10, 12, 15, 20]:
    for pause in [3, 5, 10]:
        add(f"V4_E1_ddbrk{brk}_p{pause}", {"portfolio_dd_breaker": brk, "portfolio_dd_pause_days": pause})

# 4.2 组合级回撤减仓
for thr in [8, 10, 12, 15]:
    for frac in [0.2, 0.3, 0.5]:
        add(f"V4_E2_ddreduce{thr}_f{frac}", {"portfolio_dd_reduce_pct": 1, "portfolio_dd_reduce_threshold": thr, "portfolio_dd_reduce_frac": frac})

# 4.3 季度再平衡
for max_sec in [30, 40, 50]:
    add(f"V4_E3_rebal{max_sec}", {"rebalance": True, "max_sector_pct": max_sec})

# 4.4 相关性过滤
for corr in [0.7, 0.8, 0.9]:
    add(f"V4_E4_corr{corr}", {"max_correlation": corr})

# 4.5 板块集中度限制
for msc in [2, 3, 4]:
    add(f"V4_E5_sector{msc}", {"max_sector_count": msc})

# ═══════════════════════════════════════════════════════════
# 第5组: 仓位管理策略（V3完全没测，6种）
# ═══════════════════════════════════════════════════════════

# 5.1 金字塔补仓
add("V4_F1_pyramid", {"pyramiding_enabled": True})

# 5.2 企稳买回
for rsi in [40, 50, 60]:
    for min_days in [3, 5, 10]:
        add(f"V4_F2_buyback_rsi{rsi}_d{min_days}", {"enable_buy_back": True, "buy_back_rsi_max": rsi, "buy_back_min_days": min_days})

# 5.3 等额分配
add("V4_F3_equal_alloc", {"equal_allocate": True})

# 5.4 凯利分数
for kf in [0.25, 0.5, 0.75, 1.0]:
    add(f"V4_F4_kellyfrac{kf}", {"kelly_fraction": kf})

# 5.5 单次买入上限
for pct in [0.15, 0.20, 0.25, 0.30, 0.40]:
    add(f"V4_F5_maxbuy{pct}", {"max_single_buy_pct": pct})

# 5.6 冷却期
for profit_d in [5, 10, 15]:
    for loss_d in [15, 30, 45]:
        add(f"V4_F6_cool_p{profit_d}_l{loss_d}", {"cooldown_days": profit_d, "cooldown_profit_days": profit_d, "cooldown_loss_days": loss_d})

# ═══════════════════════════════════════════════════════════
# 第6组: 成本与交易频率（V3完全没测，5种）
# ═══════════════════════════════════════════════════════════

# 6.1 滑点模拟
for slip in [0.1, 0.3, 0.5, 1.0]:
    add(f"V4_G1_slip{slip}", {"slippage_pct": slip})

# 6.2 年交易上限
for yt in [20, 30, 40, 50, 80]:
    add(f"V4_G2_yeartrades{yt}", {"max_yearly_trades": yt})

# 6.3 最低持有天数
for hd in [0, 15, 30, 45, 60, 90]:
    add(f"V4_G3_holdays{hd}", {"min_holding_days": hd})

# 6.4 费率惩罚
for cp in [0.3, 0.5, 1.0, 1.5]:
    add(f"V4_G4_costpen{cp}", {"cost_penalty": cp})

# 6.5 限购加分
for lb in [0.3, 0.5, 1.0]:
    add(f"V4_G5_limitboost{lb}", {"limit_boost": lb})

# ═══════════════════════════════════════════════════════════
# 第7组: 动态参数变体（V3完全没测）
# ═══════════════════════════════════════════════════════════

# 7.1 动态持仓数变体
for bull_m, bear_m in [(1.5, 0.6), (2.0, 0.5), (1.2, 0.7), (1.0, 1.0), (2.0, 0.3)]:
    add(f"V4_H1_dynmh_b{bull_m}_s{bear_m}", {"max_holdings_bull_mult": bull_m, "max_holdings_bear_mult": bear_m})

# 7.2 固定持仓数（关闭动态）
for mh in [3, 5, 8, 10, 12, 15]:
    add(f"V4_H2_fixmh{mh}", {"dynamic_max_holdings": False, "max_holdings": mh})

# 7.3 市场状态专属
add("V4_H3_regime", {"regime_specific": True})

# 7.4 动态仓位参数
for bull_pos, bear_pos in [(35, 15), (40, 10), (25, 20), (30, 15)]:
    add(f"V4_H4_dynpos_b{bull_pos}_s{bear_pos}", {"dyn_max_pos_bull": bull_pos, "dyn_max_pos_bear": bear_pos})

# 7.5 现金储备变体
for cr in [0.05, 0.10, 0.15, 0.20, 0.30]:
    add(f"V4_H5_cashres{cr}", {"cash_reserve_pct": cr})

# ═══════════════════════════════════════════════════════════
# 第8组: 市场择时（V3完全没测，3种）
# ═══════════════════════════════════════════════════════════

# 8.1 周线MACD背离
add("V4_I1_macd_div", {"weekly_macd_divergence": True})

# 8.2 周线布林带
add("V4_I2_bollinger", {"weekly_bollinger_adjust": True})

# 8.3 年线过滤
add("V4_I3_yearly_ma", {"yearly_ma_filter": True})

# 8.4 组合择时
add("V4_I4_all_timing", {"weekly_macd_divergence": True, "weekly_bollinger_adjust": True, "yearly_ma_filter": True})

# ═══════════════════════════════════════════════════════════
# 第9组: 结构参数（V3完全没测）
# ═══════════════════════════════════════════════════════════

# 9.1 每月定投
for amt in [500, 1000, 2000]:
    for mh in [8, 12, 15]:
        add(f"V4_J1_inject{amt}_mh{mh}", {"monthly_injection": amt, "max_holdings": mh})

# 9.2 Top-N过滤
for n in [3, 5, 8, 10]:
    add(f"V4_J2_topn{n}", {"top_n": n})

# 9.3 共识优先
add("V4_J3_consprio", {"consensus_priority": True})

# 9.4 共识门槛变体
for mc in [1, 2, 3, 4, 5]:
    add(f"V4_J4_cons{mc}", {"min_consensus": mc})

# 9.5 评分门槛变体
for ms in [0.0, 2.0, 2.5, 3.0, 3.5, 4.0]:
    add(f"V4_J5_minscore{ms}", {"min_score": ms})

# 9.6 QDII+行业限制
for qdii in [30, 50, 70]:
    add(f"V4_J6_qdii{qdii}", {"max_qdii_pct": qdii})

# ═══════════════════════════════════════════════════════════
# 第10组: 评分权重变体（V3完全没测，12种）
# ═══════════════════════════════════════════════════════════
weight_variants = [
    ("equal", {"quality": 20, "cost": 20, "manager": 20, "momentum": 20, "smart_money": 20}),
    ("mom_heavy", {"quality": 15, "cost": 15, "manager": 15, "momentum": 40, "smart_money": 15}),
    ("sm_heavy", {"quality": 15, "cost": 15, "manager": 15, "momentum": 15, "smart_money": 40}),
    ("quality_heavy", {"quality": 40, "cost": 15, "manager": 15, "momentum": 15, "smart_money": 15}),
    ("cost_heavy", {"quality": 15, "cost": 40, "manager": 15, "momentum": 15, "smart_money": 15}),
    ("mgr_heavy", {"quality": 15, "cost": 15, "manager": 40, "momentum": 15, "smart_money": 15}),
    ("mom_sm", {"quality": 15, "cost": 15, "manager": 10, "momentum": 30, "smart_money": 30}),
    ("qual_cost", {"quality": 30, "cost": 30, "manager": 15, "momentum": 10, "smart_money": 15}),
    ("weak_mom", {"quality": 25, "cost": 25, "manager": 25, "momentum": 5, "smart_money": 20}),
    ("sm_qual", {"quality": 30, "cost": 15, "manager": 15, "momentum": 10, "smart_money": 30}),
    ("no_cost", {"quality": 30, "cost": 0, "manager": 25, "momentum": 20, "smart_money": 25}),
    ("no_mgr", {"quality": 30, "cost": 25, "manager": 0, "momentum": 20, "smart_money": 25}),
]
for wname, weights in weight_variants:
    add(f"V4_K1_w_{wname}", {"weights": weights})

# ═══════════════════════════════════════════════════════════
# 第11组: smart_swap参数变体
# ═══════════════════════════════════════════════════════════
for margin in [0.3, 0.5, 1.0, 1.5, 2.0]:
    for min_hold in [15, 30, 60]:
        add(f"V4_L1_swap_m{margin}_h{min_hold}", {"smart_swap_margin": margin, "smart_swap_min_hold_days": min_hold})

# 关闭smart_swap
add("V4_L2_no_swap", {"smart_swap": False})

# ═══════════════════════════════════════════════════════════
# 第12组: 精选组合（最有前途的策略组合）
# ═══════════════════════════════════════════════════════════

# 12.1 止盈+移动止盈+止损三合一
for sl, tp, act, dd in [(-10, 15, 5, 3), (-15, 20, 8, 5), (-15, 20, 10, 5), (-20, 25, 10, 8)]:
    add(f"V4_M1_sl{abs(sl)}_tp{tp}_tr{act}_{dd}", {
        "no_stop_loss": False, "stop_loss_pct": sl,
        "take_profit_pct": tp, "profit_mode": "half",
        "trailing_tp_activate": act, "trailing_tp_drawdown": dd,
    })

# 12.2 止盈+卖出策略组合
for tp, ms, sc in [(15, 2.0, 3), (20, 2.0, 2), (20, 1.5, 3), (25, 2.0, 2)]:
    add(f"V4_M2_tp{tp}_ms{ms}_sc{sc}", {
        "take_profit_pct": tp, "momentum_sell": ms, "sell_consensus": sc,
    })

# 12.3 止盈+RSI卖出+不创新高
for tp, rsi, nh in [(15, 75, 15), (20, 70, 20), (20, 75, 20), (25, 75, 15)]:
    add(f"V4_M3_tp{tp}_rsi{rsi}_nh{nh}", {
        "take_profit_pct": tp, "rsi_sell_threshold": rsi, "no_new_high_days": nh,
    })

# 12.4 止盈+时间止损+ATR
for tp, ts, atr in [(15, 60, 2.0), (20, 90, 2.0), (20, 60, 2.5), (25, 90, 2.0)]:
    add(f"V4_M4_tp{tp}_ts{ts}_atr{atr}", {
        "take_profit_pct": tp, "time_stop_days": ts, "time_stop_min_profit": 5,
        "atr_stop_loss_mult": atr,
    })

# 12.5 止盈+风控组合
for tp, brk, rebal in [(15, 15, 40), (20, 12, 40), (20, 15, 50), (25, 15, 40)]:
    add(f"V4_M5_tp{tp}_brk{brk}_rebal{rebal}", {
        "take_profit_pct": tp, "portfolio_dd_breaker": brk,
        "rebalance": True, "max_sector_pct": rebal,
    })

# 12.6 止盈+金字塔+企稳买回
for tp in [15, 20, 25]:
    add(f"V4_M6_tp{tp}_pyramid_bb", {
        "take_profit_pct": tp, "pyramiding_enabled": True,
        "enable_buy_back": True, "buy_back_rsi_max": 50, "buy_back_min_days": 5,
    })

# 12.7 买入过滤+止盈组合
for tp in [15, 20, 25]:
    add(f"V4_M7_tp{tp}_ma20_macd", {
        "take_profit_pct": tp, "ma20_trend_buy": True, "macd_golden_cross_buy": True,
    })

# 12.8 全能防御型（止损+止盈+移动止盈+RSI卖出+不创新高+冷却）
add("V4_M8_defensive", {
    "no_stop_loss": False, "stop_loss_pct": -15,
    "take_profit_pct": 20, "profit_mode": "half",
    "trailing_tp_activate": 10, "trailing_tp_drawdown": 5,
    "rsi_sell_threshold": 75, "no_new_high_days": 20,
    "cooldown_days": 10, "cooldown_profit_days": 10, "cooldown_loss_days": 30,
})

# 12.9 全能进攻型（止盈+移动止盈+smart_swap+金字塔+动态持仓）
add("V4_M9_aggressive", {
    "take_profit_pct": 25, "profit_mode": "half",
    "trailing_tp_activate": 15, "trailing_tp_drawdown": 8,
    "smart_swap": True, "smart_swap_margin": 0.5,
    "pyramiding_enabled": True,
    "dynamic_max_holdings": True, "max_holdings_bull_mult": 2.0, "max_holdings_bear_mult": 0.5,
    "kelly_cap": 0.40,
})

# 12.10 均衡型（止盈+止损+移动止盈+风控+再平衡+冷却）
add("V4_M10_balanced", {
    "no_stop_loss": False, "stop_loss_pct": -15,
    "take_profit_pct": 20, "profit_mode": "half",
    "trailing_tp_activate": 8, "trailing_tp_drawdown": 5,
    "portfolio_dd_breaker": 15, "portfolio_dd_pause_days": 5,
    "rebalance": True, "max_sector_pct": 40,
    "cooldown_days": 10, "cooldown_profit_days": 7, "cooldown_loss_days": 20,
    "kelly_cap": 0.30,
})

# 12.11 买入持有+止盈+卖出策略组合
for tp in [20, 30, 40]:
    add(f"V4_M11_bh_tp{tp}_sell", {
        "take_profit_pct": tp, "momentum_sell": 2.0,
        "sell_consensus": 3, "time_stop_days": 90, "time_stop_min_profit": 5,
    })

# 12.12 评分权重+止盈组合
for tp, wname, weights in [(15, "sm_heavy", {"quality": 15, "cost": 15, "manager": 15, "momentum": 15, "smart_money": 40}),
                            (20, "mom_sm", {"quality": 15, "cost": 15, "manager": 10, "momentum": 30, "smart_money": 30}),
                            (20, "qual_cost", {"quality": 30, "cost": 30, "manager": 15, "momentum": 10, "smart_money": 15})]:
    add(f"V4_M12_tp{tp}_w_{wname}", {
        "take_profit_pct": tp, "weights": weights,
    })

# ═══════════════════════════════════════════════════════════
# 第13组: 定投+止盈（常见场景）
# ═══════════════════════════════════════════════════════════
for inj, tp in [(1000, 15), (1000, 20), (2000, 15), (2000, 20), (1000, 25)]:
    add(f"V4_N1_inject{inj}_tp{tp}", {"monthly_injection": inj, "take_profit_pct": tp})

# 定投+止盈+止损
for inj, tp, sl in [(1000, 20, -15), (2000, 20, -15), (1000, 15, -10)]:
    add(f"V4_N2_inject{inj}_tp{tp}_sl{abs(sl)}", {
        "monthly_injection": inj, "take_profit_pct": tp,
        "no_stop_loss": False, "stop_loss_pct": sl,
    })

# ═══════════════════════════════════════════════════════════
# 输出
# ═══════════════════════════════════════════════════════════
OUTPUT = Path(__file__).resolve().parent / "v4_sweep_configs.json"
with open(OUTPUT, "w", encoding="utf-8") as f:
    json.dump(STRATEGIES, f, ensure_ascii=False, indent=2)

print(f"Generated {len(STRATEGIES)} V4 sweep configs")
print(f"Output: {OUTPUT}")

groups = {}
for s in STRATEGIES:
    parts = s["name"].split("_")
    g = parts[1] if len(parts) > 1 else "?"
    groups[g] = groups.get(g, 0) + 1
for g in sorted(groups):
    print(f"  {g}组: {groups[g]}个")
