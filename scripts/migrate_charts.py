"""一次性迁移：把两个 fund_charts.json 合并到 data/fund_charts/ 目录。

数据源：
  1. data/fund_charts.json (实盘, 273只, 数据良好)
  2. backtest/data/fund_charts.json (回测, 2187只, 大部分只有20天)

合并策略：同基金取数据点更多的版本。
"""
import json
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))

from tools.chart_loader import update_chart

LIVE_FILE = PROJECT / "data" / "fund_charts.json"
BACKTEST_FILE = PROJECT / "backtest" / "data" / "fund_charts.json"
TARGET_DIR = PROJECT / "data" / "fund_charts"


def main():
    live = json.loads(LIVE_FILE.read_text("utf-8")) if LIVE_FILE.exists() else {}
    bt = json.loads(BACKTEST_FILE.read_text("utf-8")) if BACKTEST_FILE.exists() else {}

    print(f"实盘数据: {len(live)} 只")
    print(f"回测数据: {len(bt)} 只")

    all_codes = set(live.keys()) | set(bt.keys())
    print(f"合并去重: {len(all_codes)} 只")

    migrated = 0
    for code in sorted(all_codes):
        live_pts = live.get(code, [])
        bt_pts = bt.get(code, [])
        # 取数据点更多的版本
        pts = live_pts if len(live_pts) >= len(bt_pts) else bt_pts
        if pts:
            update_chart(code, pts, TARGET_DIR)
            migrated += 1

    print(f"已迁移: {migrated} 只 → {TARGET_DIR}")

    # 重命名旧文件为 .bak
    if LIVE_FILE.exists():
        LIVE_FILE.rename(str(LIVE_FILE) + ".bak")
        print(f"  {LIVE_FILE.name} → {LIVE_FILE.name}.bak")
    if BACKTEST_FILE.exists():
        BACKTEST_FILE.rename(str(BACKTEST_FILE) + ".bak")
        print(f"  {BACKTEST_FILE.name} → {BACKTEST_FILE.name}.bak")

    print("迁移完成。旧文件已重命名为 .bak")


if __name__ == "__main__":
    main()
