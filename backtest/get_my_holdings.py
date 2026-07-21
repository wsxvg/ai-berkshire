#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""获取用户持仓数据并分析"""
import json, sys, os
from pathlib import Path

os.chdir("c:/fund")

# 1. 查看watchlist_mine (自选基金)
print("=" * 70)
print("1. 自选基金 (watchlist_mine.json)")
print("=" * 70)
wl = json.load(open("data/fund_cache/watchlist_mine.json", "r", encoding="utf-8"))
funds = wl.get("funds", [])
print(f"共{len(funds)}只基金\n")
print(f"{'代码':<10} {'名称':<25} {'日收益%':>8} {'周收益%':>8} {'月收益%':>8}")
print("-" * 70)
for f in funds[:30]:
    code = f.get("fund_code", "")
    name = f.get("fund_name", "")[:23]
    day_r = f.get("day_return", 0)
    wk_r = f.get("week_return", 0)
    mo_r = f.get("month_return", 0)
    print(f"{code:<10} {name:<25} {day_r:>8.2f} {wk_r:>8.2f} {mo_r:>8.2f}")

# 2. 尝试从JD Finance API获取用户持仓
print(f"\n{'=' * 70}")
print("2. 尝试获取用户实际持仓 (JD Finance API)")
print("=" * 70)

# 检查cookie是否有效
cookie_path = Path("data/jd_auth/cookies.json")
if cookie_path.exists():
    print("Cookie文件存在，尝试获取持仓...")
    # 读取cookie
    with open(cookie_path, "r", encoding="utf-8") as f:
        cookie_data = json.load(f)
    # 检查是否有uid
    uid = cookie_data.get("uid", "")
    if uid:
        print(f"用户ID: {uid}")
        # 尝试调用API
        try:
            sys.path.insert(0, ".")
            from tools.jd_finance_api import JDFinanceAPI
            api = JDFinanceAPI()
            result = api.get_user_holdings(uid)
            if result:
                holdings = result.get("holdings", result.get("data", []))
                print(f"持仓数量: {len(holdings)}")
                for h in holdings:
                    code = h.get("fundCode", h.get("code", ""))
                    name = h.get("fundName", h.get("name", ""))[:20]
                    shares = h.get("shares", h.get("holdShares", 0))
                    cost = h.get("costNav", h.get("cost", 0))
                    cur_nav = h.get("nav", h.get("latestNav", 0))
                    buy_date = h.get("buyDate", h.get("purchaseDate", ""))
                    profit = h.get("profit", h.get("totalProfit", 0))
                    ret_pct = h.get("returnRate", h.get("profitRate", 0))
                    print(f"  {code} {name} 买入={buy_date} 份额={shares} 成本={cost} 净值={cur_nav} 收益={profit}({ret_pct}%)")
            else:
                print("获取持仓失败（cookie可能过期）")
        except Exception as e:
            print(f"API调用失败: {e}")
    else:
        print("Cookie中无uid，无法获取持仓")
else:
    print("Cookie文件不存在")

# 3. 从fund_snapshots获取最新持仓快照
print(f"\n{'=' * 70}")
print("3. 持仓快照 (fund_snapshots)")
print("=" * 70)
snap_dir = Path("data/fund_snapshots")
if snap_dir.exists():
    snaps = sorted(snap_dir.glob("*.json"), reverse=True)
    if snaps:
        print(f"最新快照: {snaps[0].name}")
        with open(snaps[0], "r", encoding="utf-8") as f:
            snap = json.load(f)
        if isinstance(snap, list):
            print(f"持仓数量: {len(snap)}")
            for h in snap[:20]:
                code = h.get("code", h.get("fund_code", ""))
                name = h.get("name", h.get("fund_name", ""))[:20]
                shares = h.get("shares", h.get("hold_shares", 0))
                cost = h.get("cost", h.get("cost_nav", 0))
                cur_nav = h.get("nav", h.get("latest_nav", 0))
                ret = h.get("return", h.get("profit", 0))
                ret_pct = h.get("return_pct", h.get("profit_rate", 0))
                buy_date = h.get("buy_date", h.get("purchase_date", ""))
                print(f"  {code} {name} 买入={buy_date} 成本={cost} 净值={cur_nav} 收益={ret}({ret_pct}%)")
        elif isinstance(snap, dict):
            for k, v in list(snap.items())[:5]:
                print(f"  {k}: {v}")
    else:
        print("无快照文件")
else:
    print("快照目录不存在")

# 4. 从sim报告获取最近持仓
print(f"\n{'=' * 70}")
print("4. 最近模拟报告中的持仓")
print("=" * 70)
sim_dir = Path("reports/sim")
if sim_dir.exists():
    sim_files = sorted([f for f in sim_dir.glob("*.json") if "2026-07" in f.name], reverse=True)
    if not sim_files:
        sim_files = sorted([f for f in sim_dir.glob("*.json") if "2026-06" in f.name], reverse=True)
    if sim_files:
        latest = sim_files[0]
        print(f"最近报告: {latest.name}")
        with open(latest, "r", encoding="utf-8") as f:
            sim = json.load(f)
        holdings = sim.get("holdings", sim.get("portfolio", {}).get("holdings", []))
        if isinstance(holdings, dict):
            holdings = list(holdings.values())
        print(f"持仓数量: {len(holdings)}")
        for h in holdings[:20]:
            code = h.get("code", h.get("fund_code", ""))
            name = h.get("name", h.get("fund_name", ""))[:20]
            shares = h.get("shares", 0)
            buy_nav = h.get("buy_nav", h.get("cost", 0))
            cur_nav = h.get("nav", h.get("current_nav", 0))
            cum_ret = h.get("cum_return", h.get("return_pct", 0))
            buy_date = h.get("buy_date", h.get("purchase_date", ""))
            print(f"  {code} {name} 买入={buy_date} 买入净值={buy_nav} 当前净值={cur_nav} 收益={cum_ret}%")
    else:
        print("无最近模拟报告")
else:
    print("模拟报告目录不存在")
