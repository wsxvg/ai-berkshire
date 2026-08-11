#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
R34 Tactical Asset Allocation Engine
=====================================
Simple monthly-rebalance momentum strategy across ~13 broad asset classes.

Signal : cross-sectional momentum (1m / 3m / 6m / 12m returns)
Regime : CSI300 above/below 200-day MA → controls risk exposure
Rebalance: monthly (every rebalance_days trading days)
Position: equal-weight top-K assets (default K=4)
Cost: 0.15% one-way (bid-ask + slippage estimate)
"""
import json, math, os, sys


def load_navseries(universe_path='data/taa_universe.json',
                   charts_path='backtest/data/fund_charts.json'):
    """Load NAV series for each asset in universe."""
    with open(universe_path) as f:
        uni = json.load(f)
    with open(charts_path) as f:
        charts = json.load(f)

    nav = {}
    meta = {}
    for a in uni['assets']:
        code = a['code']
        pts = charts.get(code, [])
        if not pts or len(pts) < 30:
            continue
        series = {}
        for p in pts:
            d = p['xAxis']
            v = float(p['yAxis'])
            if v > 0:
                series[d] = v
        if len(series) < 30:
            continue
        nav[code] = series
        meta[code] = a

    # Use a real investable ETF (CSI300 tracker) as benchmark
    bm_assets = [a for a in uni['assets'] if a['category'] == 'A_share_large']
    if bm_assets:
        bm_code = bm_assets[0]['code']
        bm_series = nav.get(bm_code, {})
    else:
        bm_code = None
        bm_series = {}
    
    print(f"[TAA] benchmark={bm_code} ({len(bm_series)} pts)", file=sys.stderr)
    return nav, meta, bm_series


def dates_aligned(nav, bm_series):
    """Get all sorted trading dates across all assets + benchmark."""
    s = set(bm_series.keys())
    for series in nav.values():
        s.update(series.keys())
    return sorted(s)


def momentum_score(nav_series, date, all_dates, lookbacks=(21, 63, 126, 252)):
    """Compute weighted momentum score as weighted avg return over lookbacks."""
    if date not in nav_series:
        return None
    nav = nav_series[date]
    if nav is None or nav <= 0:
        return None
    scores = []
    weights = []
    for lb in lookbacks:
        past_idx = None
        for j in range(len(all_dates) - 1, -1, -1):
            if all_dates[j] <= date:
                past_idx = j
                break
        if past_idx is None:
            return None
        target_idx = past_idx - lb
        if target_idx < 0:
            return None
        past_date = all_dates[target_idx]
        past_val = nav_series.get(past_date)
        if past_val is None or past_val <= 0:
            return None
        ret = (nav / past_val) - 1
        scores.append(ret)
        weights.append(1.0 / lb)
    if not scores:
        return None
    tw = sum(weights)
    return sum(s * w for s, w in zip(scores, weights)) / tw


def compute_ma(series, date, window=200):
    """Compute MA(window) for the series at given date."""
    all_dates = sorted(series.keys())
    found = None
    for j in range(len(all_dates) - 1, -1, -1):
        if all_dates[j] <= date:
            found = j
            break
    if found is None:
        return None
    if found + 1 < window:
        return None
    vals = [series[all_dates[k]] for k in range(found + 1 - window, found + 1)]
    s = sum(vals)
    return s / window


def run_taa_backtest(
    nav, meta, bm_series,
    start_date, end_date,
    rebalance_days=21,
    top_k=4,
    ma_window=200,
    bear_max_equity=0,
    cost_bps=15,
    initial_cash=10000,
):
    """Run single-period TAA backtest."""
    all_dates = dates_aligned(nav, bm_series)
    dates = [d for d in all_dates if start_date <= d <= end_date]
    if len(dates) < 2:
        return None

    cash = initial_cash
    holdings = {}  # code → shares
    nav_by_code = nav
    codes = list(nav.keys())
    total_value = initial_cash
    last_rebalance_idx = -rebalance_days
    portfolio_nav = []
    
    for i, date in enumerate(dates):
        # Compute portfolio value
        asset_value = 0
        for code in list(holdings.keys()):
            price = nav_by_code[code].get(date)
            if price is None:
                prev_dates = [d for d in sorted(nav_by_code[code].keys()) if d <= date]
                if prev_dates:
                    price = nav_by_code[code][prev_dates[-1]]
            if price is not None:
                asset_value += holdings[code] * price
        
        total_value = cash + asset_value
        
        # Check if rebalance day (allow initial buy at i=0; momentum_score
        # returns None for assets lacking sufficient history → natural filter)
        if (i - last_rebalance_idx) >= rebalance_days:
            bm_price = bm_series.get(date)
            bm_ma = compute_ma(bm_series, date, ma_window)
            regime = "bull" if (bm_price and bm_ma and bm_price > bm_ma) else "bear"
            
            # Score all assets
            scored = []
            for code in codes:
                score = momentum_score(nav[code], date, all_dates)
                if score is not None:
                    scored.append((code, score))
            
            scored.sort(key=lambda x: x[1], reverse=True)
            
            # Pick top-K
            selected = scored[:top_k]
            
            # In bear regime, prefer non-equity assets (bonds, gold, cash)
            if regime == "bear" and bear_max_equity == 0:
                safety_codes = set()
                for cat in ('CN_bond', 'CN_credit', 'cash', 'commodity'):
                    for code in codes:
                        if meta.get(code, {}).get('category') == cat:
                            safety_codes.add(code)
                safety_scored = [(c, s) for c, s in scored if c in safety_codes]
                if safety_scored:
                    selected = safety_scored[:top_k]
            
            if not selected:
                last_rebalance_idx = i
                portfolio_nav.append(total_value)
                continue
            
            # Sell all current holdings
            sell_cost = 0
            for code in list(holdings.keys()):
                price = nav_by_code[code].get(date)
                if price is None:
                    prev_dates = [d for d in sorted(nav_by_code[code].keys()) if d <= date]
                    price = nav_by_code[code][prev_dates[-1]] if prev_dates else None
                if price and holdings[code] > 0:
                    proceeds = holdings[code] * price
                    sell_cost += proceeds * cost_bps / 10000
                    cash += proceeds
                del holdings[code]
            
            cash -= sell_cost
            
            # Buy new targets
            n_sel = len(selected)
            target_alloc = 1.0 / n_sel
            buy_budget = cash
            
            for code, score in selected:
                alloc_value = buy_budget * target_alloc
                price = nav_by_code[code].get(date)
                if price is None:
                    prev_dates = [d for d in sorted(nav_by_code[code].keys()) if d <= date]
                    price = nav_by_code[code][prev_dates[-1]] if prev_dates else None
                if price and price > 0:
                    shares = alloc_value / price
                    cost = alloc_value * cost_bps / 10000
                    holdings[code] = shares
                    cash -= (alloc_value + cost)
            
            last_rebalance_idx = i
        
        portfolio_nav.append(total_value)
    
    if len(portfolio_nav) < 2:
        return None
    
    final_val = portfolio_nav[-1]
    total_return = (final_val / initial_cash - 1) * 100
    
    peak = portfolio_nav[0]
    max_dd = 0
    for v in portfolio_nav:
        if v > peak:
            peak = v
        dd = (peak - v) / peak * 100
        if dd > max_dd:
            max_dd = dd
    
    # Benchmark return over same period using common dates
    bm_dates_in_window = [d for d in sorted(bm_series.keys()) if start_date <= d <= end_date]
    bm_return = 0
    if len(bm_dates_in_window) >= 2:
        bm_start = bm_series[bm_dates_in_window[0]]
        bm_end = bm_series[bm_dates_in_window[-1]]
        if bm_start > 0:
            bm_return = (bm_end / bm_start - 1) * 100
    
    days = len(dates)
    years = days / 252.0
    if years > 0 and final_val > 0:
        ann_return = ((final_val / initial_cash) ** (1 / years) - 1) * 100
    else:
        ann_return = total_return
    
    return {
        "period": f"{dates[0]}~{dates[-1]}",
        "return": round(total_return, 3),
        "ann_return": round(ann_return, 3),
        "max_drawdown": round(max_dd, 3),
        "benchmark": round(bm_return, 3),
        "days": days,
        "final_value": round(final_val, 2),
    }


if __name__ == "__main__":
    """Quick smoke test."""
    nav, meta, bm_series = load_navseries()
    print(f"Loaded {len(nav)} assets")
    for code in sorted(nav.keys(), key=lambda c: len(nav[c]), reverse=True):
        name = meta[code]['name']
        print(f"  {code}: {name} ({len(nav[code])} pts)")
    
    res = run_taa_backtest(
        nav, meta, bm_series,
        start_date="2024-06-01", end_date="2025-06-01",
        rebalance_days=21, top_k=4, cost_bps=15
    )
    if res:
        print(f"\nTest: {res['period']}")
        print(f"  Return: {res['return']:+.2f}%  Ann: {res['ann_return']:+.2f}%")
        print(f"  MaxDD: {res['max_drawdown']:.2f}%  Benchmark: {res['benchmark']:+.2f}%")
        print(f"  Days: {res['days']}  Final: {res['final_value']}")
    else:
        print("No result (insufficient data)")
