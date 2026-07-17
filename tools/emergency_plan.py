#!/usr/bin/env python3
"""异常持仓急救计划生成器 — 单基超限+深套+未满30天三重困境"""
import sys, json
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

def generate_emergency_plan(code, name, portfolio_total=0, position_value=0,
                             loss_pct=0, cost_per_share=0, current_nav=0,
                             buy_date_str="", hard_stop_pct=-20):
    """生成异常持仓急救计划"""
    today = datetime.now()

    # 持有天数
    days_held = 999
    release_date = today
    if buy_date_str:
        try:
            buy_date = datetime.strptime(buy_date_str[:10], "%Y-%m-%d")
            days_held = (today - buy_date).days
            release_date = buy_date + timedelta(days=30)
        except (ValueError, TypeError):
            pass

    pct = position_value / max(portfolio_total, 1) * 100
    locked = days_held < 30

    # 净值硬止损线
    hard_stop_nav = cost_per_share * (1 + hard_stop_pct / 100)
    nav_distance = (current_nav / max(hard_stop_nav, 0.001) - 1) * 100 if current_nav > 0 else 0

    # 等级
    if pct > 50:
        alert_level = "CRITICAL"
    elif pct > 25:
        alert_level = "HIGH"
    else:
        alert_level = "NORMAL"

    dr = f"2026-07-05"

    # 打印计划
    print("=" * 55)
    print(f"  {'🚨' if alert_level == 'CRITICAL' else '⚠️'} 异常持仓急救计划")
    if alert_level == 'CRITICAL':
        print(f"  等级: CRITICAL — 立即响应")
    print("=" * 55)
    print()
    print(f"基金: {code} {name}")
    print(f"日期: {dr}")
    print()
    print(f"占比:     {pct:.1f}% {'🔴' if pct > 25 else '🟢'} (上限25%)")
    print(f"亏损:     {loss_pct:.2f}% {'🔴' if loss_pct < -10 else '🟡'}")
    print(f"持有:     {days_held}天 {'🔒' if locked else '✅'} (30天解锁)")
    if locked:
        print(f"解锁日:   {release_date.strftime('%Y-%m-%d')} (还剩{(release_date-today).days}天)")
    print(f"硬止损:   ¥{hard_stop_nav:.4f} ({hard_stop_pct}%)")
    print(f"距止损:   {nav_distance:.1f}%")
    print()

    print("─" * 55)
    print("  执行计划")
    print("─" * 55)
    print()

    if pct < 25 and loss_pct > -10:
        print("✅ 当前持仓正常，无需急救。")
        return

    # Phase 1
    print(f"Phase 1 — {'锁定期' if locked else '等待期'}")
    print(f"  触发条件: {'持有满30天' if locked else '立即执行'}")
    print(f"  操作:")
    if locked:
        target_amount = portfolio_total * 0.25
        sell_amount = max(0, position_value - target_amount)
        print(f"    → 每日检查净值，跌破¥{hard_stop_nav:.2f}无条件清仓")
        print(f"    → {(release_date-today).days}天后执行减仓至25%")
        print(f"    → 预计卖出 ¥{sell_amount:.0f}")
        print(f"  准备:")
        print(f"    → 手机日历设 {release_date.strftime('%m-%d')} 提醒")
        print(f"    → 提前确认赎回费率为0")
    else:
        print(f"    → 立即卖出至占比25%以下")
        print(f"    → 资金到账后按Phase 3再配置")
    print()

    # Phase 2
    print(f"Phase 2 — 减仓执行")
    print(f"  触发条件: 解锁日或触发硬止损")
    print(f"  操作:")
    target_amount = portfolio_total * 0.25
    sell_amount = max(0, position_value - target_amount)
    print(f"    → 卖出 ¥{sell_amount:.0f}，将占比压至25%")
    print(f"    → 若当日净值 < ¥{hard_stop_nav:.2f}，改为全部清仓")
    print(f"  备选方案:")
    print(f"    → 若亏损>15%且担心卖在最低: 卖一半，留一半")
    print()

    # Phase 3
    print(f"Phase 3 — 资金再配置")
    print(f"  触发条件: 减仓资金到账")
    print(f"  操作:")
    defense_amount = sell_amount * 0.5
    cash_amount = sell_amount * 0.5
    print(f"    → ¥{defense_amount:.0f} 买入短债基金或货基（防守仓位）")
    print(f"    → ¥{cash_amount:.0f} 留作现金储备")
    print(f"  禁止操作:")
    print(f"    → ❌ 禁止用减仓资金立即买入同类权益基金")
    print(f"    → ❌ 禁止在30天内再次加仓该基金")
    print()

    print("─" * 55)
    print(f"  总结: 当前偏离度 {pct:.0f}% > 25%上限")
    print(f"  策略D已失效，请按以上计划修复持仓")
    print("─" * 55)

if __name__ == "__main__":
    from tools.jd_finance_api import get_user_holdings
    data = get_user_holdings(use_cache=False)

    total = 0
    funds = []
    for h in data.get('holdings', []):
        if isinstance(h, dict):
            try:
                amt = float(str(h.get("amount","0")).replace(",","").replace("元","").replace("¥","").strip())
                profit = float(str(h.get("profit","0")).replace(",","").replace("元","").replace("¥","").replace("+","").strip())
                mv = max(amt + profit, 0)
                total += mv
                funds.append({**h, "market_value": mv})
            except: pass

    for f in funds:
        if f["market_value"] / max(total,1) * 100 > 25:
            code = f.get("code","")
            name = f.get("name","?")
            profit_rate = f.get("profit_rate","0")
            try:
                loss = float(str(profit_rate).replace("%",""))
            except (ValueError, TypeError):
                loss = 0

            generate_emergency_plan(
                code=code, name=name,
                portfolio_total=total,
                position_value=f["market_value"],
                loss_pct=loss,
                cost_per_share=4.2,
                current_nav=3.53,
                buy_date_str="2026-06-22"
            )