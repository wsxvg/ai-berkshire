#!/usr/bin/env python3
"""偏差检测脚本 — 每日 CI 调用

检查 champion_paper_account.json 的最新偏差是否超标。
超标时返回非零退出码，CI 标记 🚨。

Usage:
    python scripts/check_deviation.py
"""
import json
import sys
import io
from pathlib import Path

# 修复 Windows GBK 终端编码
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

PROJECT = Path(__file__).resolve().parent.parent
ACC_PATH = PROJECT / "reports" / "sim" / "champion_paper_account.json"
STS_PATH = PROJECT / "reports" / "sim" / "champion_status.json"


def main():
    if not ACC_PATH.exists():
        print("[check_deviation] PaperAccount 不存在，跳过")
        return 0

    data = json.loads(ACC_PATH.read_text("utf-8"))
    status = json.loads(STS_PATH.read_text("utf-8")) if STS_PATH.exists() else {}

    if data.get("frozen"):
        reason = status.get("frozen_reason", "未知")
        print(f"[FROZEN] 账户已冻结: {reason}")
        return 1

    snaps = data.get("daily_snapshots", [])
    if not snaps:
        print("[check_deviation] 无快照，跳过")
        return 0

    latest = snaps[-1]
    dev = latest.get("deviation_pct", 0)
    dd = latest.get("current_dd", 0)
    phase = data.get("phase", "shadow")

    # Phase 对应的阈值
    THRESHOLDS = {
        "shadow": {"max_dev": 5.0, "cb_dd": 5.0},
        "pilot": {"max_dev": 3.0, "cb_dd": 8.0},
        "standard": {"max_dev": 3.0, "cb_dd": 12.4},
        "full": {"max_dev": 3.0, "cb_dd": 15.0},
    }
    th = THRESHOLDS.get(phase, THRESHOLDS["shadow"])

    print(f"Phase: {phase} | 偏差: {dev:.2f}% (限{th['max_dev']}%) | 回撤: {dd:.2f}% (限{th['cb_dd']}%)")

    if dev > th["max_dev"]:
        print(f"[WARN] 偏差超标: {dev:.2f}% > {th['max_dev']}%")
    if dd > th["cb_dd"]:
        print(f"[ALERT] 回撤超标: {dd:.2f}% > {th['cb_dd']}%")
        return 1

    # 检查连续偏差
    dev_log = data.get("deviation_log", [])
    recent = [d for d in dev_log[-5:] if d.get("deviation_pct", 0) > th["max_dev"]]
    if len(recent) >= 5:
        print(f"[ALERT] 偏差连续5天 > {th['max_dev']}%")
        return 1

    print("[OK] 偏差正常")
    return 0


if __name__ == "__main__":
    sys.exit(main())
