#!/usr/bin/env python3
"""Backtest: 基于历史数据的评分引擎回测。
不修改项目代码，只引用现有模块。

用法：
    python -m backtest.run

数据目录：
    backtest/data/         # 存放拉取的历史数据
    backtest/reports/      # 回测结果
"""
import sys
from pathlib import Path

BACKTEST_DIR = Path(__file__).parent
PROJECT_DIR = BACKTEST_DIR.parent
DATA_DIR = BACKTEST_DIR / "data"
REPORTS_DIR = BACKTEST_DIR / "reports"

sys.path.insert(0, str(PROJECT_DIR))