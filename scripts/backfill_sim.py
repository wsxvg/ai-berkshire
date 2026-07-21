"""批量回放实盘模拟：从6月1日到今天，每个交易日跑一次"""
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).parent.parent

# 中国交易日（排除周末，简化处理）
def trading_days(start, end):
    days = []
    d = start
    while d <= end:
        if d.weekday() < 5:  # 周一到周五
            days.append(d)
        d += timedelta(days=1)
    return days

start = datetime(2026, 6, 1)
end = datetime(2026, 7, 21)
days = trading_days(start, end)
print(f"共 {len(days)} 个交易日需要回放")

for i, d in enumerate(days):
    ds = d.strftime("%Y-%m-%d")
    print(f"\n{'='*60}")
    print(f"[{i+1}/{len(days)}] 回放 {ds}")
    print(f"{'='*60}")
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "daily_live.py"), "--simulate-date", ds],
        capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    # 只打印最后20行
    lines = result.stdout.strip().split("\n")
    for line in lines[-20:]:
        print(line)
    if result.returncode != 0:
        print(f"ERROR: returncode={result.returncode}")
        print(result.stderr[-500:])

print(f"\n{'='*60}")
print(f"回放完成！共 {len(days)} 个交易日")
