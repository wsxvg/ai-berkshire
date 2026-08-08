#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
审计关注池「大佬」的真实质量 — 过滤风口型伪大佬

检验维度:
1. 交易行为: 换手率、持仓集中度、是否追涨杀跌
2. 收益质量: 是否持续产生 alpha，还是仅靠单只基金爆发
3. 行为一致性: 是否有稳定的投资哲学，还是风格漂移
"""
import json
import sys
import re
from collections import defaultdict
from datetime import datetime

sys.path.insert(0, '.')

# === 1. 加载交易数据 ===
with open('backtest/data/trading_history_fixed.json', 'r', encoding='utf-8') as f:
    trades = json.load(f)

print(f"=== 交易记录总览 ===")
print(f"总交易笔数: {len(trades)}")

# 字段检查
if trades:
    print(f"字段: {list(trades[0].keys())[:10]}")
    print(f"样例: {trades[0]}")

# === 2. 加载交易 by date ===
with open('backtest/data/trading_by_date_fixed.json', 'r', encoding='utf-8') as f:
    tbd = json.load(f)

dates = sorted(tbd.keys())
print(f"\n=== 日期覆盖 ===")
print(f"{dates[0]} ~ {dates[-1]} ({len(dates)} days)")

# 每天有多少大佬在交易
sample_date = dates[len(dates)//2]
daily = tbd[sample_date]
print(f"\n{sample_date} 当日交易数: {len(daily)}")
if daily:
    print(f"交易样例: {daily[0]}")

# === 3. 加载基金净值 (用于计算收益) ===
from tools.chart_loader import load_all_charts
charts = load_all_charts()
print(f"\n基金数: {len(charts)}")

# === 4. 构建每只基金的日净值查找 ===
fund_nav = {}
for code, pts in charts.items():
    fund_nav[code] = {}
    for p in pts:
        fund_nav[code][p['xAxis']] = p['yAxis'][0] if isinstance(p['yAxis'], list) else p['yAxis']

# === 5. 分析每个大佬的交易行为 ===
# 数据结构: {大佬ID: {fund_code: [{date, direction, amount}, ...]}}
players = defaultdict(lambda: defaultdict(list))

for d in dates:
    for rec in tbd[d]:
        pid = rec.get('_uid') or rec.get('user_id') or rec.get('id')
        # detail 可能包含 "基金XXXXXX" 基金代码
        detail = rec.get('detail', '')
        fund_name = rec.get('fund_name', '')
        direction = rec.get('action') or rec.get('type') or rec.get('direction')
        amount_str = rec.get('amount', '0').replace('元', '').replace(',', '')
        try:
            amount = float(amount_str)
        except ValueError:
            amount = 0
        # 提取基金代码
        fcode = ''
        if '基金' in detail:
            m = re.search(r'基金(\d+)', detail)
            if m:
                fcode = m.group(1)
        if not fcode and fund_name:
            # 尝试从 charts 里匹配
            fcode = fund_name  # fallback
        if pid and fcode:
            players[pid][fcode].append({
                'date': d,
                'direction': direction,
                'amount': amount,
                'fund_name': fund_name,
                'raw': rec
            })

print(f"\n=== 大佬人数 ===")
print(f"独立大佬数: {len(players)}")

# === 6. 统计每个大佬的风格指标 ===
metrics = []
for pid, holdings in players.items():
    total_trades = sum(len(t) for t in holdings.values())
    unique_funds = len(holdings)
    
    # 平均持仓天数 (简化)
    hold_days = []
    for fcode, trade_list in holdings.items():
        if len(trade_list) >= 2:
            d0 = datetime.strptime(trade_list[0]['date'], '%Y-%m-%d')
            d1 = datetime.strptime(trade_list[-1]['date'], '%Y-%m-%d')
            hold_days.append((d1 - d0).days)
    
    avg_hold = sum(hold_days) / len(hold_days) if hold_days else 0
    max_hold = max(hold_days) if hold_days else 0
    
    # 换手率 proxy: 交易次数 / 基金数
    turnover = total_trades / unique_funds if unique_funds else 0
    
    # 单基金集中持仓 (只交易 1-2 只基金 = 超级集中)
    concentration = 1 / unique_funds if unique_funds else 0
    
    metrics.append({
        'pid': pid,
        'total_trades': total_trades,
        'unique_funds': unique_funds,
        'avg_hold_days': avg_hold,
        'max_hold_days': max_hold,
        'turnover': turnover,
        'concentration': concentration,
    })

# === 7. 输出分布 ===
print(f"\n=== 交易行为分布 ===")
trades_list = [m['total_trades'] for m in metrics]
funds_list = [m['unique_funds'] for m in metrics]
hold_list = [m['avg_hold_days'] for m in metrics if m['avg_hold_days'] > 0]

import statistics

def stats(data, name):
    if not data:
        print(f"  {name}: 无数据")
        return
    print(f"  {name}: median={statistics.median(data):.0f}, mean={statistics.mean(data):.1f}, "
          f"min={min(data):.0f}, max={max(data):.0f}, p25={sorted(data)[len(data)//4]:.0f}, p75={sorted(data)[3*len(data)//4]:.0f}")

stats(trades_list, "总交易笔数")
stats(funds_list, "持仓基金数")
stats(hold_list, "平均持有天数")

# === 8. 过滤: 识别伪大佬 ===
# 可疑特征:
# - 交易笔数 < 5 (数据太少，无法评估)
# - 持仓基金数 == 1 (单押，可能是赌徒)
# - 平均持有 < 7 天 (短线炒作)
# - 换手率 > 10 (过度交易)

real_big = []
suspicious = []
no_data = []

for m in metrics:
    if m['total_trades'] < 5:
        no_data.append(m)
    elif m['unique_funds'] <= 2 and m['total_trades'] > 20:
        # 只玩 1-2 只基金但交易频繁 = 短线炒单，不是真大佬
        suspicious.append(('high_frequency_single', m))
    elif m['avg_hold_days'] < 5 and m['total_trades'] > 10:
        # 超短线
        suspicious.append(('ultra_short', m))
    elif m['turnover'] > 15:
        suspicious.append(('excessive_trading', m))
    else:
        real_big.append(m)

print(f"\n=== 质量分层 ===")
print(f"有效大佬 (可评估): {len(real_big)}")
print(f"可疑 (疑似风口型/赌徒): {len(suspicious)}")
print(f"数据不足 (交易<5笔): {len(no_data)}")

if suspicious:
    print(f"\n--- 可疑大佬样本 ---")
    for reason, m in suspicious[:10]:
        print(f"  [{reason}] pid={m['pid'][:8]}... trades={m['total_trades']} funds={m['unique_funds']} "
              f"avg_hold={m['avg_hold_days']:.0f}d turnover={m['turnover']:.1f}")

# === 9. 保存过滤后的名单 ===
legit_ids = set(m['pid'] for m in real_big)
output = {
    "audit_date": dates[-1],
    "total_players": len(players),
    "legit_big_players": len(real_big),
    "suspicious": len(suspicious),
    "no_data": len(no_data),
    "legit_pids": sorted(legit_ids),
    "suspicious_detail": [
        {"reason": r, "pid": m['pid'], "trades": m['total_trades'], "funds": m['unique_funds']}
        for r, m in suspicious[:20]
    ]
}
with open('data/big_player_audit.json', 'w', encoding='utf-8') as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

print(f"\n审核结果保存至 data/big_player_audit.json")
print(f"建议: 仅保留 {len(real_big)} 位 '有效大佬' 的信号作为 smart_money 维度")
