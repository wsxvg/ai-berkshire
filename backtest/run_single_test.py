#!/usr/bin/env python3
"""单测试运行脚本 — 供GitHub Actions调用

用法: python backtest/run_single_test.py <test_name>
结果: 写入 backtest/results/<test_name>.json
"""
import sys, json, copy, time, os

# 所有测试配置
TEST_CONFIGS = {
    # 基线
    "baseline": {},
    # 方案A
    "A1_macd_div": {"weekly_macd_divergence": True, "divergence_top_discount": 0.6},
    "A2_bollinger": {"weekly_bollinger_adjust": True},
    "A3_yearly_ma": {"yearly_ma_filter": True},
    "A4_rsi70": {"block_overbought": True},
    "A5_all_combined": {"weekly_macd_divergence": True, "weekly_bollinger_adjust": True, "yearly_ma_filter": True, "block_overbought": True},
    # 方案B
    "B1_risk60": {"market_risk_filter": True, "market_risk_threshold": 60, "market_risk_caution": 30},
    "B2_risk50": {"market_risk_filter": True, "market_risk_threshold": 50, "market_risk_caution": 20},
    "B3_risk40": {"market_risk_filter": True, "market_risk_threshold": 40, "market_risk_caution": 20},
    # 方案C
    "C1_predictor60": {"market_predictor": True, "predictor_prob_threshold": 0.6, "predictor_retrain_days": 20},
    "C2_predictor55": {"market_predictor": True, "predictor_prob_threshold": 0.55, "predictor_retrain_days": 20},
    # OpenClaw
    "OC_time_stop120": {"time_stop_days": 120, "time_stop_min_profit": 5},
    "OC_rsi_sell80": {"rsi_sell_threshold": 80, "rsi_sell_pct": 0.3},
    "OC_no_new_high20": {"no_new_high_days": 20},
    "OC_ma_cross": {"ma_death_cross_sell": True},
    "OC_dd_breaker12": {"portfolio_dd_breaker": 12, "portfolio_dd_pause_days": 5},
    # 方案D：新策略
    "D1_step_tp": {"step_take_profit": True},
    "D2_atr_stop": {"atr_stop_loss_mult": 2.0},
    "D3_macd_buy": {"macd_golden_cross_buy": True},
    "D4_dyn_kelly": {"market_risk_filter": True, "market_risk_threshold": 60, "market_risk_caution": 30, "kelly_fraction": 0.5},
    # 混合组合
    "E1_A5_B1": {"weekly_macd_divergence": True, "weekly_bollinger_adjust": True, "yearly_ma_filter": True, "block_overbought": True, "market_risk_filter": True, "market_risk_threshold": 60, "market_risk_caution": 30},
    "E2_A5_C1": {"weekly_macd_divergence": True, "weekly_bollinger_adjust": True, "yearly_ma_filter": True, "block_overbought": True, "market_predictor": True, "predictor_prob_threshold": 0.6},
    "E3_B1_C1": {"market_risk_filter": True, "market_risk_threshold": 60, "market_risk_caution": 30, "market_predictor": True, "predictor_prob_threshold": 0.6},
    "E4_all": {"weekly_macd_divergence": True, "weekly_bollinger_adjust": True, "yearly_ma_filter": True, "block_overbought": True, "market_risk_filter": True, "market_risk_threshold": 60, "market_risk_caution": 30, "market_predictor": True, "predictor_prob_threshold": 0.6},
    # 参数扫描
    "F1_rsi65": {"block_overbought": True, "rsi_block_threshold": 65},
    "F2_rsi75": {"block_overbought": True, "rsi_block_threshold": 75},
    "F3_tp40": {"take_profit_pct": 40},
    "F4_tp60": {"take_profit_pct": 60},
    "F5_trail5": {"trailing_tp_activate": 20, "trailing_tp_drawdown": 5},
    "F6_trail12": {"trailing_tp_activate": 20, "trailing_tp_drawdown": 12},
    "F7_sector30": {"rebalance": True, "max_sector_pct": 30},
    # D2 + B1 组合
    "G1_atr_risk": {"atr_stop_loss_mult": 2.0, "market_risk_filter": True, "market_risk_threshold": 50, "market_risk_caution": 30},
    # D1 + D2 组合
    "G2_step_atr": {"step_take_profit": True, "atr_stop_loss_mult": 2.0},
    # 全部组合（所有策略全开）
    "H1_all_in": {"step_take_profit": True, "atr_stop_loss_mult": 2.0, "macd_golden_cross_buy": True, "market_risk_filter": True, "market_risk_threshold": 50, "market_risk_caution": 30, "weekly_macd_divergence": True, "weekly_bollinger_adjust": True, "yearly_ma_filter": True, "block_overbought": True},
    # 方案I：新买入过滤
    "I1_ma20_buy": {"ma20_trend_buy": True},
    "I2_rsi_oversold": {"rsi_buy_max": 40},
    "I3_breakout60": {"momentum_breakout_days": 60},
    # 方案J：参数变体
    "J1_stop15": {"stop_loss_pct": -15},
    "J2_stop50": {"stop_loss_pct": -50},
    "J3_score4": {"min_score": 4.0},
    "J4_consensus1": {"min_consensus": 1},
    "J5_consensus3": {"min_consensus": 3},
    "J6_maxpos50": {"max_position_pct": 50},
    "J7_cash3": {"cash_reserve_pct": 0.03},
    "J8_nostop": {"no_stop_loss": True},
    "J9_hold60": {"min_holding_days": 60},
    "J10_hold15": {"min_holding_days": 15},
    # 方案K：组合策略
    "K1_value_trend": {"min_score": 4.0, "ma20_trend_buy": True},
    "K2_event_v2": {"ma20_trend_buy": True, "stop_loss_pct": -15},
    "K3_all_buy_filters": {"ma20_trend_buy": True, "macd_golden_cross_buy": True, "momentum_breakout_days": 60},
    # 方案S：卖出优化（全新方向）
    "S1_mom_adj": {"momentum_sell": 1.5, "momentum_sell_adjust": 0.3},
    "S2_loss_hold30": {"loss_hold_days": 30},
    "S2b_loss_hold15": {"loss_hold_days": 15},
    "S3_tp_trail_dyn": {"tp_trail_dynamic": True},
    "S4_mom_decay5": {"mom_decay_days": 5},
    "S4b_mom_decay10": {"mom_decay_days": 10},
    # 卖出组合
    "S5_mom_adj_trail": {"momentum_sell": 1.5, "momentum_sell_adjust": 0.3, "tp_trail_dynamic": True},
    "S6_trail_atr": {"tp_trail_dynamic": True, "atr_stop_loss_mult": 2.0},
    "S7_mom_adj_decay": {"momentum_sell": 1.5, "momentum_sell_adjust": 0.3, "mom_decay_days": 5},
    # profit_mode变体
    "S8_profit_all": {"take_profit_pct": 80, "profit_mode": "all"},
    "S9_profit_quarter": {"take_profit_pct": 30, "profit_mode": "quarter"},
    "S10_no_mom_crash": {"momentum_sell": 0.0},  # 完全禁用动量崩溃卖出
    "S11_mom_crash_bull": {"momentum_sell": 1.5},  # 牛市也触发（去掉market_state!=bull条件）
    # trailing_tp激活
    "S12_trail_act15": {"trailing_tp_activate": 15, "trailing_tp_drawdown": 10},
    "S13_trail_act30": {"trailing_tp_activate": 30, "trailing_tp_drawdown": 8},
    "S14_trail_act10_dd5": {"trailing_tp_activate": 10, "trailing_tp_drawdown": 5},
    # 组合：动量调整+移动止盈+宽松止盈
    "S15_combo": {"momentum_sell": 1.5, "momentum_sell_adjust": 0.3, "tp_trail_dynamic": True, "trailing_tp_activate": 20, "trailing_tp_drawdown": 8},
    # 方案T：大跌预测+清仓逃跑（Transformer改良版）
    "T1_crash5_sell70": {"market_predictor": True, "predictor_crash_threshold": -0.05, "predictor_sell_threshold": 0.7, "predictor_retrain_days": 20},
    "T2_crash3_sell70": {"market_predictor": True, "predictor_crash_threshold": -0.03, "predictor_sell_threshold": 0.7, "predictor_retrain_days": 20},
    "T3_crash5_sell60": {"market_predictor": True, "predictor_crash_threshold": -0.05, "predictor_sell_threshold": 0.6, "predictor_retrain_days": 20},
    "T4_crash10_sell80": {"market_predictor": True, "predictor_crash_threshold": -0.10, "predictor_sell_threshold": 0.8, "predictor_retrain_days": 20},
    # 方案U：新卖出策略
    "U1_ma50_exit": {"ma50_trend_exit": True},
    "U2_vol_spike2": {"vol_spike_mult": 2.0},
    "U2b_vol_spike3": {"vol_spike_mult": 3.0},
    "U3_port_dd10": {"portfolio_dd_reduce_pct": 1, "portfolio_dd_reduce_threshold": 10, "portfolio_dd_reduce_frac": 0.3},
    "U3b_port_dd15": {"portfolio_dd_reduce_pct": 1, "portfolio_dd_reduce_threshold": 15, "portfolio_dd_reduce_frac": 0.3},
    # 方案U买入策略
    "U4_rel_strength": {"relative_strength_buy": True},
    "U5_contrarian2": {"contrarian_buy_drop": 0.02},
    "U5b_contrarian3": {"contrarian_buy_drop": 0.03},
    # 方案V：LightGBM预测（CPU秒级）
    "V1_lgb_crash5_sell70": {"lgb_predictor": True, "lgb_crash_threshold": -0.05, "lgb_sell_threshold": 0.7, "lgb_buy_stop_threshold": 0.6},
    "V2_lgb_crash3_sell60": {"lgb_predictor": True, "lgb_crash_threshold": -0.03, "lgb_sell_threshold": 0.6, "lgb_buy_stop_threshold": 0.5},
    "V3_lgb_crash5_sell60": {"lgb_predictor": True, "lgb_crash_threshold": -0.05, "lgb_sell_threshold": 0.6, "lgb_buy_stop_threshold": 0.5},
    "V4_lgb_crash10_sell80": {"lgb_predictor": True, "lgb_crash_threshold": -0.10, "lgb_sell_threshold": 0.8, "lgb_buy_stop_threshold": 0.7},
    # 方案W：组合结构
    "W1_maxhold5": {"max_holdings": 5},
    "W2_maxhold10": {"max_holdings": 10},
    "W3_maxhold15": {"max_holdings": 15},
    "W4_pyramid": {"pyramiding_enabled": True},
    # 方案X：组合策略
    "X1_ma50_portdd": {"ma50_trend_exit": True, "portfolio_dd_reduce_pct": 1, "portfolio_dd_reduce_threshold": 10, "portfolio_dd_reduce_frac": 0.3},
    "X2_volspike_relstr": {"vol_spike_mult": 2.0, "relative_strength_buy": True},
    "X3_lgb_ma50": {"lgb_predictor": True, "lgb_crash_threshold": -0.05, "lgb_sell_threshold": 0.7, "ma50_trend_exit": True},
    # 方案Y：大佬排名与信号机制（从未优化"跟谁买"的核心逻辑）
    "Y1_dynrank": {"dynamic_ranking": True},
    "Y2_dynrank_w60": {"dynamic_ranking": True, "ranking_window": 60},
    "Y3_dynrank_w180": {"dynamic_ranking": True, "ranking_window": 180},
    "Y4_dynrank_hl30": {"dynamic_ranking": True, "ranking_half_life": 30},
    "Y5_weighted": {"use_weighted_consensus": True},
    "Y6_net_signal": {"net_signal": True},
    "Y7_dynrank_weighted": {"dynamic_ranking": True, "use_weighted_consensus": True},
    "Y8_dynrank_netsig": {"dynamic_ranking": True, "net_signal": True},
    # 方案Z：市场择时与仓位自适应（核心择时参数从未测过）
    "Z1_bear_nobuy": {"bear_market_no_buy": True},
    "Z2_dyn_maxpos": {"dyn_max_pos_bull": 35, "dyn_max_pos_neutral": 25, "dyn_max_pos_bear": 15},
    "Z3_dyn_maxpos_cash": {"dyn_max_pos_bull": 35, "dyn_max_pos_neutral": 25, "dyn_max_pos_bear": 15, "dyn_cash_reserve_bull": 0.10, "dyn_cash_reserve_neutral": 0.20, "dyn_cash_reserve_bear": 0.40},
    "Z4_no_timing": {"timing_filter": False},
    "Z5_no_overbought": {"block_overbought": False},
    # 方案AA：持有期与交易成本（持有期只测过60/15，成本从未测过）
    "AA1_hold30": {"min_holding_days": 30},
    "AA2_hold90": {"min_holding_days": 90},
    "AA3_hold120": {"min_holding_days": 120},
    "AA4_slip05": {"slippage_pct": 0.5},
    "AA5_slip10": {"slippage_pct": 1.0},
    # 方案AB：卖出信号与选股范围（卖出共识/选股过滤从未测过）
    "AB1_sellcons2": {"sell_consensus": 2},
    "AB2_sellcons3": {"sell_consensus": 3},
    "AB3_topn5": {"top_n": 5},
    "AB4_topn10": {"top_n": 10},
    "AB5_consprio": {"consensus_priority": True},
    "AB6_costpen": {"cost_penalty": 1.0},
    "AB7_limitboost": {"limit_boost": 0.5},
    # 方案AC：资金管理与配置开关（定投/动态止损/行情自适应从未测过）
    "AC1_inject1k": {"monthly_injection": 1000},
    "AC2_inject5k": {"monthly_injection": 5000},
    "AC3_nodynsl": {"dynamic_stop_loss": False},
    "AC4_noregime": {"regime_specific": False},
    "AC5_qdii50": {"max_qdii_pct": 50},
    # 方案AD：评分惩罚（下跌趋势惩罚系数从未扫描）
    "AD1_nopenalty": {"downtrend_penalty": 0.0},
    "AD2_pen03": {"downtrend_penalty": 0.3},
    "AD3_pen10": {"downtrend_penalty": 1.0},
    # 方案AE：组合策略（最有潜力的新方向组合）
    "AE1_bear_dynpos": {"bear_market_no_buy": True, "dyn_max_pos_bull": 35, "dyn_max_pos_neutral": 25, "dyn_max_pos_bear": 15},
    "AE2_dynrank_netsig_w": {"dynamic_ranking": True, "net_signal": True, "use_weighted_consensus": True},
    "AE3_sellcons_dynrank": {"sell_consensus": 2, "dynamic_ranking": True},
    "AE4_topn_consprio": {"top_n": 10, "consensus_priority": True},
    # ═══ 方案BA：加权共识深挖（Y5=58.94%基线，探索权重门槛） ═══
    "BA1_w_cons1": {"use_weighted_consensus": True, "min_consensus": 1},
    "BA2_w_cons3": {"use_weighted_consensus": True, "min_consensus": 3},
    "BA3_w_cons4": {"use_weighted_consensus": True, "min_consensus": 4},
    "BA4_w_thr15": {"use_weighted_consensus": True, "weighted_consensus_threshold": 1.5},
    "BA5_w_thr20": {"use_weighted_consensus": True, "weighted_consensus_threshold": 2.0},
    "BA6_w_thr25": {"use_weighted_consensus": True, "weighted_consensus_threshold": 2.5},
    "BA7_w_thr30": {"use_weighted_consensus": True, "weighted_consensus_threshold": 3.0},
    "BA8_w_thr35": {"use_weighted_consensus": True, "weighted_consensus_threshold": 3.5},
    "BA9_w_adaptive": {"use_weighted_consensus": True, "adaptive_consensus": True},
    "BA10_w_cons2_topn10": {"use_weighted_consensus": True, "min_consensus": 2, "top_n": 10},
    "BA11_w_cons2_consprio": {"use_weighted_consensus": True, "min_consensus": 2, "consensus_priority": True},
    "BA12_w_cons2_maxhold10": {"use_weighted_consensus": True, "min_consensus": 2, "max_holdings": 10},
    # ═══ 方案BB：净信号深挖（Y6=58.08%基线，探索净信号强度） ═══
    "BB1_net_ratio15": {"net_signal": True, "net_signal_ratio": 1.5},
    "BB2_net_ratio2": {"net_signal": True, "net_signal_ratio": 2.0},
    "BB3_net_ratio3": {"net_signal": True, "net_signal_ratio": 3.0},
    "BB4_net_diff2": {"net_signal": True, "net_signal_diff": 2},
    "BB5_net_diff3": {"net_signal": True, "net_signal_diff": 3},
    "BB6_net_diff4": {"net_signal": True, "net_signal_diff": 4},
    "BB7_net_cons1": {"net_signal": True, "min_consensus": 1},
    "BB8_net_cons3": {"net_signal": True, "min_consensus": 3},
    "BB9_net_adaptive": {"net_signal": True, "adaptive_consensus": True},
    "BB10_net_topn10": {"net_signal": True, "top_n": 10},
    "BB11_net_consprio": {"net_signal": True, "consensus_priority": True},
    "BB12_net_maxhold10": {"net_signal": True, "max_holdings": 10},
    # ═══ 方案BC：Y5+Y6组合及变体（最有潜力） ═══
    "BC1_w_net": {"use_weighted_consensus": True, "net_signal": True},
    "BC2_w_net_cons1": {"use_weighted_consensus": True, "net_signal": True, "min_consensus": 1},
    "BC3_w_net_cons3": {"use_weighted_consensus": True, "net_signal": True, "min_consensus": 3},
    "BC4_w_net_thr20": {"use_weighted_consensus": True, "net_signal": True, "weighted_consensus_threshold": 2.0},
    "BC5_w_net_thr25": {"use_weighted_consensus": True, "net_signal": True, "weighted_consensus_threshold": 2.5},
    "BC6_w_net_diff2": {"use_weighted_consensus": True, "net_signal": True, "net_signal_diff": 2},
    "BC7_w_net_ratio2": {"use_weighted_consensus": True, "net_signal": True, "net_signal_ratio": 2.0},
    "BC8_w_net_adaptive": {"use_weighted_consensus": True, "net_signal": True, "adaptive_consensus": True},
    "BC9_w_net_topn10": {"use_weighted_consensus": True, "net_signal": True, "top_n": 10},
    "BC10_w_net_consprio": {"use_weighted_consensus": True, "net_signal": True, "consensus_priority": True},
    "BC11_w_net_maxhold10": {"use_weighted_consensus": True, "net_signal": True, "max_holdings": 10},
    "BC12_w_net_sellcons2": {"use_weighted_consensus": True, "net_signal": True, "sell_consensus": 2},
    # ═══ 方案BD：加权+净信号+评分组合 ═══
    "BD1_w_net_score4": {"use_weighted_consensus": True, "net_signal": True, "min_score": 4.0},
    "BD2_w_net_costpen": {"use_weighted_consensus": True, "net_signal": True, "cost_penalty": 1.0},
    "BD3_w_net_limitboost": {"use_weighted_consensus": True, "net_signal": True, "limit_boost": 0.5},
    "BD4_w_net_qdii50": {"use_weighted_consensus": True, "net_signal": True, "max_qdii_pct": 50},
    "BD5_w_net_corr04": {"use_weighted_consensus": True, "net_signal": True, "max_correlation": 0.4},
    "BD6_w_net_sector30": {"use_weighted_consensus": True, "net_signal": True, "max_sector_pct": 30},
    # ═══ 方案BE：极限组合（Y5+Y6+多个赢家叠加） ═══
    "BE1_w_net_topn_consprio": {"use_weighted_consensus": True, "net_signal": True, "top_n": 10, "consensus_priority": True},
    "BE2_w_net_thr25_diff2": {"use_weighted_consensus": True, "net_signal": True, "weighted_consensus_threshold": 2.5, "net_signal_diff": 2},
    "BE3_w_net_adaptive_consprio": {"use_weighted_consensus": True, "net_signal": True, "adaptive_consensus": True, "consensus_priority": True},
    "BE4_w_net_maxhold10_consprio": {"use_weighted_consensus": True, "net_signal": True, "max_holdings": 10, "consensus_priority": True},
    "BE5_w_net_thr20_adaptive": {"use_weighted_consensus": True, "net_signal": True, "weighted_consensus_threshold": 2.0, "adaptive_consensus": True},
    "BE6_w_net_thr30_diff3": {"use_weighted_consensus": True, "net_signal": True, "weighted_consensus_threshold": 3.0, "net_signal_diff": 3},
    # ═══ 方案FA：KDJ指标买入过滤（听说对基金格外有效） ═══
    "FA1_kdj_block80": {"kdj_buy_mode": "block_overbought", "kdj_overbought_k": 80},
    "FA2_kdj_block70": {"kdj_buy_mode": "block_overbought", "kdj_overbought_k": 70},
    "FA3_kdj_block60": {"kdj_buy_mode": "block_overbought", "kdj_overbought_k": 60},
    "FA4_kdj_oversold": {"kdj_buy_mode": "oversold_only", "kdj_oversold_k": 20},
    "FA5_kdj_oversold30": {"kdj_buy_mode": "oversold_only", "kdj_oversold_k": 30},
    "FA6_kdj_golden": {"kdj_buy_mode": "golden_cross"},
    # KDJ买入 + Y5加权共识组合
    "FA7_w_kdj_block80": {"use_weighted_consensus": True, "kdj_buy_mode": "block_overbought", "kdj_overbought_k": 80},
    "FA8_w_kdj_block70": {"use_weighted_consensus": True, "kdj_buy_mode": "block_overbought", "kdj_overbought_k": 70},
    "FA9_w_kdj_oversold": {"use_weighted_consensus": True, "kdj_buy_mode": "oversold_only", "kdj_oversold_k": 20},
    "FA10_w_kdj_golden": {"use_weighted_consensus": True, "kdj_buy_mode": "golden_cross"},
    # ═══ 方案FB：KDJ指标卖出过滤 ═══
    "FB1_kdj_sell_death": {"kdj_sell_mode": "death_cross"},
    "FB2_kdj_sell_overexit": {"kdj_sell_mode": "overbought_exit"},
    "FB3_w_kdj_sell_death": {"use_weighted_consensus": True, "kdj_sell_mode": "death_cross"},
    "FB4_w_kdj_sell_overexit": {"use_weighted_consensus": True, "kdj_sell_mode": "overbought_exit"},
    # KDJ买卖组合
    "FB5_kdj_buy_block_sell_death": {"kdj_buy_mode": "block_overbought", "kdj_overbought_k": 80, "kdj_sell_mode": "death_cross"},
    "FB6_w_kdj_buy_sell": {"use_weighted_consensus": True, "kdj_buy_mode": "block_overbought", "kdj_overbought_k": 80, "kdj_sell_mode": "overbought_exit"},
    # ═══ 方案FC：动量加速检测（3月涨30%+1月加速不买） ═══
    "FC1_maccel_block": {"maccel_block": True},
    "FC2_maccel_block_20": {"maccel_block": True, "maccel_3m_threshold": 20.0},
    "FC3_maccel_block_40": {"maccel_block": True, "maccel_3m_threshold": 40.0},
    "FC4_maccel_ratio2": {"maccel_block": True, "maccel_ratio": 2.0},
    "FC5_maccel_ratio1": {"maccel_block": True, "maccel_ratio": 1.0},
    # 动量加速卖出
    "FC6_maccel_sell": {"maccel_sell": True},
    "FC7_maccel_sell_20": {"maccel_sell": True, "maccel_3m_threshold": 20.0},
    # 动量加速 + Y5组合
    "FC8_w_maccel_block": {"use_weighted_consensus": True, "maccel_block": True},
    "FC9_w_maccel_block_20": {"use_weighted_consensus": True, "maccel_block": True, "maccel_3m_threshold": 20.0},
    "FC10_w_maccel_sell": {"use_weighted_consensus": True, "maccel_sell": True},
    # ═══ 方案FD：KDJ+动量加速组合 ═══
    "FD1_kdj_maccel": {"kdj_buy_mode": "block_overbought", "kdj_overbought_k": 80, "maccel_block": True},
    "FD2_kdj_maccel_sell": {"kdj_buy_mode": "block_overbought", "kdj_overbought_k": 80, "maccel_sell": True},
    "FD3_w_kdj_maccel": {"use_weighted_consensus": True, "kdj_buy_mode": "block_overbought", "kdj_overbought_k": 80, "maccel_block": True},
    "FD4_w_kdj_maccel_sell": {"use_weighted_consensus": True, "kdj_buy_mode": "block_overbought", "kdj_overbought_k": 80, "maccel_sell": True},
    "FD5_w_kdj_sell_maccel": {"use_weighted_consensus": True, "kdj_sell_mode": "overbought_exit", "maccel_block": True},
    # ═══ 方案FE：三合一极限组合 ═══
    "FE1_w_kdj_maccel_net": {"use_weighted_consensus": True, "net_signal": True, "kdj_buy_mode": "block_overbought", "kdj_overbought_k": 80, "maccel_block": True},
    "FE2_w_kdj_sell_maccel_sell": {"use_weighted_consensus": True, "kdj_sell_mode": "overbought_exit", "maccel_sell": True},
    "FE3_w_kdj_buy_sell_maccel": {"use_weighted_consensus": True, "kdj_buy_mode": "block_overbought", "kdj_overbought_k": 80, "kdj_sell_mode": "overbought_exit", "maccel_block": True},
    "FE4_w_kdj_golden_maccel": {"use_weighted_consensus": True, "kdj_buy_mode": "golden_cross", "maccel_block": True},
}

LABELS = {
    "baseline": "基线",
    "A1_macd_div": "A1:周线MACD顶背离",
    "A2_bollinger": "A2:周线布林带",
    "A3_yearly_ma": "A3:年线过滤",
    "A4_rsi70": "A4:RSI超买70",
    "A5_all_combined": "A5:全部前瞻指标",
    "B1_risk60": "B1:风险>60停买",
    "B2_risk50": "B2:风险>50停买",
    "B3_risk40": "B3:风险>40停买",
    "C1_predictor60": "C1:Transformer P跌>0.6",
    "C2_predictor55": "C2:Transformer P跌>0.55",
    "OC_time_stop120": "OC:时间止损120天",
    "OC_rsi_sell80": "OC:RSI>80卖30%",
    "OC_no_new_high20": "OC:20日不创新高",
    "OC_ma_cross": "OC:MA5下穿MA20",
    "OC_dd_breaker12": "OC:组合回撤12%熔断",
    "D1_step_tp": "D1:阶梯止盈(30/50/80分批)",
    "D2_atr_stop": "D2:ATR动态止损(2×ATR)",
    "D3_macd_buy": "D3:MACD金叉买入过滤",
    "D4_dyn_kelly": "D4:动态凯利(风险分调仓)",
    "E1_A5_B1": "E1:A5+B1(指标+风险)",
    "E2_A5_C1": "E2:A5+C1(指标+Transformer)",
    "E3_B1_C1": "E3:B1+C1(风险+Transformer)",
    "E4_all": "E4:全部组合(A+B+C)",
    "F1_rsi65": "F1:RSI超买65(更严格)",
    "F2_rsi75": "F2:RSI超买75(较宽松)",
    "F3_tp40": "F3:止盈40%(更早)",
    "F4_tp60": "F4:止盈60%(更晚)",
    "F5_trail5": "F5:移动止盈回撤5%(紧)",
    "F6_trail12": "F6:移动止盈回撤12%(松)",
    "F7_sector30": "F7:行业集中度30%",
    "G1_atr_risk": "G1:ATR止损+风险50停买",
    "G2_step_atr": "G2:阶梯止盈+ATR止损",
    "H1_all_in": "H1:全部策略全开",
    "I1_ma20_buy": "I1:MA20趋势买入过滤",
    "I2_rsi_oversold": "I2:RSI<40超卖买入",
    "I3_breakout60": "I3:60日新高突破买入",
    "J1_stop15": "J1:紧止损15%(事件驱动V2)",
    "J2_stop50": "J2:松止损50%",
    "J3_score4": "J3:高门槛4.0(价值)",
    "J4_consensus1": "J4:低共识1人(激进)",
    "J5_consensus3": "J5:高共识3人(保守)",
    "J6_maxpos50": "J6:单仓上限50%(集中)",
    "J7_cash3": "J7:现金储备3%(满仓)",
    "J8_nostop": "J8:无止损(扛回撤)",
    "J9_hold60": "J9:最低持有60天",
    "J10_hold15": "J10:最低持有15天(快轮)",
    "K1_value_trend": "K1:价值+趋势(高门槛+MA20)",
    "K2_event_v2": "K2:事件驱动V2(MA20+止15%)",
    "K3_all_buy_filters": "K3:全部买入过滤(MA20+MACD+突破)",
    "S1_mom_adj": "S1:动量阈值动态调整(亏严盈松)",
    "S2_loss_hold30": "S2:亏损持有30天止损",
    "S2b_loss_hold15": "S2b:亏损持有15天止损",
    "S3_tp_trail_dyn": "S3:动态移动止盈(越赚越紧)",
    "S4_mom_decay5": "S4:动量衰退5天卖出",
    "S4b_mom_decay10": "S4b:动量衰退10天卖出",
    "S5_mom_adj_trail": "S5:动量调整+动态止盈",
    "S6_trail_atr": "S6:动态止盈+ATR止损",
    "S7_mom_adj_decay": "S7:动量调整+衰退卖出",
    "S8_profit_all": "S8:80%全卖止盈",
    "S9_profit_quarter": "S9:30%卖1/4止盈",
    "S10_no_mom_crash": "S10:禁用动量崩溃卖出",
    "S11_mom_crash_bull": "S11:牛市也触发动量崩溃",
    "S12_trail_act15": "S12:15%激活移动止盈10%",
    "S13_trail_act30": "S13:30%激活移动止盈8%",
    "S14_trail_act10_dd5": "S14:10%激活移动止盈5%",
    "S15_combo": "S15:组合(动量调整+动态止盈+移动止盈)",
    "T1_crash5_sell70": "T1:预测跌5%+P>70%清仓",
    "T2_crash3_sell70": "T2:预测跌3%+P>70%清仓",
    "T3_crash5_sell60": "T3:预测跌5%+P>60%清仓",
    "T4_crash10_sell80": "T4:预测跌10%+P>80%清仓",
    "U1_ma50_exit": "U1:MA50趋势破位卖出",
    "U2_vol_spike2": "U2:波动率2x突增卖出",
    "U2b_vol_spike3": "U2b:波动率3x突增卖出",
    "U3_port_dd10": "U3:组合回撤10%减仓30%",
    "U3b_port_dd15": "U3b:组合回撤15%减仓30%",
    "U4_rel_strength": "U4:相对强度买入(跑赢基准)",
    "U5_contrarian2": "U5:逆向买入(跌2%才买)",
    "U5b_contrarian3": "U5b:逆向买入(跌3%才买)",
    "V1_lgb_crash5_sell70": "V1:LGB预测跌5%+P>70%清仓",
    "V2_lgb_crash3_sell60": "V2:LGB预测跌3%+P>60%清仓",
    "V3_lgb_crash5_sell60": "V3:LGB预测跌5%+P>60%清仓",
    "V4_lgb_crash10_sell80": "V4:LGB预测跌10%+P>80%清仓",
    "W1_maxhold5": "W1:最多持5只(集中)",
    "W2_maxhold10": "W2:最多持10只",
    "W3_maxhold15": "W3:最多持15只(分散)",
    "W4_pyramid": "W4:金字塔加仓",
    "X1_ma50_portdd": "X1:MA50破位+组合回撤减仓",
    "X2_volspike_relstr": "X2:波动率突增+相对强度",
    "X3_lgb_ma50": "X3:LGB预测+MA50破位",
    "Y1_dynrank": "Y1:动态大佬排名(每30天重算)",
    "Y2_dynrank_w60": "Y2:动态排名+短窗口60天",
    "Y3_dynrank_w180": "Y3:动态排名+长窗口180天",
    "Y4_dynrank_hl30": "Y4:动态排名+短半衰期30天",
    "Y5_weighted": "Y5:加权共识(按大佬实力)",
    "Y6_net_signal": "Y6:净信号过滤(买>卖才买)",
    "Y7_dynrank_weighted": "Y7:动态排名+加权共识",
    "Y8_dynrank_netsig": "Y8:动态排名+净信号",
    "Z1_bear_nobuy": "Z1:熊市不买入",
    "Z2_dyn_maxpos": "Z2:动态仓位(牛35/震25/熊15)",
    "Z3_dyn_maxpos_cash": "Z3:动态仓位+动态现金储备",
    "Z4_no_timing": "Z4:关闭择时过滤",
    "Z5_no_overbought": "Z5:关闭超买过滤",
    "AA1_hold30": "AA1:最低持有30天",
    "AA2_hold90": "AA2:最低持有90天",
    "AA3_hold120": "AA3:最低持有120天",
    "AA4_slip05": "AA4:滑点0.5%",
    "AA5_slip10": "AA5:滑点1.0%",
    "AB1_sellcons2": "AB1:2人卖出才跟卖",
    "AB2_sellcons3": "AB2:3人卖出才跟卖",
    "AB3_topn5": "AB3:只买评分前5",
    "AB4_topn10": "AB4:只买评分前10",
    "AB5_consprio": "AB5:共识优先排序",
    "AB6_costpen": "AB6:高费率惩罚1.0",
    "AB7_limitboost": "AB7:限购基金加成",
    "AC1_inject1k": "AC1:每月定投1000",
    "AC2_inject5k": "AC2:每月定投5000",
    "AC3_nodynsl": "AC3:关闭动态止损",
    "AC4_noregime": "AC4:关闭行情自适应",
    "AC5_qdii50": "AC5:QDII占比限50%",
    "AD1_nopenalty": "AD1:无下跌趋势惩罚",
    "AD2_pen03": "AD2:轻下跌惩罚0.3",
    "AD3_pen10": "AD3:重下跌惩罚1.0",
    "AE1_bear_dynpos": "AE1:熊市不买+动态仓位",
    "AE2_dynrank_netsig_w": "AE2:动态排名+净信号+加权",
    "AE3_sellcons_dynrank": "AE3:跟卖+动态排名",
    "AE4_topn_consprio": "AE4:前10+共识优先",
    "BA1_w_cons1": "BA1:加权共识+门槛1(松)",
    "BA2_w_cons3": "BA2:加权共识+门槛3(严)",
    "BA3_w_cons4": "BA3:加权共识+门槛4(极严)",
    "BA4_w_thr15": "BA4:加权门槛1.5",
    "BA5_w_thr20": "BA5:加权门槛2.0",
    "BA6_w_thr25": "BA6:加权门槛2.5",
    "BA7_w_thr30": "BA7:加权门槛3.0",
    "BA8_w_thr35": "BA8:加权门槛3.5",
    "BA9_w_adaptive": "BA9:加权+自适应共识",
    "BA10_w_cons2_topn10": "BA10:加权+前10选基",
    "BA11_w_cons2_consprio": "BA11:加权+共识优先",
    "BA12_w_cons2_maxhold10": "BA12:加权+最多10只",
    "BB1_net_ratio15": "BB1:净信号+买卖比1.5x",
    "BB2_net_ratio2": "BB2:净信号+买卖比2.0x",
    "BB3_net_ratio3": "BB3:净信号+买卖比3.0x",
    "BB4_net_diff2": "BB4:净信号+差值>=2",
    "BB5_net_diff3": "BB5:净信号+差值>=3",
    "BB6_net_diff4": "BB6:净信号+差值>=4",
    "BB7_net_cons1": "BB7:净信号+门槛1(松)",
    "BB8_net_cons3": "BB8:净信号+门槛3(严)",
    "BB9_net_adaptive": "BB9:净信号+自适应",
    "BB10_net_topn10": "BB10:净信号+前10选基",
    "BB11_net_consprio": "BB11:净信号+共识优先",
    "BB12_net_maxhold10": "BB12:净信号+最多10只",
    "BC1_w_net": "BC1:加权+净信号(双核)",
    "BC2_w_net_cons1": "BC2:加权+净信号+门槛1",
    "BC3_w_net_cons3": "BC3:加权+净信号+门槛3",
    "BC4_w_net_thr20": "BC4:加权+净信号+权门2.0",
    "BC5_w_net_thr25": "BC5:加权+净信号+权门2.5",
    "BC6_w_net_diff2": "BC6:加权+净信号+差值2",
    "BC7_w_net_ratio2": "BC7:加权+净信号+比2x",
    "BC8_w_net_adaptive": "BC8:加权+净信号+自适应",
    "BC9_w_net_topn10": "BC9:加权+净信号+前10",
    "BC10_w_net_consprio": "BC10:加权+净信号+共识优先",
    "BC11_w_net_maxhold10": "BC11:加权+净信号+最多10只",
    "BC12_w_net_sellcons2": "BC12:加权+净信号+跟卖2",
    "BD1_w_net_score4": "BD1:加权+净信号+高评分4",
    "BD2_w_net_costpen": "BD2:加权+净信号+费率惩罚",
    "BD3_w_net_limitboost": "BD3:加权+净信号+限购加成",
    "BD4_w_net_qdii50": "BD4:加权+净信号+QDII限50%",
    "BD5_w_net_corr04": "BD5:加权+净信号+相关0.4",
    "BD6_w_net_sector30": "BD6:加权+净信号+行业30%",
    "BE1_w_net_topn_consprio": "BE1:加权+净信号+前10+优先",
    "BE2_w_net_thr25_diff2": "BE2:加权+净信号+权门2.5+差2",
    "BE3_w_net_adaptive_consprio": "BE3:加权+净信号+自适应+优先",
    "BE4_w_net_maxhold10_consprio": "BE4:加权+净信号+10只+优先",
    "BE5_w_net_thr20_adaptive": "BE5:加权+净信号+权门2+自适应",
    "BE6_w_net_thr30_diff3": "BE6:加权+净信号+权门3+差3",
    "FA1_kdj_block80": "FA1:KDJ超买80不买",
    "FA2_kdj_block70": "FA2:KDJ超买70不买",
    "FA3_kdj_block60": "FA3:KDJ超买60不买",
    "FA4_kdj_oversold": "FA4:KDJ超卖20才买",
    "FA5_kdj_oversold30": "FA5:KDJ超卖30才买",
    "FA6_kdj_golden": "FA6:KDJ金叉才买",
    "FA7_w_kdj_block80": "FA7:加权+KDJ超买80不买",
    "FA8_w_kdj_block70": "FA8:加权+KDJ超买70不买",
    "FA9_w_kdj_oversold": "FA9:加权+KDJ超卖才买",
    "FA10_w_kdj_golden": "FA10:加权+KDJ金叉才买",
    "FB1_kdj_sell_death": "FB1:KDJ死叉卖出",
    "FB2_kdj_sell_overexit": "FB2:KDJ超买区死叉卖",
    "FB3_w_kdj_sell_death": "FB3:加权+KDJ死叉卖",
    "FB4_w_kdj_sell_overexit": "FB4:加权+KDJ超买死叉卖",
    "FB5_kdj_buy_block_sell_death": "FB5:KDJ超买不买+死叉卖",
    "FB6_w_kdj_buy_sell": "FB6:加权+KDJ超买不买+死叉卖",
    "FC1_maccel_block": "FC1:动量加速不买(3月30%)",
    "FC2_maccel_block_20": "FC2:动量加速不买(3月20%)",
    "FC3_maccel_block_40": "FC3:动量加速不买(3月40%)",
    "FC4_maccel_ratio2": "FC4:动量加速(2倍才预警)",
    "FC5_maccel_ratio1": "FC5:动量加速(1倍即预警)",
    "FC6_maccel_sell": "FC6:动量加速卖出",
    "FC7_maccel_sell_20": "FC7:动量加速卖(3月20%)",
    "FC8_w_maccel_block": "FC8:加权+动量加速不买",
    "FC9_w_maccel_block_20": "FC9:加权+动量加速不买20%",
    "FC10_w_maccel_sell": "FC10:加权+动量加速卖出",
    "FD1_kdj_maccel": "FD1:KDJ超买+动量加速不买",
    "FD2_kdj_maccel_sell": "FD2:KDJ超买+动量加速卖",
    "FD3_w_kdj_maccel": "FD3:加权+KDJ+动量加速不买",
    "FD4_w_kdj_maccel_sell": "FD4:加权+KDJ+动量加速卖",
    "FD5_w_kdj_sell_maccel": "FD5:加权+KDJ卖+动量加速不买",
    "FE1_w_kdj_maccel_net": "FE1:加权+净信号+KDJ+动量",
    "FE2_w_kdj_sell_maccel_sell": "FE2:加权+KDJ卖+动量卖",
    "FE3_w_kdj_buy_sell_maccel": "FE3:加权+KDJ买卖+动量不买",
    "FE4_w_kdj_golden_maccel": "FE4:加权+KDJ金叉+动量不买",
}

# 导入参数扫描配置（113个自动生成的测试）
try:
    from backtest.sweep_configs import SWEEP_CONFIGS, SWEEP_LABELS
    TEST_CONFIGS.update(SWEEP_CONFIGS)
    LABELS.update(SWEEP_LABELS)
except ImportError:
    pass


def main():
    if len(sys.argv) < 2:
        print("Usage: python backtest/run_single_test.py <test_name>")
        sys.exit(1)

    test_name = sys.argv[1]
    if test_name not in TEST_CONFIGS:
        print(f"Unknown test: {test_name}")
        print(f"Available: {', '.join(TEST_CONFIGS.keys())}")
        sys.exit(1)

    # 确定项目根目录
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    os.chdir(project_root)
    sys.path.insert(0, project_root)

    from backtest.engine.backtest import run_backtest

    base_cfg = json.loads(
        open("data/evolution/best_config.json", "r", encoding="utf-8").read()
    )["config"]

    cfg = copy.deepcopy(base_cfg)
    cfg.update(TEST_CONFIGS[test_name])
    cfg["start_date"] = "2023-07-17"
    cfg["end_date"] = "2026-07-17"
    cfg["initial_cash"] = 100000

    t0 = time.time()
    label = LABELS.get(test_name, test_name)
    print(f"{'='*60}")
    print(f"Test: {label} ({test_name})")
    print(f"{'='*60}")

    r = run_backtest(cfg)
    elapsed = time.time() - t0

    result = {
        "name": test_name,
        "label": label,
        "total_return": round(r["total_return"], 2),
        "max_drawdown": round(r["max_drawdown"], 2),
        "sharpe": round(r["sharpe_ratio"], 2),
        "trade_count": r["trade_count"],
        "elapsed_sec": round(elapsed, 1),
    }
    print(f"\n{'='*60}")
    print(f"Result: {label}")
    print(f"  return={result['total_return']}% dd={result['max_drawdown']}% "
          f"sharpe={result['sharpe']} trades={result['trade_count']} "
          f"time={result['elapsed_sec']}s")
    print(f"{'='*60}")

    os.makedirs("backtest/results", exist_ok=True)
    outpath = f"backtest/results/{test_name}.json"
    with open(outpath, "w") as f:
        json.dump(result, f, indent=2)
    print(f"Saved: {outpath}")


if __name__ == "__main__":
    main()
