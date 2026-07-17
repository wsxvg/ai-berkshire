#!/usr/bin/env python3
"""步骤6.6: 组合测试 — 金字塔补仓 + 动态止损同时开启"""
import sys, json, time, copy
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))
REPORTS = PROJECT / "backtest" / "reports"

from backtest.engine.backtest import run_backtest

BASE = json.loads((PROJECT / "data" / "evolution" / "best_config.json").read_text("utf-8"))["config"]

cfg = copy.deepcopy(BASE)
cfg["pyramiding_enabled"] = True
cfg["dynamic_stop_loss"] = True

print("="*60, flush=True)
print("  步骤6.6: 金字塔补仓 + 动态止损 组合测试", flush=True)
print("="*60, flush=True)

t0 = time.time()
result = run_backtest(cfg)
elapsed = time.time() - t0
ret = result.get("total_return", 0)
dd = result.get("max_drawdown", 0)
trades = result.get("trade_count", 0)

print(f"\n{'='*60}", flush=True)
print(f"  组合结果: ret={ret:.2f}% dd={dd:.2f}% trades={trades} ({elapsed:.0f}s)", flush=True)
print(f"  冠军基线: ret=65.84% dd=9.21% trades=314", flush=True)
print(f"  Δ收益: {ret-65.84:+.2f}pp", flush=True)
print(f"  Δ回撤: {dd-9.21:+.2f}pp", flush=True)

# 判断是否通过
if ret > 65.84 and dd <= 9.21 + 0.5:
    print(f"  ✅ 组合通过! 收益提升且回撤可控", flush=True)
    # 保存最终配置
    final = {"config": cfg, "return": round(ret, 2), "dd": round(dd, 2), "trades": trades}
    out = REPORTS / "FINAL_COMBO_result.json"
    out.write_text(json.dumps(final, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  保存: {out}", flush=True)
else:
    print(f"  ⚠️ 组合未通过门槍", flush=True)
    print(f"  门槍: 收益>65.84% 且 回撤≤9.71%", flush=True)
