#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""每日利润保护监控器 — 检查持仓是否触及卖出条件

每天运行一次，输出需要卖出的基金列表。
基于回测验证有效的卖出规则：
  1. 动量崩溃: 动量分<1.5且市场非牛市 → 卖
  2. 浮盈回撤: 浮盈>20%后从高点回撤>15% → 卖
  3. 止损: 亏损>-30% → 卖
  4. 动量衰退: 连续5天动量下降 → 关注

用法: python tools/profit_monitor.py
"""
import sys, os, json, statistics
from datetime import datetime
from pathlib import Path

os.chdir("c:/fund")
sys.path.insert(0, ".")

# 加载持仓数据
def load_holdings():
    """从最新的持仓缓存加载"""
    # 尝试从fund_cache加载
    cache_dir = Path("data/fund_cache")
    for f in sorted(cache_dir.glob("holdings_*.json"), reverse=True):
        with open(f, "r", encoding="utf-8") as fh:
            return json.load(fh)
    # 尝试从watchlist加载
    wl_path = Path("data/fund_cache/watchlist_mine.json")
    if wl_path.exists():
        with open(wl_path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    return {}

def load_fund_chart(code):
    """加载基金净值数据"""
    charts_path = Path("backtest/data/fund_charts.json")
    if not hasattr(load_fund_chart, "_cache"):
        with open(charts_path, "r", encoding="utf-8") as f:
            load_fund_chart._cache = json.load(f)
    return load_fund_chart._cache.get(code, [])

def compute_rsi(nav_values, period=14):
    if len(nav_values) < period + 1:
        return 50.0
    deltas = [nav_values[i] - nav_values[i-1] for i in range(1, len(nav_values))]
    recent = deltas[-period:]
    gains = [d for d in recent if d > 0]
    losses = [-d for d in recent if d < 0]
    avg_gain = sum(gains) / period if gains else 0
    avg_loss = sum(losses) / period if losses else 0
    if avg_loss == 0:
        return 100.0
    return 100 - (100 / (1 + avg_gain / avg_loss))

def compute_momentum_score(pts, cutoff_date):
    """简化版动量评分"""
    valid = [p for p in pts if p.get("xAxis", "") <= cutoff_date]
    if len(valid) < 60:
        return 3.0
    values = [float(p.get("yAxis", 0)) for p in valid]
    cur = values[-1]
    # 近20日收益率
    ret_20 = cur - values[-20] if len(values) >= 20 else 0
    # 近60日收益率
    ret_60 = cur - values[-60] if len(values) >= 60 else 0
    # RSI
    navs = [(100 + v) / 100 for v in values]
    rsi = compute_rsi(navs, 14)
    # 简化评分
    score = 2.5
    if ret_20 > 5: score += 0.5
    if ret_20 > 10: score += 0.5
    if ret_60 > 10: score += 0.5
    if rsi > 60: score += 0.5
    if rsi < 40: score -= 0.5
    if ret_20 < 0: score -= 0.5
    return min(5.0, max(0.0, score))

def detect_market_state(cutoff_date):
    """简化版市场状态检测"""
    # 用沪深300作为基准
    charts_path = Path("backtest/data/fund_charts.json")
    if not hasattr(detect_market_state, "_bm"):
        with open(charts_path, "r", encoding="utf-8") as f:
            all_charts = json.load(f)
        # 找沪深300
        for code, pts in all_charts.items():
            if "沪深300" in str(pts[:1]) or "510300" in code or "511300" in code:
                detect_market_state._bm = pts
                break
        if not hasattr(detect_market_state, "_bm"):
            # 用任意大盘基金作为代理
            detect_market_state._bm = list(all_charts.values())[0] if all_charts else []
    
    bm = detect_market_state._bm
    valid = [p for p in bm if p.get("xAxis", "") <= cutoff_date]
    if len(valid) < 60:
        return "neutral"
    values = [float(p.get("yAxis", 0)) for p in valid]
    ret_60 = values[-1] - values[-60]
    if ret_60 > 8:
        return "bull"
    elif ret_60 < -5:
        return "bear"
    return "neutral"

def main():
    today = datetime.now().strftime("%Y-%m-%d")
    print(f"\n{'='*60}")
    print(f"利润保护监控器 — {today}")
    print(f"{'='*60}")
    
    holdings = load_holdings()
    if not holdings:
        print("未找到持仓数据")
        return
    
    market_state = detect_market_state(today)
    print(f"市场状态: {market_state}")
    print(f"持仓数量: {len(holdings) if isinstance(holdings, list) else len(holdings)}")
    print()
    
    alerts = []
    
    # 处理持仓列表
    holding_list = holdings if isinstance(holdings, list) else holdings.get("holdings", [])
    
    for h in holding_list:
        code = h.get("code", h.get("fund_code", ""))
        name = h.get("name", h.get("fund_name", ""))[:20]
        buy_nav = h.get("buy_nav", h.get("cost_nav", 1.0))
        buy_date = h.get("buy_date", h.get("purchase_date", ""))
        
        pts = load_fund_chart(code)
        if not pts:
            continue
        
        valid = [p for p in pts if p.get("xAxis", "") <= today]
        if not valid:
            continue
        
        cur_nav = (100 + float(valid[-1].get("yAxis", 0))) / 100
        cum_return = (cur_nav / buy_nav - 1) * 100 if buy_nav > 0 else 0
        
        # 计算峰值和回撤
        nav_values = [(100 + float(p.get("yAxis", 0))) / 100 for p in valid]
        peak = max(nav_values)
        drawdown_from_peak = (cur_nav / peak - 1) * 100 if peak > 0 else 0
        
        # 动量分
        mom_score = compute_momentum_score(pts, today)
        
        # RSI
        rsi = compute_rsi(nav_values, 14)
        
        status = "HOLD"
        reason = ""
        
        # 规则1: 动量崩溃（非牛市）
        if mom_score < 1.5 and market_state != "bull":
            status = "SELL"
            reason = f"动量崩溃 mom={mom_score:.2f} (非牛市)"
        
        # 规则2: 浮盈回撤
        elif cum_return > 20 and drawdown_from_peak < -15:
            status = "SELL"
            reason = f"浮盈回撤 profit={cum_return:.1f}% dd={drawdown_from_peak:.1f}%"
        
        # 规则3: 止损
        elif cum_return < -30:
            status = "SELL"
            reason = f"止损 return={cum_return:.1f}%"
        
        # 规则4: 动量衰退警告
        elif mom_score < 2.0 and cum_return > 10:
            status = "WATCH"
            reason = f"动量衰退 mom={mom_score:.2f} profit={cum_return:.1f}%"
        
        # 规则5: RSI超买警告
        elif rsi > 80 and cum_return > 15:
            status = "WATCH"
            reason = f"RSI超买 rsi={rsi:.0f} profit={cum_return:.1f}%"
        
        if status != "HOLD":
            alerts.append({
                "status": status,
                "code": code,
                "name": name,
                "return": cum_return,
                "drawdown": drawdown_from_peak,
                "mom": mom_score,
                "rsi": rsi,
                "reason": reason,
            })
        
        # 打印所有持仓状态
        marker = {"SELL": "❌卖", "WATCH": "⚠️关注", "HOLD": "✅持有"}[status]
        print(f"  {marker} {name:<20} ret={cum_return:>6.1f}% dd={drawdown_from_peak:>6.1f}% mom={mom_score:.1f} rsi={rsi:.0f} {reason}")
    
    # 汇总
    print(f"\n{'='*60}")
    sell_list = [a for a in alerts if a["status"] == "SELL"]
    watch_list = [a for a in alerts if a["status"] == "WATCH"]
    
    if sell_list:
        print(f"\n🚨 需要立即卖出 ({len(sell_list)}只):")
        for a in sell_list:
            print(f"  {a['name']} ({a['code']}) — {a['reason']}")
    
    if watch_list:
        print(f"\n⚠️ 需要关注 ({len(watch_list)}只):")
        for a in watch_list:
            print(f"  {a['name']} ({a['code']}) — {a['reason']}")
    
    if not sell_list and not watch_list:
        print("\n✅ 所有持仓正常，无需操作")
    
    print(f"\n{'='*60}")
    print(f"规则说明:")
    print(f"  ❌卖出: 动量<1.5(非牛市) / 浮盈>20%后回撤>15% / 亏损>30%")
    print(f"  ⚠️关注: 动量<2.0且盈利>10% / RSI>80且盈利>15%")
    print(f"  ✅持有: 以上条件均未触发")
    print(f"\n每天运行: python tools/profit_monitor.py")

if __name__ == "__main__":
    main()
