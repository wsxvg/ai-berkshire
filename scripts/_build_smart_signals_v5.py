#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""基于 v5 权威标准码重建「大佬持仓模型 + 回调低吸」信号 (R21)。

与 _build_smart_signals.py 的关键区别:
  - 数据源从 trading_by_date_fixed.json (旧模糊映射) 改为
    trading_by_date_real414_v5.json (京东官方 getFundChart 权威标准码, 99.93% 覆盖率)
  - 直接使用 v5 记录的 fund_code (权威码), 不再用 get_chart_code 从 detail/name 解析,
    避免 fund_name_map 模糊匹配把基金错配成不同类型导致的信号聚合污染。

策略逻辑 (沿用 R20 回调低吸+大佬不跑):
  1. 通过交易历史构建每个大佬的逐日持仓
  2. 找出持仓中「累计投入金额最高的前 3 只基金」→ 大佬的"信心持仓"
  3. 当日基金回调(近1日跌幅)时, 检查重仓大佬是否净卖出
     - 没有净卖出(甚至净加仓) → 大佬不跑 → 真信心 → 买入信号
     - 净卖出 → 大佬跑了 → 假信心 → 忽略

输出: data/smart_money_signals.json
  {date: {chart_code: {net_buy, hold_count, topgain_hold, callback_pct}}}
"""
import json, sys, os
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

V5 = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                  "backtest", "data", "trading_by_date_real414_v5.json")
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "data", "smart_money_signals.json")

def parse_amount(s):
    if isinstance(s, (int, float)):
        return float(s)
    s = str(s).replace("元", "").replace(",", "").strip()
    try:
        return float(s)
    except ValueError:
        return 0

def main():
    print("加载 v5 交易数据...")
    with open(V5, encoding="utf-8") as f:
        tbd = json.load(f)

    dates = sorted(tbd.keys())
    print(f"{dates[0]} ~ {dates[-1]}, {len(dates)} days")

    # === 重放持仓 (增量式) ===
    print("重放持仓...")
    player_holdings = defaultdict(lambda: defaultdict(lambda: {"amount": 0.0}))
    all_players = set()

    for date in dates:
        for rec in tbd[date]:
            pid = rec.get("_uid")
            if not pid:
                continue
            fcode = rec.get("fund_code", "")
            if not fcode:
                continue
            all_players.add(pid)
            action = rec.get("action", "")
            amount = parse_amount(rec.get("amount", "0"))
            if "买入" in action or "申购" in action:
                player_holdings[pid][fcode]["amount"] += amount
            elif "卖出" in action or "赎回" in action:
                player_holdings[pid][fcode]["amount"] -= amount
                if player_holdings[pid][fcode]["amount"] < 0:
                    player_holdings[pid][fcode]["amount"] = 0

    # === 计算每个大佬的 top3 持仓 (按累计投入金额) ===
    print("计算大佬 top3 持仓...")
    player_top3 = {}
    for pid in all_players:
        holdings = [(fcode, h["amount"])
                    for fcode, h in player_holdings[pid].items()
                    if h["amount"] > 0]
        holdings.sort(key=lambda x: -x[1])
        player_top3[pid] = [h[0] for h in holdings[:3]]

    # === 逐日生成信号 ===
    print("加载净值...")
    from tools.chart_loader import load_all_charts
    charts = load_all_charts()
    # fcode -> {date: nav}
    fund_nav = {}
    for code, pts in charts.items():
        navs = {}
        for p in pts:
            y = p.get("yAxis")
            if isinstance(y, list):
                y = y[0] if y else None
            if y is not None:
                navs[p.get("xAxis", "")] = y
        fund_nav[code] = navs

    # 每只基金按日期排序的净值
    fund_nav_sorted = {c: sorted(navs.items()) for c, navs in fund_nav.items()}

    print("构建信号...")
    signals = {}

    # 逐日重放, 统计当日买卖
    holdings_now = defaultdict(lambda: defaultdict(float))  # pid -> fcode -> amount
    all_players_list = sorted(all_players)

    for i, date in enumerate(dates):
        signals[date] = {}
        day_signal = signals[date]

        # 当天交易 → 更新持仓并统计
        day_funds = defaultdict(lambda: {"buy": set(), "sell": set()})
        for rec in tbd[date]:
            pid = rec.get("_uid")
            fcode = rec.get("fund_code", "")
            if not pid or not fcode:
                continue
            action = rec.get("action", "")
            amount = parse_amount(rec.get("amount", "0"))
            if "买入" in action or "申购" in action:
                holdings_now[pid][fcode] += amount
                day_funds[fcode]["buy"].add(pid)
            elif "卖出" in action or "赎回" in action:
                holdings_now[pid][fcode] -= amount
                if holdings_now[pid][fcode] < 0:
                    holdings_now[pid][fcode] = 0
                day_funds[fcode]["sell"].add(pid)

        # 对当天有交易的基金生成信号
        for fcode, stats in day_funds.items():
            buy_pids = stats["buy"]
            sell_pids = stats["sell"]
            net_buy = len(buy_pids) - len(sell_pids)

            # hold_count: 当天持有该基金的大佬数
            hold_count = sum(1 for pid in all_players_list
                             if holdings_now[pid][fcode] > 0)

            # topgain_hold: 在 top3 持仓中且当前仍持有
            topgain_hold = 0
            for pid, top3 in player_top3.items():
                if fcode in top3 and holdings_now[pid][fcode] > 0:
                    topgain_hold += 1

            # 回调: 近1日跌幅
            callback_pct = 0.0
            navs = fund_nav_sorted.get(fcode, [])
            for j, (dt, _) in enumerate(navs):
                if dt >= date:
                    if j > 0:
                        prev_nav = navs[j - 1][1]
                        cur_nav = navs[j][1]
                        if prev_nav and prev_nav > 0:
                            callback_pct = (cur_nav / prev_nav - 1) * 100
                    break

            # 信号: 大佬在 top3 且净买入>=0
            if topgain_hold >= 2 and net_buy >= 0:
                day_signal[fcode] = {
                    "net_buy": net_buy,
                    "hold_count": hold_count,
                    "topgain_hold": topgain_hold,
                    "callback_pct": round(callback_pct, 2),
                }

        if i % 200 == 0:
            print(f"  {date}: {len(day_signal)} signals", flush=True)

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(signals, f, ensure_ascii=False)

    total_sigs = sum(len(v) for v in signals.values())
    print(f"\n信号文件: {OUT}")
    print(f"总信号数: {total_sigs}")
    print(f"平均每天: {total_sigs / len(dates):.1f} 个基金信号")

if __name__ == "__main__":
    main()