"""最终验证：83.6% 覆盖率 + 所有 fix 后的回测效果"""
import json, os, sys
from pathlib import Path
PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))
c = json.loads((PROJECT / "data/evolution/best_config.json").read_text("utf-8"))
cfg = c["config"]
cfg["start_date"] = "2024-03-11"; cfg["end_date"] = "2026-07-14"
cfg["min_score"] = 3.0; cfg["min_consensus"] = 3; cfg["use_weighted_consensus"] = True
cfg["stop_loss_pct"] = -12; cfg["take_profit_pct"] = 20; cfg["max_holdings"] = 5
cfg["pyramiding_enabled"] = True; cfg["dynamic_ranking"] = True
cfg["circuit_breaker_pct"] = 15; cfg["correlation_sell_threshold"] = 0.95
_old=os.dup(2); _dn=os.open(os.devnull,os.O_WRONLY); os.dup2(_dn,2); os.close(_dn)
try:
    from backtest.engine.backtest import run_backtest
    r=run_backtest(cfg)
    print(f"年化:{r.get('annualized_return',0):+.1f}% 夏普:{r.get('sharpe',0)} 回报:{r.get('total_return',0):.1f}% 回撤:{r.get('max_drawdown',0):.1f}% 交易:{r.get('trade_count',0)}")
finally:
    os.dup2(_old,2); os.close(_old)
