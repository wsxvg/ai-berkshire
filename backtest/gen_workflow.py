#!/usr/bin/env python3
"""生成大规模参数扫描workflow YAML"""
import json, re

with open("backtest/sweep_configs.py", "r", encoding="utf-8") as f:
    content = f.read()

# 提取JSON部分
config_match = re.search(r'SWEEP_CONFIGS = (\{.*?\})\n\n', content, re.DOTALL)
labels_match = re.search(r'SWEEP_LABELS = (\{.*?\})\n', content, re.DOTALL)

SWEEP_CONFIGS = json.loads(config_match.group(1)) if config_match else {}
SWEEP_LABELS = json.loads(labels_match.group(1)) if labels_match else {}

test_names = list(SWEEP_CONFIGS.keys())
print(f"Total tests: {len(test_names)}")

# 生成YAML
yaml = """name: Backtest Matrix 7 (Parameter Sweep 113)

on:
  workflow_dispatch:

jobs:
  backtest:
    runs-on: ubuntu-latest
    timeout-minutes: 30
    strategy:
      fail-fast: false
      max-parallel: 20
      matrix:
        test_name: [
"""

# 每行5个test name
for i in range(0, len(test_names), 5):
    batch = test_names[i:i+5]
    yaml += "          " + ", ".join(batch)
    if i + 5 < len(test_names):
        yaml += ",\n"
    else:
        yaml += "\n"

yaml += """        ]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - name: Install dependencies
        run: pip install lightgbm scikit-learn numpy pandas
      - name: Run backtest
        run: python backtest/run_single_test.py ${{ matrix.test_name }}
      - name: Upload result
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: result-${{ matrix.test_name }}
          path: backtest/results/${{ matrix.test_name }}.json

  collect-results:
    needs: backtest
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/download-artifact@v4
        with:
          path: backtest/results
          merge-multiple: true
      - name: Generate summary
        run: python backtest/collect_results.py
      - name: Upload summary
        uses: actions/upload-artifact@v4
        with:
          name: backtest-summary-7
          path: backtest/reports/unified_backtest_summary.json
"""

with open(".github/workflows/backtest-matrix-7.yml", "w", encoding="utf-8") as f:
    f.write(yaml)

print(f"Written to .github/workflows/backtest-matrix-7.yml")
print(f"Test names: {test_names[:5]}... {test_names[-5:]}")
