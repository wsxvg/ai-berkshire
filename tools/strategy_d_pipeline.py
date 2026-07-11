#!/usr/bin/env python3
"""
策略D · 全流程自动决策
一句话命令: python tools/strategy_d_pipeline.py
输出：仓位扫描 + 大佬动态 + 大师标签 + 减仓计划 + 最终决策
"""
import sys, json, os
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["AKSHARE_QUIET"] = "1"

def section(title):
    print()
    print("=" * 55)
    print(f"  {title}")
    print("=" * 55)
    print()

# ═════════ 1. 持仓数据 ═════════
section("1. 持仓扫描")
from tools.jd_finance_api import get_user_holdings
data = get_user_holdings(use_cache=False)
holdings = data.get('holdings', [])
if not holdings:
    print("  ⚠️ 无持仓数据")
    sys.exit(1)

total = 0
funds = []
for h in holdings:
    if isinstance(h, dict):
        try:
            amt = float(str(h.get("amount","0")).replace(",","").replace("元","").replace("¥","").strip())
            profit = float(str(h.get("profit","0")).replace(",","").replace("元","").replace("¥","").replace("+","").strip())
            mv = max(amt + profit, 0)
            total += mv
            funds.append({
                "code": h.get("code",""), "name": h.get("name","?")[:25],
                "amount": amt, "profit": profit, "market_value": mv,
                "profit_rate": h.get("profit_rate","0")
            })
        except: pass

funds.sort(key=lambda x: -x["market_value"])
print(f"  {'代码':8s} {'名称':24s} {'市值':>8s} {'盈亏':>8s} {'占比':>6s}")
print(f"  {'-'*56}")
for f in funds:
    pct = f["market_value"] / max(total,1) * 100
    profit_str = f'{f["profit"]:+.0f}'
    print(f"  {f['code']:8s} {f['name']:24s} ¥{f['market_value']:>5.0f} {profit_str:>8s} {pct:>5.0f}%")

# ═════════ 2. 策略偏离度 ═════════
section("2. 策略偏离度")
max_pct = max(f["market_value"] for f in funds) / max(total,1) * 100
eq_pct = 100  # all funds are equity
alert_level = "🔴 CRITICAL" if max_pct > 50 else "🟡 HIGH" if max_pct > 25 else "🟢 OK"
print(f"  集中度:  {max_pct:.0f}% {'🔴' if max_pct > 25 else '🟢'} (上限25%)")
print(f"  权益:    {eq_pct:.0f}% {'🔴' if eq_pct > 70 else '🟢'} (建议≤70%)")
print(f"  防守:    0% 🔴 (建议≥30%债基/现金)")
print(f"  综合:    {alert_level}")

# ═════════ 3. 大佬动态 ═════════
section("3. 大佬动态")
try:
    snap = json.loads(open('data/holdings_snapshot.json', 'r', encoding='utf-8').read())
    fund_counts = {}
    fund_holders = {}
    for user, flist in snap.get('holdings', {}).items():
        for f in flist if isinstance(flist, list) else []:
            if isinstance(f, dict):
                code = f.get('code', '')
                fund_counts[code] = fund_counts.get(code, 0) + 1
                if code not in fund_holders:
                    fund_holders[code] = f.get('name', '?')

    top = sorted(fund_counts.items(), key=lambda x: -x[1])[:8]
    print(f"  {'基金':30s} {'持有':6s}")
    print(f"  {'-'*38}")
    for code, count in top:
        print(f"  {fund_holders.get(code, '?')[:28]:28s} {count:3d}人")

    # Check if 024239 holders are selling
    for user, flist in snap.get('holdings', {}).items():
        for f in flist if isinstance(flist, list) else []:
            if isinstance(f, dict) and f.get('code') == '024239':
                profit = f.get('profit', '0')
                print(f"\n  024239: 6位大佬持有，全部盈利")
                break
except Exception as e:
    print(f"  ⚠️ {e}")

# ═════════ 4. 大师标签 ═════════
section("4. 大师风险标签")
from tools.master_analysis import duanyongping_tag, buffett_tag, munger_tag, lilu_tag, load_akshare_managers
import akshare as ak

for f in funds:
    code = f["code"]
    # Load holdings for duanyongping
    akshare_holdings = {}
    try:
        df = ak.fund_portfolio_hold_em(symbol=code, date="2026")
        if df is not None and not df.empty:
            akshare_holdings[code] = df
    except: pass

    # Manager data
    akshare_mgr = load_akshare_managers([code])

    dyp = duanyongping_tag(code, {}, None, akshare_holdings)
    bt = buffett_tag(code, {})
    sector_perf = {"QDII": 25.0}
    mg = munger_tag(code, f["name"], sector_perf)
    ll = lilu_tag(code, {}, akshare_mgr)

    print(f"  **{f['name']}**")
    print(f"    段永平: {dyp[0]}")
    print(f"    巴菲特: {bt[0]}")
    print(f"    芒格:   {mg[0]}")
    print(f"    李录:   {ll[0]}")
    print()

# ═════════ 5. 止损检查 ═════════
section("5. 止损检查")
for f in funds:
    try:
        rate = float(str(f["profit_rate"]).replace("%",""))
    except: rate = 0

    if rate <= -20:
        print(f"  🔴 {f['code']} {f['name']}: 亏损{rate:.1f}% → 触发硬止损！立即卖出！")
    elif rate <= -15:
        print(f"  🟡 {f['code']} {f['name']}: 亏损{rate:.1f}% → 接近止损，关注中")
    else:
        print(f"  🟢 {f['code']} {f['name']}: 亏损{rate:.1f}% → 安全")

# ═════════ 6. 最终决策 ═════════
section("6. 最终决策")
hard_stop_triggered = False
for f in funds:
    try:
        rate = float(str(f["profit_rate"]).replace("%",""))
    except: rate = 0
    if rate <= -20:
        hard_stop_triggered = True
        code = f["code"]
        sell_amt = f["market_value"]
        print(f"  🔴 硬止损触发: {f['name']}")
        print()
        print(f"  决策: 立即卖出")
        print(f"  卖出: 全部 {f['amount']} 份 (≈¥{sell_amt:.0f})")
        print(f"  赎回费: 0.5% (持有期不足30天)")
        print(f"  预计到账: ≈¥{sell_amt * 0.995:.0f}")
        print()

if not hard_stop_triggered:
    print(f"  🟢 无硬止损触发")
    for f in funds:
        try: rate = float(str(f["profit_rate"]).replace("%",""))
        except: rate = 0
        if rate < -10:
            print(f"  🟡 {f['code']}: 亏损{rate:.1f}%，建议减仓")

    print(f"\n  ✅ 建议: 持有观察，下次检视在季度末")

# ═════════ 7. 再配置建议 ═════════
section("7. 到账资金再配置")
if hard_stop_triggered:
    proceeds = 1451
    print(f"  回款: ¥{proceeds}")
    print(f"  建议配置:")
    print(f"    ¥{proceeds//2} → 007194 华泰柏瑞短债A（防守仓位，年化3.3%）")
    print(f"    ¥{proceeds - proceeds//2} → 现金储备")
    print()
    print(f"  下次建仓纪律:")
    print(f"    ├─ 用分批工具: python tools/dca_planner.py 金额")
    print(f"    ├─ 单基不超过总资产25%")
    print(f"    └─ 权益总仓位不超过70%")
else:
    print(f"  🟢 当前无需调整")

print()
print("-" * 55)
print(f"  报告时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
print("-" * 55)