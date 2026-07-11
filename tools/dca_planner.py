#!/usr/bin/env python3
"""分批建仓计算器 — 防止一次性买在高点"""
import sys, json
from datetime import datetime, timedelta
from pathlib import Path

def plan_dca(total_amount, batches=3, interval_days=7, fund_codes=None, current_holdings=None):
    """
    分批建仓计划（策略D版）
    如果一次性买入会突破单基25%上限，强制分批。
    """
    # 检查持仓约束
    if current_holdings and fund_codes:
        from tools.jd_finance_api import get_user_holdings
        try:
            hdata = current_holdings if isinstance(current_holdings, dict) else get_user_holdings(use_cache=False)
            total = 0
            existing = {}
            for h in hdata.get("holdings", []):
                if isinstance(h, dict):
                    try:
                        amt = float(str(h.get("amount","0")).replace(",","").replace("元","").replace("¥","").strip())
                        profit = float(str(h.get("profit","0")).replace(",","").replace("元","").replace("¥","").replace("+","").strip())
                        mv = max(amt + profit, 0)
                        code = h.get("code","")
                        total += mv
                        existing[code] = existing.get(code, 0) + mv
                    except: pass
            for code in fund_codes:
                current = existing.get(code, 0)
                new_total = total + total_amount
                new_pct = (current + total_amount) / new_total * 100
                if new_pct > 25:
                    print(f"
⚠️ 策略D纪律锁: 一次性买入{code}后占比{new_pct:.0f}%，超过25%上限！")
                    print(f"强制改为分批建仓:
")
                    # Auto-generate 3 batches
                    batch_max = new_total * 0.25 - current
                    if batch_max > 0:
                        b1 = min(total_amount * 0.4, batch_max)
                        b2 = min(total_amount * 0.4, batch_max - b1)
                        b3 = total_amount - b1 - b2
                        if b3 < 0: b3 = 0
                        print(f"  第1批 (T+0):  ¥{b1:.0f}  → 占比{(current+b1)/(total+b1)*100:.0f}%")
                        print(f"  第2批 (T+7):  ¥{b2:.0f}  → 占比{(current+b1+b2)/(total+b1+b2)*100:.0f}%")
                        print(f"  第3批 (T+14): ¥{b3:.0f}  → 占比{(current+b1+b2+b3)/(total+b1+b2+b3)*100:.0f}%")
                        print()
                        print("注意: 第一批买入后若该基金亏损>5%，暂停后续批次，重新评估")
                        return
                    else:
                        print(f"  当前{code}已超限，禁止买入！")
                        return
        except Exception as e:
            print(f"(跳过持仓检查: {e})")

    """
    分批建仓计划

    Args:
        total_amount: 总投入金额
        batches: 分几批（默认3批）
        interval_days: 每批间隔天数（默认7天）
        fund_codes: 基金代码列表（可选）
    """
    today = datetime.now()
    base_per_batch = total_amount / batches

    print("=" * 55)
    print("  分批建仓计划")
    print(f"  生成时间: {today.strftime('%Y-%m-%d')}")
    print("=" * 55)
    print()
    print(f"总金额: ¥{total_amount:,.0f}")
    print(f"分批数: {batches} 批")
    print(f"间隔:  每 {interval_days} 天")
    if fund_codes:
        print(f"基金:   {', '.join(fund_codes)}")
    print()
    print(f"{'批次':6s} {'日期':14s} {'金额':>10s} {'比例':>8s} {'策略':16s}")
    print("-" * 56)

    for i in range(batches):
        batch_date = today + timedelta(days=i * interval_days)
        # 金字塔: 越往后金额越大（跌了补更多）
        if batches == 5:
            ratios = [1, 1.5, 2, 2.5, 3]
        elif batches == 4:
            ratios = [1, 2, 3, 4]
        elif batches == 3:
            ratios = [1, 2, 3]
        else:
            ratios = [1] * batches

        total_ratio = sum(ratios)
        amount = total_amount * ratios[i] / total_ratio
        batch_num = i + 1

        # 策略说明
        if i == 0:
            strategy = "底仓（先上车）"
        elif i == batches - 1:
            strategy = "最后加仓"
        else:
            strategy = "逢跌补仓"

        print(f"#{batch_num:<4d} {batch_date.strftime('%Y-%m-%d'):14s} ¥{amount:>7,.0f} {ratios[i]/total_ratio*100:>7.0f}% {strategy:16s}")

    print()
    print("💡 建议:")
    print("  1. 第一笔建 30-40% 底仓，避免踏空")
    print("  2. 后续每批观察市场，跌幅大可适当加码")
    print("  3. 市场大涨可暂停某批，等回调再补")
    print("  4. QDII基金注意T+2确认，预留时间差")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description='分批建仓计算器')
    parser.add_argument('amount', type=float, nargs='?', default=3000, help='总投入金额')
    parser.add_argument('--batches', type=int, default=3, help='分批数')
    parser.add_argument('--interval', type=int, default=7, help='间隔天数')
    parser.add_argument('--funds', nargs='*', default=None, help='基金代码')
    args = parser.parse_args()
    plan_dca(args.amount, args.batches, args.interval, args.funds)