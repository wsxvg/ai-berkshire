"""对比原日期 vs 扩展日期在同一数据集上的表现"""
import json, os, sys, copy
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))

c = json.loads((PROJECT / "data/evolution/best_config.json").read_text("utf-8"))
base_cfg = c["config"]
base_cfg["end_date"] = "2026-07-14"

from backtest.engine.backtest import run_backtest

def mute(fn):
    _old = os.dup(2)
    _dn = os.open(os.devnull, os.O_WRONLY)
    os.dup2(_dn, 2)
    os.close(_dn)
    try:
        return fn()
    finally:
        os.dup2(_old, 2)
        os.close(_old)

# Test 1: 原日期
cfg1 = copy.deepcopy(base_cfg)
cfg1["start_date"] = "2024-03-11"
r1 = mute(lambda: run_backtest(cfg1))
print(f"原日期(2024-03~)   年化:{r1.get('annualized_return',0):+6.1f}% 回报:{r1.get('total_return',0):+6.1f}% 回撤:{r1.get('max_drawdown',0):+5.1f}% 交易:{r1.get('trade_count',0)} | ms=3.52")

# Test 2: 扩展日期
cfg2 = copy.deepcopy(base_cfg)
cfg2["start_date"] = "2023-07-14"
r2 = mute(lambda: run_backtest(cfg2))
print(f"扩展日期(2023-07~) 年化:{r2.get('annualized_return',0):+6.1f}% 回报:{r2.get('total_return',0):+6.1f}% 回撤:{r2.get('max_drawdown',0):+5.1f}% 交易:{r2.get('trade_count',0)} | ms=3.52")

# Test 3: 扩展日期 + 加权 + 低门槛
cfg3 = copy.deepcopy(base_cfg)
cfg3["start_date"] = "2023-07-14"
cfg3["min_score"] = 2.5
cfg3["use_weighted_consensus"] = True
cfg3["min_consensus"] = 3
r3 = mute(lambda: run_backtest(cfg3))
print(f"扩展+加权+ms=2.5  年化:{r3.get('annualized_return',0):+6.1f}% 回报:{r3.get('total_return',0):+6.1f}% 回撤:{r3.get('max_drawdown',0):+5.1f}% 交易:{r3.get('trade_count',0)}")
