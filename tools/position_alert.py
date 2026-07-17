#!/usr/bin/env python3
"""仓位预警脚本 — 每天扫描持仓，检查是否违反策略D的铁律"""
import sys, json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

def check_portfolio():
    """扫描持仓，返回所有预警"""
    from tools.jd_finance_api import get_user_holdings

    try:
        data = get_user_holdings(use_cache=False)
    except Exception as e:
        return [f"[ERROR] 获取持仓失败: {e}"]

    alerts = []
    holdings = data.get('holdings', [])

    if not holdings:
        return ["[WARN] 没有获取到持仓数据，请检查Cookie是否有效"]

    # 计算总资产和单基占比
    total_value = 0
    fund_details = []

    for h in holdings:
        if isinstance(h, dict):
            code = h.get('code', '')
            name = h.get('name', '?')
            amount_str = str(h.get('amount', '0')).replace(',', '').replace('元', '').replace('¥', '').strip()
            profit_str = str(h.get('profit', '0')).replace(',', '').replace('元', '').replace('¥', '').replace('+', '').strip()
            profit_rate = h.get('profit_rate', '0')

            try:
                amount = float(amount_str) if amount_str else 0
            except (ValueError, TypeError):
                amount = 0
            try:
                profit = float(profit_str) if profit_str else 0
            except (ValueError, TypeError):
                profit = 0

            # market_value = amount + profit (当前市值)
            market_value = amount + profit
            total_value += market_value

            fund_details.append({
                'code': code,
                'name': name,
                'amount': amount,
                'profit': profit,
                'profit_rate': profit_rate,
                'market_value': market_value
            })

    if total_value == 0:
        return ["[WARN] 持仓总资产为0，没有有效持仓"]

    # ─── 铁律1：单基不超过25% ───
    max_single_pct = 25
    for f in fund_details:
        pct = f['market_value'] / total_value * 100
        f['pct'] = round(pct, 1)
        if pct > max_single_pct:
            alerts.append(
                f"[RED] 单基超限: {f['code']} {f['name'][:20]} "
                f"占比 {pct:.1f}%，超过 {max_single_pct}% 上限！"
            )

    # ─── 铁律2：权益占比（股票/混合/QDII）不超过70% ───
    # 粗略判断：有 profit_rate 的基金都是权益类（基金平台只有权益类显示收益率）
    equity_value = sum(f['market_value'] for f in fund_details if f['profit_rate'] != '0')
    equity_pct = equity_value / total_value * 100

    if equity_pct > 70:
        alerts.append(
            f"[YELLOW] 权益仓位过高: {equity_pct:.1f}%（上限70%），建议补充债基/货基"
        )

    # ─── 铁律3：亏损超过 -20% 强制止损 ───
    hard_stop = -20
    for f in fund_details:
        try:
            rate = float(str(f['profit_rate']).replace('%', '').strip())
        except (ValueError, TypeError):
            rate = 0
        if rate <= hard_stop:
            alerts.append(
                f"[RED] 触发硬止损: {f['code']} {f['name'][:20]} "
                f"亏损 {rate:.1f}%，达到 -20% 强制止损线！立即卖出！"
            )
        elif rate <= -15:
            alerts.append(
                f"[YELLOW] 接近止损: {f['code']} {f['name'][:20]} "
                f"亏损 {rate:.1f}%，距 -20% 硬止损还有 {abs(rate + 20):.1f}%"
            )

    # ─── 输出报告 ───
    print("=" * 55)
    print("  策略D · 仓位预警报告")
    print(f"  扫描时间: 2026-07-04")
    print("=" * 55)
    print()
    print(f"总资产: ¥{total_value:,.2f}")
    print(f"持有基金: {len(fund_details)} 只")
    print()

    # 持仓明细
    print(f"{'代码':8s} {'基金名称':24s} {'投入':>8s} {'盈亏':>8s} {'占比':>6s}")
    print("-" * 58)
    fund_details.sort(key=lambda x: -x['market_value'])
    for f in fund_details:
        name = f['name'][:22]
        amt = f'¥{f["market_value"]:,.0f}'
        profit_str = f'{f["profit"]:+.0f}' if abs(f.get('profit',0)) < 10000 else f'¥{f["profit"]:,.0f}'
        pct = f'{f["pct"]:.0f}%'
        print(f'{f["code"]:8s} {name:24s} {amt:>8s} {profit_str:>8s} {pct:>6s}')
    print()

    # 汇总
    print(f"权益仓位: {equity_pct:.1f}%")
    print()

    # 预警
    if alerts:
        print("⚠️  预警:")
        for a in alerts:
            print(f"  {a}")
        print()
    else:
        print("✅ 所有指标正常，持仓合规")
        print()

    return alerts

if __name__ == "__main__":
    check_portfolio()