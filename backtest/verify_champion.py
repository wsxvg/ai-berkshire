#!/usr/bin/env python3
"""步骤0验证：跑冠军配置，确认 69.60% 可复现"""
import sys, json, time, os
os.environ["PYTHONUNBUFFERED"] = "1"
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))

from backtest.engine.backtest import run_backtest

# 直接从 best_config.json 读取冠军配置
config = json.loads(Path(PROJECT / "data" / "evolution" / "best_config.json").read_text("utf-8"))["config"]

print("=== 步骤0: 冠军复现验证 ===", flush=True)
print(f"配置: initial_cash={config.get('initial_cash')} ft={config.get('fund_type_filter')} sec={config.get('max_sector_pct')}", flush=True)
t0 = time.time()
result = run_backtest(config)
elapsed = time.time() - t0
ret = result.get("total_return", 0)
dd = result.get("max_drawdown", 0)
trades = result.get("trade_count", 0)
print(f"\n{'='*50}", flush=True)
print(f"结果: return={ret:.2f}% dd={dd:.2f}% trades={trades} ({elapsed:.0f}s)", flush=True)
print(f"期望: return=69.60% dd=9.13% trades=347", flush=True)
diff = abs(ret - 69.60)
if diff <= 1.0:
    print(f"✅ 复现成功! 偏差={diff:.2f}pp (<1pp)", flush=True)
else:
    print(f"⚠️ 复现偏差={diff:.2f}pp (>1pp)", flush=True)
