#!/usr/bin/env python3
"""批量实盘模拟：7月1日 → 7月17日（12个交易日）
每天用 --simulate-date 跑 daily_live.py，连续模拟"""
import subprocess, sys, os
from datetime import datetime, timedelta

# 7月1日到7月17日的交易日（跳过周末）
dates = []
d = datetime(2026, 7, 1)
end = datetime(2026, 7, 17)
while d <= end:
    if d.weekday() < 5:  # 周一至周五
        dates.append(d.strftime("%Y-%m-%d"))
    d += timedelta(days=1)

print(f"=== 批量实盘模拟: {dates[0]} → {dates[-1]} ({len(dates)} 个交易日) ===")
print(f"配置: V2 (金字塔补仓 + 动态止损)")
print(f"本金: 10万 / 每笔: 5000")
print()

# 重置虚拟组合
vp_path = "reports/sim/virtual_portfolio.json"
if os.path.exists(vp_path):
    os.remove(vp_path)
    print("虚拟组合已重置")

for i, date in enumerate(dates):
    print(f"\n{'='*60}")
    print(f"  [{i+1}/{len(dates)}] 模拟 {date}")
    print(f"{'='*60}")
    
    result = subprocess.run(
        [sys.executable, "scripts/daily_live.py", "--simulate-date", date],
        capture_output=True, text=True, encoding="utf-8", cwd="c:\\fund"
    )
    
    # 打印输出
    if result.stdout:
        for line in result.stdout.split("\n"):
            if line.strip():
                print(f"  {line}")
    if result.returncode != 0:
        print(f"  ERROR: {result.stderr[:200]}")

print(f"\n{'='*60}")
print(f"  批量模拟完成!")
print(f"  查看结果: reports/sim/")
print(f"{'='*60}")
