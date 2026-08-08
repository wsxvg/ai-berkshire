#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
构建「大佬持仓模型 + 回调低吸」信号

策略逻辑 (用户提出):
1. 通过交易历史构建每个大佬的逐日持仓
2. 找出持仓中「累计收益最高的前 3 只基金」→ 大佬的"核心持仓/信心持仓"
3. 当前一日基金跌 X% (回调) 时触发观察
4. 检查这些重仓大佬的操作:
     - 没有净卖出(甚至净加仓) → 大佬不跑 → 真信心 → 买入信号
     - 净卖出 → 大佬跑了 → 可能是假信心 → 忽略

输出: data/smart_money_signals.json
  每日每基金的信号: {
    date: {
      chart_code: {
        "net_buy_players": 5,  # 当日净买入人数
        "hold_players": 12,    # 当日持有该基金的大佬数
        "topgain_hold": 3,     # 在大佬 gain_top3 持仓中的大佬数
        "callback_pct": -5.2,  # 近1日跌幅(%)
      }
    }
  }

回测引擎修改:
  scoring函数加分:
    if callback_pct <= -threshold and topgain_hold >= 2 and net_buy >= 0:
        score += BONUS * topgain_hold
"""
import json, sys, re, os
from collections import defaultdict
from datetime import datetime, timedelta

sys.path.insert(0, '.')

# === 加载映射 ===
with open('data/jdcode_to_chart.json', encoding='utf-8') as f:
    jdcode_to_chart = json.load(f)
with open('data/eastmoney_all_funds.json', encoding='utf-8') as f:
    name_to_chart_raw = {}
    for fund in json.load(f):
        code = str(fund.get('code', ''))
        name = fund.get('name', '')
        if code and name:
            name_to_chart_raw[name] = code

print(f"映射表: jdcode→chart {len(jdcode_to_chart)}, name→chart {len(name_to_chart_raw)}")

def get_chart_code(rec):
    """从交易记录提取 chart_code"""
    detail = rec.get('detail', '')
    m = re.search(r'基金(\d+)', detail)
    if m and m.group(1) in jdcode_to_chart:
        return jdcode_to_chart[m.group(1)]
    fund_name = rec.get('fund_name', '')
    if fund_name in name_to_chart_raw:
        return name_to_chart_raw[fund_name]
    return None

def parse_amount(s):
    if isinstance(s, (int, float)):
        return float(s)
    s = str(s).replace('元', '').replace(',', '').strip()
    try:
        return float(s)
    except ValueError:
        return 0

# === 加载交易数据 ===
print("加载交易数据...")
with open('backtest/data/trading_by_date_fixed.json', encoding='utf-8') as f:
    tbd = json.load(f)

dates = sorted(tbd.keys())
print(f"{dates[0]} ~ {dates[-1]}, {len(dates)} days")

# === 重放持仓 (增量式) ===
print("重放持仓...")
# pid -> fcode -> {"amount": 累计投入, "shares": 份额, "last_buy_cost": 最近买入成本}
player_holdings = defaultdict(lambda: defaultdict(lambda: {"amount": 0.0, "cost": 0.0}))
# 每日交易统计
daily_stats = {}  # date -> {fcode: {"buy_pids": set(), "sell_pids": set(), "amount": float}}

all_players = set()
fund_holdings_count = defaultdict(int)  # fcode -> 持有该基金的大佬数 (每日更新)

# 先按日期重放
for date in dates:
    txns = tbd[date]
    day_funds = defaultdict(lambda: {"buy": set(), "sell": set(), "amount": 0.0})
    
    for rec in txns:
        pid = rec.get('_uid')
        if not pid:
            continue
        all_players.add(pid)
        fcode = get_chart_code(rec)
        if not fcode:
            continue
        action = rec.get('action', '')
        amount = parse_amount(rec.get('amount', '0'))
        
        if '买入' in action or '申购' in action:
            day_funds[fcode]["buy"].add(pid)
            player_holdings[pid][fcode]["amount"] += amount
            player_holdings[pid][fcode]["cost"] += amount
        elif '卖出' in action or '赎回' in action:
            day_funds[fcode]["sell"].add(pid)
            player_holdings[pid][fcode]["amount"] -= amount
            # 清仓检测
            if player_holdings[pid][fcode]["amount"] <= 0:
                player_holdings[pid][fcode]["amount"] = 0
                player_holdings[pid][fcode]["cost"] = 0
    
    # 计算当天持有 count (对当天有交易的基金)
    for fcode in day_funds:
        buy_pids = day_funds[fcode]["buy"]
        sell_pids = day_funds[fcode]["sell"]
        # 更新持有数 = 之前的持有数 + 新买入 - 新卖出
        # 简化: 对当天有交易的大佬重新计算是否持有
        new_hold_count = 0
        for pid in all_players:
            if player_holdings[pid][fcode]["amount"] > 0:
                new_hold_count += 1
        fund_holdings_count[fcode] = new_hold_count
        
        net_buy = len(buy_pids) - len(sell_pids)
        day_funds[fcode]["net_buy"] = net_buy
        day_funds[fcode]["hold_count"] = new_hold_count
    
    daily_stats[date] = dict(day_funds)

# === 计算每个大佬的 gain_top3 持仓 ===
print("计算大佬 gain_top3...")
# 加载基金净值 (用于估算持仓市值)
from tools.chart_loader import load_all_charts
charts = load_all_charts()
# 建立净值查找
fund_nav = {}
for code, pts in charts.items():
    fund_nav[code] = {}
    for p in pts:
        fund_nav[code][p['xAxis']] = p['yAxis'][0] if isinstance(p['yAxis'], list) else p['yAxis']

# 取最新日期的价格估算
latest_date = dates[-1]
player_topgain = {}  # pid -> [top3 chart_codes]

for pid in all_players:
    holdings = []
    for fcode, holding in player_holdings[pid].items():
        if holding["cost"] > 0 and holding["amount"] > 0:
            # 估算当前市值
            price_latest = fund_nav.get(fcode, {}).get(latest_date, 0)
            # 估算份额 (简化：amount / price_at_purchase ~ amount/cost)
            # 由于没有完整的份额和净值时间序列, 简化: 用 amount 排名
            holdings.append((fcode, holding["amount"]))
    
    # 按持仓金额 top3
    holdings.sort(key=lambda x: -x[1])
    player_topgain[pid] = [h[0] for h in holdings[:3]]

print(f"有 gain_top3 的大佬数: {len([p for p in player_topgain if player_topgain[p]])}")

# === 构建信号 ===
print("构建信号...")
signals = {}
last_nav = {}  # fcode -> {date: nav}

# 对每只基金, 找到每日净值计算跌幅
# 优化: 只对有交易的基金计算
for i, date in enumerate(dates):
    signals[date] = {}
    day_signal = signals[date]
    
    # 当天有交易的基金
    traded_funds = daily_stats.get(date, {})
    if not traded_funds:
        continue
    
    for fcode, stats in traded_funds.items():
        net_buy = stats["net_buy"]
        hold_count = stats["hold_count"]
        buy_pids = stats["buy"]
        sell_pids = stats["sell"]
        
        # 计算 topgain 中有多少大佬今天持有 fcode
        topgain_hold = 0
        for pid, top3 in player_topgain.items():
            if fcode in top3 and player_holdings[pid][fcode]["amount"] > 0:
                topgain_hold += 1
        
        # 计算回调: 需要前一天的 NAV
        callback_pct = 0
        if fcode in fund_nav:
            navs = fund_nav[fcode]
            dts = sorted(navs.keys())
            idx = dts.index(date) if date in dts else -1
            if idx > 0:
                prev_nav = navs[dts[idx-1]]
                cur_nav = navs[dts[idx]]
                if prev_nav > 0:
                    callback_pct = (cur_nav / prev_nav - 1) * 100
        
        # 信号: 只有大佬净买入/持有 且 在 topgain 中 才有意义
        if topgain_hold >= 2 and net_buy >= 0:
            day_signal[fcode] = {
                "net_buy": net_buy,
                "hold_count": hold_count,
                "topgain_hold": topgain_hold,
                "callback_pct": round(callback_pct, 2),
            }

    if i % 200 == 0:
        print(f"  {date}: {len(day_signal)} signals")

# 输出
os.makedirs('data', exist_ok=True)
out_path = 'data/smart_money_signals.json'
with open(out_path, 'w', encoding='utf-8') as f:
    json.dump(signals, f, ensure_ascii=False, indent=2)

print(f"\n信号文件: {out_path}")
total_sigs = sum(len(v) for v in signals.values())
print(f"总信号数: {total_sigs}")
print(f"平均每天: {total_sigs/len(dates):.1f} 个基金信号")
