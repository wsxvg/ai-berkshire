#!/usr/bin/env python3
"""Generate V8 sweep configs: Multi-day consensus window.

V8 core change: consensus_window_days parameter.
Instead of requiring 2+ buyers on the SAME day, accumulate buyers
over N trading days. This dramatically increases signal coverage
without lowering quality (still need 2+ distinct buyers).

V7 champion: V7_C6_pyr_ms30 (ret=+101.68%, sharpe=6.21, 39 trades)
Key bottleneck: contrarian_buy_drop limits buying to ~15-20 days/3yr.
Multi-day consensus lets us pick up signals from those window days
even if the market didn't crash on that exact day.
"""
import json

# ═══════════════════════════════════════════════════════════════
# V7 Champion base (V7_C6_pyr_ms30 config)
# ret=+101.68%, sharpe=6.21, 39 trades, AO=85.8
# ═══════════════════════════════════════════════════════════════
V7_CHAMP = {
    "start_date": "2023-07-17",
    "end_date": "2026-07-24",
    "initial_cash": 10000,
    "monthly_injection": 0,
    "weights": {"quality": 25, "cost": 20, "manager": 20, "momentum": 15, "smart_money": 20},
    "min_score": 3.0,
    "no_stop_loss": True,
    "take_profit_pct": 1000,
    "profit_mode": "half",
    "cost_penalty": 0,
    "min_consensus": 2,
    "fund_type_filter": "all",
    "momentum_sell": 0,
    "max_candidates_per_day": 30,  # 限制评分数量，多日窗口会增加候选数
    "max_holdings": 8,
    "kelly_cap": 0.35,
    "smart_swap": True,
    "smart_swap_margin": 1.0,
    "smart_swap_min_hold_days": 30,
    "dynamic_max_holdings": True,
    "max_holdings_bull_mult": 1.5,
    "max_holdings_bear_mult": 0.6,
    # V7 champion overrides
    "contrarian_buy_drop": 0.03,
    "pyramiding_enabled": True,
    "regime_specific": True,
    "kelly_cap_bull": 0.5,
    "kelly_cap_bear": 0.15,
}

# V6 Base without contrarian (for control groups)
V6_BASE_NO_CONTRARIAN = dict(V7_CHAMP)
V6_BASE_NO_CONTRARIAN.pop("contrarian_buy_drop", None)
V6_BASE_NO_CONTRARIAN["min_score"] = 3.3
V6_BASE_NO_CONTRARIAN["kelly_cap"] = 0.35
V6_BASE_NO_CONTRARIAN.pop("pyramiding_enabled", None)
V6_BASE_NO_CONTRARIAN.pop("regime_specific", None)
V6_BASE_NO_CONTRARIAN.pop("kelly_cap_bull", None)
V6_BASE_NO_CONTRARIAN.pop("kelly_cap_bear", None)
V6_BASE_NO_CONTRARIAN["max_candidates_per_day"] = 50  # 限制评分数量，防止多日窗口导致性能爆炸


def champ_with(**overrides):
    cfg = dict(V7_CHAMP)
    cfg.update(overrides)
    return cfg


def base_with(**overrides):
    cfg = dict(V6_BASE_NO_CONTRARIAN)
    cfg.update(overrides)
    return cfg


strategies = []

# ═══════════════════════════════════════════════════════════════
# A. V7 Champion + Multi-day Consensus (core test)
# Keep contrarian timing, add multi-day signal accumulation
# ═══════════════════════════════════════════════════════════════
for window in [3, 5, 7, 10, 14]:
    strategies.append({
        "name": f"V8_A1_cw{window}",
        "desc": f"V7 champ + consensus_window={window}d",
        "config": champ_with(consensus_window_days=window)
    })

# With lower kelly (reduce drawdown)
for window in [3, 5, 7]:
    strategies.append({
        "name": f"V8_A2_cw{window}_kc025",
        "desc": f"V7 champ + cw={window}d + kelly=0.25 (lower DD)",
        "config": champ_with(consensus_window_days=window, kelly_cap=0.25)
    })

# With min_score=3.3 (stricter quality filter to offset more signals)
for window in [3, 5, 7]:
    strategies.append({
        "name": f"V8_A3_cw{window}_ms33",
        "desc": f"V7 champ + cw={window}d + min_score=3.3",
        "config": champ_with(consensus_window_days=window, min_score=3.3)
    })

# ═══════════════════════════════════════════════════════════════
# B. Multi-day Consensus WITHOUT Contrarian
# Test if multi-day consensus alone provides enough timing
# ═══════════════════════════════════════════════════════════════
for window in [3, 5, 7, 10]:
    strategies.append({
        "name": f"V8_B1_cw{window}_nocontrarian",
        "desc": f"No contrarian + cw={window}d + pyramiding",
        "config": base_with(consensus_window_days=window, pyramiding_enabled=True,
                           regime_specific=True, kelly_cap_bull=0.5, kelly_cap_bear=0.15)
    })

# Without pyramiding (simpler)
for window in [5, 7]:
    strategies.append({
        "name": f"V8_B2_cw{window}_simple",
        "desc": f"No contrarian + cw={window}d (no pyramiding)",
        "config": base_with(consensus_window_days=window)
    })

# ═══════════════════════════════════════════════════════════════
# C. Multi-day Consensus + fund_drop_buy (replace contrarian)
# fund_drop_buy checks individual fund drops, more frequent than market-level
# ═══════════════════════════════════════════════════════════════
for window in [3, 5, 7]:
    strategies.append({
        "name": f"V8_C1_cw{window}_fdrop03",
        "desc": f"fund_drop 3% 5d + cw={window}d + pyramiding",
        "config": base_with(consensus_window_days=window, fund_drop_buy=0.03, fund_drop_days=5,
                           pyramiding_enabled=True, regime_specific=True,
                           kelly_cap_bull=0.5, kelly_cap_bear=0.15)
    })
    strategies.append({
        "name": f"V8_C2_cw{window}_fdrop05",
        "desc": f"fund_drop 5% 5d + cw={window}d + pyramiding",
        "config": base_with(consensus_window_days=window, fund_drop_buy=0.05, fund_drop_days=5,
                           pyramiding_enabled=True, regime_specific=True,
                           kelly_cap_bull=0.5, kelly_cap_bear=0.15)
    })

# ═══════════════════════════════════════════════════════════════
# D. Multi-day Consensus + 4433 Filter (quality + timing)
# ═══════════════════════════════════════════════════════════════
for window in [5, 7]:
    strategies.append({
        "name": f"V8_D1_cw{window}_4433_2",
        "desc": f"V7 champ + cw={window}d + 4433 pass=2",
        "config": champ_with(consensus_window_days=window, require_4433_pass=2)
    })
    strategies.append({
        "name": f"V8_D2_cw{window}_nocontr_4433",
        "desc": f"No contrarian + cw={window}d + 4433 pass=2 + pyramiding",
        "config": base_with(consensus_window_days=window, require_4433_pass=2,
                           pyramiding_enabled=True, regime_specific=True,
                           kelly_cap_bull=0.5, kelly_cap_bear=0.15)
    })

# ═══════════════════════════════════════════════════════════════
# E. Lower Contrarian Threshold + Multi-day (more buying days)
# Instead of 3% market drop, test 1% and 2% for more opportunities
# ═══════════════════════════════════════════════════════════════
for drop in [0.01, 0.02]:
    for window in [3, 5, 7]:
        strategies.append({
            "name": f"V8_E1_drop{int(drop*100):02d}_cw{window}",
            "desc": f"contrarian={drop*100:.0f}% + cw={window}d",
            "config": champ_with(consensus_window_days=window, contrarian_buy_drop=drop)
        })

# ═══════════════════════════════════════════════════════════════
# F. Adaptive Consensus + Multi-day (best of both)
# adaptive_consensus lowers min_consensus in sparse periods,
# multi-day accumulates signals — combined should cover all periods
# ═══════════════════════════════════════════════════════════════
for window in [3, 5, 7]:
    strategies.append({
        "name": f"V8_F1_cw{window}_adaptive",
        "desc": f"V7 champ + cw={window}d + adaptive_consensus",
        "config": champ_with(consensus_window_days=window, adaptive_consensus=True)
    })
    strategies.append({
        "name": f"V8_F2_cw{window}_adaptive_nocontr",
        "desc": f"No contrarian + cw={window}d + adaptive + pyramiding",
        "config": base_with(consensus_window_days=window, adaptive_consensus=True,
                           pyramiding_enabled=True, regime_specific=True,
                           kelly_cap_bull=0.5, kelly_cap_bear=0.15)
    })

# ═══════════════════════════════════════════════════════════════
# G. Trailing TP + Multi-day (reduce drawdown)
# ═══════════════════════════════════════════════════════════════
for window in [5, 7]:
    strategies.append({
        "name": f"V8_G1_cw{window}_trail20_8",
        "desc": f"V7 champ + cw={window}d + trailing TP 20/8",
        "config": champ_with(consensus_window_days=window, trailing_tp_activate=20, trailing_tp_drawdown=8)
    })
    strategies.append({
        "name": f"V8_G2_cw{window}_trail15_6",
        "desc": f"V7 champ + cw={window}d + trailing TP 15/6 (tighter)",
        "config": champ_with(consensus_window_days=window, trailing_tp_activate=15, trailing_tp_drawdown=6)
    })

# ═══════════════════════════════════════════════════════════════
# H. V7 Champion baseline (no multi-day, for comparison)
# ═══════════════════════════════════════════════════════════════
strategies.append({
    "name": "V8_H0_v7_champion_baseline",
    "desc": "V7 champion (no multi-day, for comparison)",
    "config": champ_with()  # consensus_window_days defaults to 0
})
strategies.append({
    "name": "V8_H1_nocontrarian_baseline",
    "desc": "V6 base no contrarian (no multi-day, for comparison)",
    "config": base_with()
})

print(f"Total V8 strategies: {len(strategies)}")
for s in strategies:
    print(f"  {s['name']:45s} {s['desc']}")

with open("backtest/v8_sweep_configs.json", "w", encoding="utf-8") as f:
    json.dump(strategies, f, ensure_ascii=False, indent=2)

print(f"\nSaved to backtest/v8_sweep_configs.json")
