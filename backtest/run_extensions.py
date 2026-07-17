#!/usr/bin/env python3
"""步骤6: 引擎拓展验证（金字塔补仓 + 动态止损）
每个改动单独加、单独测。"""
import sys, json, time, copy
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))
REPORTS = PROJECT / "backtest" / "reports"

from backtest.engine.backtest import run_backtest

BASE = json.loads((PROJECT / "data" / "evolution" / "best_config.json").read_text("utf-8"))["config"]

def run_single(name, overrides):
    cfg = copy.deepcopy(BASE)
    cfg.update(overrides)
    t0 = time.time()
    print(f"\n  [RUN] {name}", flush=True)
    try:
        result = run_backtest(cfg)
        elapsed = time.time() - t0
        ret = result.get("total_return", 0)
        dd = result.get("max_drawdown", 0)
        trades = result.get("trade_count", 0)
        print(f"  -> {name}: ret={ret:.2f}% dd={dd:.2f}% trades={trades} ({elapsed:.0f}s)", flush=True)
        return {"name": name, "return": round(ret, 2), "dd": round(dd, 2),
                "trades": trades, "time_sec": round(elapsed, 0)}
    except Exception as e:
        elapsed = time.time() - t0
        print(f"  -> {name}: ERROR {e} ({elapsed:.0f}s)", flush=True)
        return {"name": name, "error": str(e)}

def save(name, results):
    path = REPORTS / name
    path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  保存: {path}", flush=True)

print("="*60)
print("# 步骤6: 引擎拓展验证")
print("="*60, flush=True)

results = []

# 6.5 金字塔补仓
print("\n## 6.5 金字塔补仓", flush=True)
r_pyramid = run_single("champion+pyramiding", {"pyramiding_enabled": True})
results.append(r_pyramid)
save("p5_extension_pyramid.json", [r_pyramid])

# 6.1 动态止损
print("\n## 6.1 动态止损", flush=True)
r_dynsl = run_single("champion+dyn_stop_loss", {"dynamic_stop_loss": True})
results.append(r_dynsl)
save("p5_extension_dynsl.json", [r_dynsl])

# 汇总
print(f"\n{'='*60}")
print("  步骤6 汇总:")
print(f"  冠军基线:       ret=65.84% dd=9.21% trades=314")
for r in results:
    if "return" in r:
        delta = r["return"] - 65.84
        print(f"  {r['name']}: ret={r['return']}% dd={r['dd']}% trades={r['trades']} (Δ{delta:+.2f}pp)")
print(f"{'='*60}", flush=True)

save("p6_extension_summary.json", results)
