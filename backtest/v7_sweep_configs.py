#!/usr/bin/env python3
"""Generate V7 sweep configs: Cross-combine V5 champion + V6 winners.

V7 fix (2026-07-27):
  - V5_CHAMP min_consensus 3→2 (was too strict, caused 0 trades with contrarian)
  - D4/D5/E4/F4 removed min_consensus=3 overrides
  - Added Group G: control strategies WITHOUT contrarian_buy_drop
    (to test if contrarian caused 0 trades)
  - Added Group H: fund_drop_buy instead of contrarian_buy_drop
    (V6's real winning feature was fund-level drop, not market-level)
"""
import json

# ═══════════════════════════════════════════════════════════════
# V5 Champion base config (ret=+99.80%, sharpe=6.94)
# Key differentiators: min_consensus=2 (lowered from 3), custom weights,
#   kelly=0.5, bear_market_no_buy, downtrend_penalty, ranking_half_life=45
# ═══════════════════════════════════════════════════════════════
V5_CHAMP = {
    "start_date": "2023-07-17",
    "end_date": "2026-07-24",
    "initial_cash": 10000,
    "monthly_injection": 0,
    "weights": {"quality": 17, "cost": 23, "manager": 29, "momentum": 11, "smart_money": 20},
    "min_score": 0.0,
    "min_consensus": 2,
    "max_holdings": 8,
    "max_position_pct": 40,
    "cash_reserve_pct": 0.05,
    "cooldown_days": 0,
    "take_profit_pct": 1000,
    "stop_loss_pct": -30,
    "trailing_tp_activate": 0,
    "trailing_tp_drawdown": 10,
    "dynamic_ranking": False,
    "ranking_window": 90,
    "kelly_cap": 0.5,
    "momentum_sell": 0.07,
    "profit_mode": "half",
    "no_stop_loss": True,
    "use_weighted_consensus": False,
    "cost_penalty": 0,
    "limit_boost": 0,
    "top_n": 0,
    "top_n_pct": 0,
    "consensus_priority": False,
    "net_signal": False,
    "max_sector_pct": 40,
    "max_qdii_pct": 100,
    "rebalance": True,
    "fund_type_filter": "all",
    "sell_consensus": 0,
    "cooldown_profit_days": 13,
    "cooldown_loss_days": 30,
    "max_correlation": 0.6,
    "ml_signal": False,
    "ml_weight": 1.0,
    "ml_retrain_days": 30,
    "timing_filter": True,
    "block_overbought": True,
    "bear_market_no_buy": True,
    "min_score_bull": 0.0,
    "min_score_neutral": 0.0,
    "min_score_bear": 0.0,
    "downtrend_penalty": 0.602,
    "risk_free_rate": 0.025,
    "slippage_pct": 0.0,
    "ranking_half_life": 45,
    "pyramiding_enabled": False,
    "dynamic_stop_loss": False,
    "regime_specific": True,
    "exclude_uids": [],
    "take_profit_pct_bull": 120,
    "take_profit_pct_neutral": 80,
    "take_profit_pct_bear": 50,
    "stop_loss_pct_bull": -25,
    "stop_loss_pct_neutral": -30,
    "stop_loss_pct_bear": -20,
    "kelly_cap_bull": 0.4,
    "kelly_cap_neutral": 0.3,
    "kelly_cap_bear": 0.15,
    "pyramiding_enabled_bull": False,
    "pyramiding_enabled_neutral": False,
    "pyramiding_enabled_bear": True,
    "trailing_tp_activate_bull": 20,
    "trailing_tp_activate_neutral": 15,
    "trailing_tp_activate_bear": 10,
    "trailing_tp_drawdown_bull": 8,
    "trailing_tp_drawdown_neutral": 10,
    "trailing_tp_drawdown_bear": 6,
}

# ═══════════════════════════════════════════════════════════════
# V6 Base config (the base used in V6A/B/C)
# Key: min_score=3.3, min_consensus=2, kelly_cap=0.35, smart_swap
# ═══════════════════════════════════════════════════════════════
V6_BASE = {
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


def v5_with(**overrides):
    """Start from V5 champion config, apply overrides."""
    cfg = dict(V5_CHAMP)
    cfg.update(overrides)
    return cfg


def v6_with(**overrides):
    """Start from V6 base config, apply overrides."""
    cfg = dict(V6_BASE)
    cfg.update(overrides)
    return cfg


v5_weights = {"quality": 17, "cost": 23, "manager": 29, "momentum": 11, "smart_money": 20}

strategies = []

# ═══════════════════════════════════════════════════════════════
# A. V5 Champion + V6 Winning Features (with contrarian_buy_drop)
# ═══════════════════════════════════════════════════════════════
strategies.append({"name": "V7_A1_v5_drop03", "desc": "V5 champ + contrarian drop 3%", "config": v5_with(contrarian_buy_drop=0.03)})
strategies.append({"name": "V7_A2_v5_drop03_pyr", "desc": "V5 champ + drop3% + pyramiding", "config": v5_with(contrarian_buy_drop=0.03, pyramiding_enabled=True)})
strategies.append({"name": "V7_A3_v5_drop03_4433_2", "desc": "V5 champ + drop3% + 4433 filter", "config": v5_with(contrarian_buy_drop=0.03, require_4433_pass=2)})
strategies.append({"name": "V7_A4_v5_drop03_pyr_4433", "desc": "V5 champ + drop3% + pyramiding + 4433", "config": v5_with(contrarian_buy_drop=0.03, pyramiding_enabled=True, require_4433_pass=2)})
strategies.append({"name": "V7_A5_v5_drop03_pyr_rkelly", "desc": "V5 champ + drop3% + pyramiding + regime kelly", "config": v5_with(contrarian_buy_drop=0.03, pyramiding_enabled=True, regime_specific=True, kelly_cap_bull=0.5, kelly_cap_bear=0.15)})
strategies.append({"name": "V7_A6_v5_drop03_pyr_4433_corr", "desc": "V5 champ + drop3% + pyramiding + 4433 + corr0.7", "config": v5_with(contrarian_buy_drop=0.03, pyramiding_enabled=True, require_4433_pass=2, max_correlation=0.7)})
strategies.append({"name": "V7_A7_v5_ultimate", "desc": "V5 champ + ALL V6 winners", "config": v5_with(contrarian_buy_drop=0.03, pyramiding_enabled=True, require_4433_pass=2, max_correlation=0.7, max_sector_count=3, mom_decay_days=5, regime_specific=True, kelly_cap_bull=0.5, kelly_cap_bear=0.15)})
strategies.append({"name": "V7_A8_v5_drop03_pyr_momdecay", "desc": "V5 champ + drop3% + pyramiding + mom decay", "config": v5_with(contrarian_buy_drop=0.03, pyramiding_enabled=True, mom_decay_days=5)})
strategies.append({"name": "V7_A9_v5_drop02_pyr", "desc": "V5 champ + drop2% + pyramiding", "config": v5_with(contrarian_buy_drop=0.02, pyramiding_enabled=True)})
strategies.append({"name": "V7_A10_v5_drop04_pyr", "desc": "V5 champ + drop4% + pyramiding", "config": v5_with(contrarian_buy_drop=0.04, pyramiding_enabled=True)})
strategies.append({"name": "V7_A11_v5_drop03_pyr_4433_momdecay", "desc": "V5 champ + drop3% + pyramiding + 4433 + momdecay", "config": v5_with(contrarian_buy_drop=0.03, pyramiding_enabled=True, require_4433_pass=2, mom_decay_days=5)})
strategies.append({"name": "V7_A12_v5_smartswap", "desc": "V5 champ + smart_swap (from V6 base)", "config": v5_with(contrarian_buy_drop=0.03, pyramiding_enabled=True, smart_swap=True, smart_swap_margin=1.0, smart_swap_min_hold_days=30)})

# ═══════════════════════════════════════════════════════════════
# B. V6 Champion Cross-Combinations (with contrarian_buy_drop)
# ═══════════════════════════════════════════════════════════════
strategies.append({"name": "V7_B1_pyr_4433_2", "desc": "V6 #1 + #2: pyramiding + 4433", "config": v6_with(contrarian_buy_drop=0.03, pyramiding_enabled=True, regime_specific=True, kelly_cap_bull=0.5, kelly_cap_bear=0.15, require_4433_pass=2)})
strategies.append({"name": "V7_B2_pyr_momdecay", "desc": "V6 #1 + #4: pyramiding + mom decay", "config": v6_with(contrarian_buy_drop=0.03, pyramiding_enabled=True, regime_specific=True, kelly_cap_bull=0.5, kelly_cap_bear=0.15, mom_decay_days=5)})
strategies.append({"name": "V7_B3_pyr_4433_corr", "desc": "V6 #1 + #2 + #3: pyramiding + 4433 + corr", "config": v6_with(contrarian_buy_drop=0.03, pyramiding_enabled=True, regime_specific=True, kelly_cap_bull=0.5, kelly_cap_bear=0.15, require_4433_pass=2, max_correlation=0.7)})
strategies.append({"name": "V7_B4_pyr_4433_momdecay", "desc": "pyramiding + 4433 + mom decay", "config": v6_with(contrarian_buy_drop=0.03, pyramiding_enabled=True, regime_specific=True, kelly_cap_bull=0.5, kelly_cap_bear=0.15, require_4433_pass=2, mom_decay_days=5)})
strategies.append({"name": "V7_B5_ultimate_combo", "desc": "ALL V6 winners combined", "config": v6_with(contrarian_buy_drop=0.03, pyramiding_enabled=True, regime_specific=True, kelly_cap_bull=0.5, kelly_cap_bear=0.15, require_4433_pass=2, max_correlation=0.7, max_sector_count=3, mom_decay_days=5)})
strategies.append({"name": "V7_B6_4433_momdecay", "desc": "4433 + mom decay (no pyramiding)", "config": v6_with(contrarian_buy_drop=0.03, require_4433_pass=2, mom_decay_days=5)})
strategies.append({"name": "V7_B7_4433_corr_momdecay", "desc": "4433 + corr + mom decay", "config": v6_with(contrarian_buy_drop=0.03, require_4433_pass=2, max_correlation=0.7, mom_decay_days=5)})
strategies.append({"name": "V7_B8_pyr_4433_smartswap", "desc": "pyramiding + 4433 + smart_swap", "config": v6_with(contrarian_buy_drop=0.03, pyramiding_enabled=True, regime_specific=True, kelly_cap_bull=0.5, kelly_cap_bear=0.15, require_4433_pass=2, smart_swap=True)})

# ═══════════════════════════════════════════════════════════════
# C. V6 Champion Fine-Tuning (with contrarian_buy_drop)
# ═══════════════════════════════════════════════════════════════
strategies.append({"name": "V7_C1_pyr_kc040", "desc": "pyramiding kelly=0.40", "config": v6_with(contrarian_buy_drop=0.03, pyramiding_enabled=True, regime_specific=True, kelly_cap_bull=0.5, kelly_cap_bear=0.15, kelly_cap=0.40)})
strategies.append({"name": "V7_C2_pyr_kc045", "desc": "pyramiding kelly=0.45", "config": v6_with(contrarian_buy_drop=0.03, pyramiding_enabled=True, regime_specific=True, kelly_cap_bull=0.5, kelly_cap_bear=0.15, kelly_cap=0.45)})
strategies.append({"name": "V7_C3_pyr_kc050", "desc": "pyramiding kelly=0.50", "config": v6_with(contrarian_buy_drop=0.03, pyramiding_enabled=True, regime_specific=True, kelly_cap_bull=0.55, kelly_cap_bear=0.20, kelly_cap=0.50)})
strategies.append({"name": "V7_C4_4433_3", "desc": "4433 stricter=3", "config": v6_with(contrarian_buy_drop=0.03, require_4433_pass=3)})
strategies.append({"name": "V7_C5_4433_1_pyr", "desc": "4433=1 + pyramiding", "config": v6_with(contrarian_buy_drop=0.03, require_4433_pass=1, pyramiding_enabled=True, regime_specific=True, kelly_cap_bull=0.5, kelly_cap_bear=0.15)})
strategies.append({"name": "V7_C6_pyr_ms30", "desc": "pyramiding + min_score=3.0", "config": v6_with(contrarian_buy_drop=0.03, pyramiding_enabled=True, regime_specific=True, kelly_cap_bull=0.5, kelly_cap_bear=0.15, min_score=3.0)})
strategies.append({"name": "V7_C7_pyr_ms35", "desc": "pyramiding + min_score=3.5", "config": v6_with(contrarian_buy_drop=0.03, pyramiding_enabled=True, regime_specific=True, kelly_cap_bull=0.5, kelly_cap_bear=0.15, min_score=3.5)})
strategies.append({"name": "V7_C8_pyr_maxhold10", "desc": "pyramiding + max_holdings=10", "config": v6_with(contrarian_buy_drop=0.03, pyramiding_enabled=True, regime_specific=True, kelly_cap_bull=0.5, kelly_cap_bear=0.15, max_holdings=10)})
strategies.append({"name": "V7_C9_pyr_maxhold6", "desc": "pyramiding + max_holdings=6 (concentrated)", "config": v6_with(contrarian_buy_drop=0.03, pyramiding_enabled=True, regime_specific=True, kelly_cap_bull=0.5, kelly_cap_bear=0.15, max_holdings=6)})
strategies.append({"name": "V7_C10_pyr_trail20_8", "desc": "pyramiding + trailing TP 20/8", "config": v6_with(contrarian_buy_drop=0.03, pyramiding_enabled=True, regime_specific=True, kelly_cap_bull=0.5, kelly_cap_bear=0.15, trailing_tp_activate=20, trailing_tp_drawdown=8)})

# ═══════════════════════════════════════════════════════════════
# D. V5 Features on V6 Base (with contrarian_buy_drop)
# ═══════════════════════════════════════════════════════════════
strategies.append({"name": "V7_D1_v6base_v5weights", "desc": "V6 base + V5 weights", "config": v6_with(weights=v5_weights, contrarian_buy_drop=0.03)})
strategies.append({"name": "V7_D2_v6base_v5w_pyr", "desc": "V6 base + V5 weights + pyramiding", "config": v6_with(weights=v5_weights, contrarian_buy_drop=0.03, pyramiding_enabled=True, regime_specific=True, kelly_cap_bull=0.5, kelly_cap_bear=0.15)})
strategies.append({"name": "V7_D3_v6base_v5w_pyr_4433", "desc": "V6 base + V5 weights + pyramiding + 4433", "config": v6_with(weights=v5_weights, contrarian_buy_drop=0.03, pyramiding_enabled=True, regime_specific=True, kelly_cap_bull=0.5, kelly_cap_bear=0.15, require_4433_pass=2)})
strategies.append({"name": "V7_D4_v6base_pyr", "desc": "V6 base + pyramiding (was cons3, now cons2)", "config": v6_with(contrarian_buy_drop=0.03, pyramiding_enabled=True, regime_specific=True, kelly_cap_bull=0.5, kelly_cap_bear=0.15)})
strategies.append({"name": "V7_D5_v6base_v5w_pyr", "desc": "V6 base + V5 weights + pyramiding (was cons3)", "config": v6_with(weights=v5_weights, contrarian_buy_drop=0.03, pyramiding_enabled=True, regime_specific=True, kelly_cap_bull=0.5, kelly_cap_bear=0.15)})
strategies.append({"name": "V7_D6_v6base_bearnobuy_pyr", "desc": "V6 base + bear_market_no_buy + pyramiding", "config": v6_with(contrarian_buy_drop=0.03, bear_market_no_buy=True, pyramiding_enabled=True, regime_specific=True, kelly_cap_bull=0.5, kelly_cap_bear=0.15)})
strategies.append({"name": "V7_D7_v6base_momsell_pyr", "desc": "V6 base + momentum_sell=0.07 + pyramiding", "config": v6_with(contrarian_buy_drop=0.03, momentum_sell=0.07, pyramiding_enabled=True, regime_specific=True, kelly_cap_bull=0.5, kelly_cap_bear=0.15)})

# ═══════════════════════════════════════════════════════════════
# E. Ultimate Hybrids (V5 + V6 everything, with contrarian_buy_drop)
# ═══════════════════════════════════════════════════════════════
strategies.append({"name": "V7_E1_v5_all_v6", "desc": "V5 champ + ALL V6 features", "config": v5_with(
    contrarian_buy_drop=0.03, pyramiding_enabled=True, require_4433_pass=2,
    max_correlation=0.7, max_sector_count=3, mom_decay_days=5,
    regime_specific=True, kelly_cap_bull=0.5, kelly_cap_bear=0.15,
    smart_swap=True, smart_swap_margin=1.0, smart_swap_min_hold_days=30,
    dynamic_max_holdings=True, max_holdings_bull_mult=1.5, max_holdings_bear_mult=0.6,
    max_holdings=8
)})
strategies.append({"name": "V7_E2_v5_pyr_4433_momdecay", "desc": "V5 champ + pyramiding + 4433 + momdecay", "config": v5_with(
    contrarian_buy_drop=0.03, pyramiding_enabled=True, require_4433_pass=2, mom_decay_days=5,
    regime_specific=True, kelly_cap_bull=0.5, kelly_cap_bear=0.15
)})
strategies.append({"name": "V7_E3_v5_pyr_smartswap_4433", "desc": "V5 champ + pyramiding + smartswap + 4433", "config": v5_with(
    contrarian_buy_drop=0.03, pyramiding_enabled=True, require_4433_pass=2,
    smart_swap=True, smart_swap_margin=1.0, smart_swap_min_hold_days=30,
    regime_specific=True, kelly_cap_bull=0.5, kelly_cap_bear=0.15,
    dynamic_max_holdings=True, max_holdings_bull_mult=1.5, max_holdings_bear_mult=0.6, max_holdings=8
)})
strategies.append({"name": "V7_E4_v5w_ultimate", "desc": "V6 base + V5 weights + ALL V6 winners", "config": v6_with(
    weights=v5_weights, contrarian_buy_drop=0.03,
    pyramiding_enabled=True, require_4433_pass=2, max_correlation=0.7,
    max_sector_count=3, mom_decay_days=5, regime_specific=True,
    kelly_cap_bull=0.5, kelly_cap_bear=0.15, bear_market_no_buy=True,
    momentum_sell=0.07
)})
strategies.append({"name": "V7_E5_v5_drop03_4433_3_pyr", "desc": "V5 champ + drop3% + strict 4433=3 + pyramiding", "config": v5_with(
    contrarian_buy_drop=0.03, pyramiding_enabled=True, require_4433_pass=3,
    regime_specific=True, kelly_cap_bull=0.5, kelly_cap_bear=0.15
)})

# ═══════════════════════════════════════════════════════════════
# F. Exploratory: New parameter combinations (with contrarian_buy_drop)
# ═══════════════════════════════════════════════════════════════
strategies.append({"name": "V7_F1_v5_drop03_downtrend02", "desc": "V5 + drop3% + lower downtrend penalty", "config": v5_with(contrarian_buy_drop=0.03, downtrend_penalty=0.3)})
strategies.append({"name": "V7_F2_v5_drop03_downtrend08", "desc": "V5 + drop3% + higher downtrend penalty", "config": v5_with(contrarian_buy_drop=0.03, downtrend_penalty=0.8)})
strategies.append({"name": "V7_F3_v5_drop03_rkelly_smartswap", "desc": "V5 + drop3% + regime kelly + smart swap", "config": v5_with(
    contrarian_buy_drop=0.03, pyramiding_enabled=True, regime_specific=True,
    kelly_cap_bull=0.5, kelly_cap_bear=0.15, smart_swap=True,
    smart_swap_margin=1.0, smart_swap_min_hold_days=30
)})
strategies.append({"name": "V7_F4_v6base_v5w_bear_4433", "desc": "V6 base + V5w + bear + 4433 + pyramiding", "config": v6_with(
    weights=v5_weights, bear_market_no_buy=True,
    contrarian_buy_drop=0.03, require_4433_pass=2, pyramiding_enabled=True,
    regime_specific=True, kelly_cap_bull=0.5, kelly_cap_bear=0.15,
    momentum_sell=0.07, downtrend_penalty=0.602
)})

# ═══════════════════════════════════════════════════════════════
# G. Control Group: NO contrarian_buy_drop
# Test if contrarian_buy_drop caused 0 trades in previous V7 run.
# Same features as A/B but without market-crash filter.
# ═══════════════════════════════════════════════════════════════
strategies.append({"name": "V7_G1_v5_nocontrarian_pyr", "desc": "V5 champ, no contrarian, pyramiding", "config": v5_with(pyramiding_enabled=True, regime_specific=True, kelly_cap_bull=0.5, kelly_cap_bear=0.15)})
strategies.append({"name": "V7_G2_v5_nocontrarian_pyr_4433", "desc": "V5 champ, no contrarian, pyramiding+4433", "config": v5_with(pyramiding_enabled=True, require_4433_pass=2, regime_specific=True, kelly_cap_bull=0.5, kelly_cap_bear=0.15)})
strategies.append({"name": "V7_G3_v5_nocontrarian_smartswap", "desc": "V5 champ, no contrarian, smartswap+pyramiding", "config": v5_with(pyramiding_enabled=True, smart_swap=True, smart_swap_margin=1.0, smart_swap_min_hold_days=30, regime_specific=True, kelly_cap_bull=0.5, kelly_cap_bear=0.15)})
strategies.append({"name": "V7_G4_v6_nocontrarian_pyr", "desc": "V6 base, no contrarian, pyramiding+rkelly", "config": v6_with(pyramiding_enabled=True, regime_specific=True, kelly_cap_bull=0.5, kelly_cap_bear=0.15)})
strategies.append({"name": "V7_G5_v6_nocontrarian_pyr_4433", "desc": "V6 base, no contrarian, 4433+pyramiding", "config": v6_with(pyramiding_enabled=True, require_4433_pass=2, regime_specific=True, kelly_cap_bull=0.5, kelly_cap_bear=0.15)})
strategies.append({"name": "V7_G6_v6_nocontrarian_ultimate", "desc": "V6 base, no contrarian, ALL winners", "config": v6_with(pyramiding_enabled=True, require_4433_pass=2, max_correlation=0.7, max_sector_count=3, mom_decay_days=5, regime_specific=True, kelly_cap_bull=0.5, kelly_cap_bear=0.15)})
strategies.append({"name": "V7_G7_v5w_nocontrarian_ultimate", "desc": "V6 base+V5w, no contrarian, ALL winners", "config": v6_with(weights=v5_weights, pyramiding_enabled=True, require_4433_pass=2, max_correlation=0.7, max_sector_count=3, mom_decay_days=5, regime_specific=True, kelly_cap_bull=0.5, kelly_cap_bear=0.15, bear_market_no_buy=True, momentum_sell=0.07)})
strategies.append({"name": "V7_G8_v6_nocontrarian_baseline", "desc": "V6 base, no contrarian, no extras (pure baseline)", "config": v6_with()})

# ═══════════════════════════════════════════════════════════════
# H. Fund-level drop (fund_drop_buy) instead of market-level (contrarian_buy_drop)
# V6's real winning feature was fund_drop_buy, not contrarian_buy_drop.
# fund_drop_buy checks each individual fund's N-day drop, much more common.
# ═══════════════════════════════════════════════════════════════
strategies.append({"name": "V7_H1_v6_funddrop03_d5_pyr", "desc": "V6 base + fund_drop 3% 5d + pyramiding", "config": v6_with(fund_drop_buy=0.03, fund_drop_days=5, pyramiding_enabled=True, regime_specific=True, kelly_cap_bull=0.5, kelly_cap_bear=0.15)})
strategies.append({"name": "V7_H2_v6_funddrop03_d5_pyr_4433", "desc": "V6 base + fund_drop + 4433 + pyramiding", "config": v6_with(fund_drop_buy=0.03, fund_drop_days=5, pyramiding_enabled=True, require_4433_pass=2, regime_specific=True, kelly_cap_bull=0.5, kelly_cap_bear=0.15)})
strategies.append({"name": "V7_H3_v6_funddrop05_d5_pyr", "desc": "V6 base + fund_drop 5% 5d + pyramiding", "config": v6_with(fund_drop_buy=0.05, fund_drop_days=5, pyramiding_enabled=True, regime_specific=True, kelly_cap_bull=0.5, kelly_cap_bear=0.15)})
strategies.append({"name": "V7_H4_v6_funddrop03_d10_pyr", "desc": "V6 base + fund_drop 3% 10d + pyramiding", "config": v6_with(fund_drop_buy=0.03, fund_drop_days=10, pyramiding_enabled=True, regime_specific=True, kelly_cap_bull=0.5, kelly_cap_bear=0.15)})
strategies.append({"name": "V7_H5_v6_funddrop05_d5_ultimate", "desc": "V6 base + fund_drop 5% + ALL winners", "config": v6_with(fund_drop_buy=0.05, fund_drop_days=5, pyramiding_enabled=True, require_4433_pass=2, max_correlation=0.7, max_sector_count=3, mom_decay_days=5, regime_specific=True, kelly_cap_bull=0.5, kelly_cap_bear=0.15)})
strategies.append({"name": "V7_H6_v5w_funddrop05_d5_pyr", "desc": "V6 base+V5w + fund_drop 5% + pyramiding", "config": v6_with(weights=v5_weights, fund_drop_buy=0.05, fund_drop_days=5, pyramiding_enabled=True, regime_specific=True, kelly_cap_bull=0.5, kelly_cap_bear=0.15)})
strategies.append({"name": "V7_H7_v6_funddrop03_d5_smartswap", "desc": "V6 base + fund_drop + smartswap + pyramiding", "config": v6_with(fund_drop_buy=0.03, fund_drop_days=5, pyramiding_enabled=True, smart_swap=True, smart_swap_margin=1.0, smart_swap_min_hold_days=30, regime_specific=True, kelly_cap_bull=0.5, kelly_cap_bear=0.15)})
strategies.append({"name": "V7_H8_v6_funddrop05_d5_equal", "desc": "V6 base + fund_drop 5% + equal_allocate", "config": v6_with(fund_drop_buy=0.05, fund_drop_days=5, equal_allocate=True, kelly_cap=0.40)})

print(f"Total V7 strategies: {len(strategies)}")
for s in strategies:
    print(f"  {s['name']:45s} {s['desc']}")

with open("backtest/v7_sweep_configs.json", "w", encoding="utf-8") as f:
    json.dump(strategies, f, ensure_ascii=False, indent=2)

print(f"\nSaved to backtest/v7_sweep_configs.json")
