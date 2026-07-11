#!/usr/bin/env python3
"""024239 华夏全球科技先锋 减仓/止损计划"""
from datetime import datetime, timedelta

# 买入信息
buy_date = datetime(2026, 6, 22)  # 确认日
today = datetime(2026, 7, 4)
hold_days = (today - buy_date).days
release_date = buy_date + timedelta(days=30)

print("=" * 55)
print("  024239 减仓/止损计划")
print("=" * 55)
print()
print(f"代码:     024239")
print(f"名称:     华夏全球科技先锋混合(QDII)C")
print(f"成本价:   4.1983 元/份")
print(f"当前净值: 3.5319 元/份（07-02）")
print(f"持有份额: 595.48 份")
print(f"持仓市值: ¥2,103.18")
print(f"亏损:     -15.87%（-¥396.82）")
print()

# 持有期
print(f"买入确认日:   {buy_date.strftime('%Y-%m-%d')}")
print(f"当前日期:     {today.strftime('%Y-%m-%d')}")
print(f"已持有:       {hold_days} 天")
print(f"免赎回费日:   {release_date.strftime('%Y-%m-%d')}（满30天）")
print()

# 净值安全线
current_nav = 3.5319
stop_loss_20 = current_nav / (1 - 0.15) * (1 - 0.20)  # 从成本价算-20%
cost_per_share = 4.1983
hard_stop_nav = cost_per_share * 0.80  # -20% = 3.3586

print(f"持仓成本单价: ¥{cost_per_share:.4f}")
print(f"-20%硬止损价: ¥{hard_stop_nav:.4f}（净值跌到此价格强制卖出）")
print(f"当前距止损:   {((current_nav - hard_stop_nav) / hard_stop_nav * 100):.1f}%")
print()

# 倒计时
remaining_days = (release_date - today).days

print("─" * 55)
print("  执行计划")
print("─" * 55)
print()

if remaining_days > 0:
    print(f"⏳ 等待期: 还剩 {remaining_days} 天到免赎回费")
    print()
    print("  这段时间：")
    print("  1️⃣  每天运行 `python tools/position_alert.py` 看预警")
    print("  2️⃣  如果净值跌破 ¥3.36（-20%），不等了直接卖")
    print()

# 到期后的方案
print(f"📅 {release_date.strftime('%Y-%m-%d')} 到期后的操作：")
print()
print(f"  情况A：亏损 > 10%（净值 < ¥3.78）")
print(f"    → 卖一半（~¥1,000），留一半观察")
print(f"    → 留的一半设 -20% 硬止损")
print(f"")
print(f"  情况B：亏损 5%-10%（净值 ¥3.78 ~ ¥3.99）")
print(f"    → 卖 1/3（~¥600），等反弹")
print(f"")
print(f"  情况C：亏损 < 5%（净值 > ¥3.99）")
print(f"    → 不动，核心仓位继续持有")
print(f"    → 季度检视时再评估")
print(f"")
print(f"  情况D：触发 -20% 硬止损（净值 < ¥3.36）")
print(f"    → ⚠️ 不等到期，强制卖出！")
print(f"    → 认亏约 ¥500，保住 ¥2,000 本金")