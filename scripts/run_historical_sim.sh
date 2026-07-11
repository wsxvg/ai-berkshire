#!/bin/bash
# 跑 6 个历史周五的模拟 (周五行情已收盘, 数据齐)
# virtual_portfolio.json 跨日累加, 反映多日连续跑结果
set -e
cd "$(dirname "$0")/.."
ROOT="$(pwd)"
DATES=("2026-05-22" "2026-05-29" "2026-06-05" "2026-06-12" "2026-06-19" "2026-06-26")
for D in "${DATES[@]}"; do
  echo "==================================================="
  echo ">> Simulating $D"
  echo "==================================================="
  PYTHONIOENCODING=utf-8 py -3.10 scripts/daily_live.py --simulate-date "$D" 2>&1 | grep -v "^$" | tail -50
  echo ""
  # 每个日期之间停 1s 防止 file lock
  sleep 1
done
echo "==================================================="
echo ">> All done. Reports:"
ls -la reports/sim/
