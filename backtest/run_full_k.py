#!/usr/bin/env python3
"""全面K变异：跟卖+持仓限制+净信号+动量杂交"""
import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backtest.engine.backtest import run_backtest

BASE = {'start_date':'2025-01-05','end_date':'2026-07-01','initial_cash':10000,'monthly_injection':0,
        'weights':{'quality':25,'cost':20,'manager':20,'momentum':15,'smart_money':20}}
K_BASE = {'min_score':0.0, 'no_stop_loss':True, 'take_profit_pct':1000,
          'profit_mode':'half', 'cost_penalty':0, 'min_consensus':2,
          'fund_type_filter':'all', 'momentum_sell':0, 'max_position_pct':100}

def run_one(name, desc, **overrides):
    cfg = dict(BASE)
    cfg.update(K_BASE)
    cfg.update(overrides)
    try:
        r = run_backtest(cfg)
        return {
            "name": name, "desc": desc,
            "return": r['total_return'], "dd": r['max_drawdown'],
            "trades": r['trade_count'], "holdings": r['final_holdings'],
            "sharpe": r['total_return'] / max(r['max_drawdown'], 1),
            "vs_bm": r['total_return'] - r.get('benchmark_return', 27.37),
            "fees": r.get('total_fees', 0),
        }
    except Exception as e:
        print(f"  FAILED {name}: {e}")
        import traceback; traceback.print_exc()
        return None

VARIANTS = [
    # ═══════ 跟卖系列（纯跟大佬卖）═══════
    ("跟卖-2人", "2人大佬卖就跟卖", {'sell_consensus':2}),
    ("跟卖-3人", "3人大佬卖就跟卖", {'sell_consensus':3}),
    ("跟卖-4人", "4人大佬卖就跟卖", {'sell_consensus':4}),

    # ═══════ 买卖对称系列 ═══════
    ("买卖对称-2", "2人买才买+2人卖就卖", {'min_consensus':2, 'sell_consensus':2}),
    ("买卖对称-3", "3人买才买+3人卖就卖", {'min_consensus':3, 'sell_consensus':3}),

    # ═══════ 净信号系列 ═══════
    ("净信号", "买入人数>卖出人数才买", {'net_signal':True}),
    ("净信号+跟卖2", "净信号+跟卖2人", {'net_signal':True, 'sell_consensus':2}),

    # ═══════ 动量+跟卖杂交 ═══════
    ("M20+跟卖2", "动量2.0+跟卖2人", {'momentum_sell':2.0, 'sell_consensus':2}),
    ("M20+跟卖3", "动量2.0+跟卖3人", {'momentum_sell':2.0, 'sell_consensus':3}),
    ("M18+跟卖2", "动量1.8+跟卖2人", {'momentum_sell':1.8, 'sell_consensus':2}),
    ("M22+跟卖2", "动量2.2+跟卖2人", {'momentum_sell':2.2, 'sell_consensus':2}),

    # ═══════ 动量+跟卖+止盈 ═══════
    ("M20+跟卖2+TP30", "动量2.0+跟卖2+止盈30", {'momentum_sell':2.0, 'sell_consensus':2, 'take_profit_pct':30}),
    ("M20+跟卖2+TP50", "动量2.0+跟卖2+止盈50", {'momentum_sell':2.0, 'sell_consensus':2, 'take_profit_pct':50}),
    ("M20+跟卖3+TP30", "动量2.0+跟卖3+止盈30", {'momentum_sell':2.0, 'sell_consensus':3, 'take_profit_pct':30}),

    # ═══════ 最大持仓系列 ═══════
    ("持仓5", "最多同时持5只", {'max_holdings':5}),
    ("持仓8", "最多同时持8只", {'max_holdings':8}),
    ("持仓10", "最多同时持10只", {'max_holdings':10}),
    ("持仓3", "最多同时持3只", {'max_holdings':3}),

    # ═══════ 动量+持仓限制 ═══════
    ("M20+持仓5", "动量2.0+最多5只", {'momentum_sell':2.0, 'max_holdings':5}),
    ("M20+持仓8", "动量2.0+最多8只", {'momentum_sell':2.0, 'max_holdings':8}),
    ("M20+持仓3", "动量2.0+最多3只", {'momentum_sell':2.0, 'max_holdings':3}),

    # ═══════ 跟卖+持仓限制 ═══════
    ("跟卖2+持仓5", "跟卖2人+最多5只", {'sell_consensus':2, 'max_holdings':5}),
    ("跟卖2+持仓8", "跟卖2人+最多8只", {'sell_consensus':2, 'max_holdings':8}),

    # ═══════ 三合一 ═══════
    ("全防护-M20+跟卖3+TP30+持仓5", "动量20+跟卖3+止盈30+持仓5",
     {'momentum_sell':2.0, 'sell_consensus':3, 'take_profit_pct':30, 'max_holdings':5}),
    ("全防护-M20+跟卖2+TP30+持仓5", "动量20+跟卖2+止盈30+持仓5",
     {'momentum_sell':2.0, 'sell_consensus':2, 'take_profit_pct':30, 'max_holdings':5}),
    ("全攻-M20+跟卖3+持仓5", "动量20+跟卖3+持仓5",
     {'momentum_sell':2.0, 'sell_consensus':3, 'max_holdings':5}),

    # ═══════ 基准对照 ═══════
    ("K-原始", "原始无脑跟投", {}),
    ("M20-纯", "纯动量2.0", {'momentum_sell':2.0}),
]

results = []
for name, desc, overrides in VARIANTS:
    print(f"\n{'='*40}")
    print(f"{name}: {desc}")
    print(f"{'='*40}")
    r = run_one(name, desc, **overrides)
    if r:
        results.append(r)
        irr = ((1 + r['return']/100) ** (12/18) - 1) * 100
        print(f"  收益:{r['return']:>+8.2f}%  夏普:{r['sharpe']:>6.2f}  回撤:{r['dd']:>6.2f}%  交易:{r['trades']:>3d}  最终持仓:{r['holdings']}  费用:{r['fees']:.0f}")

bm_return = 27.37
print(f"\n\n{'='*100}")
print(f"全面K变异对比 (基准+{bm_return}%)")
print(f"{'='*100}")
print(f"{'策略':20s} {'说明':30s} {'收益':>8s} {'回撤':>8s} {'夏普':>8s} {'超额':>8s} {'交易':>5s} {'持仓':>4s}")
print(f"{'-'*100}")
for r in sorted(results, key=lambda x: x['sharpe'], reverse=True):
    print(f"{r['name']:20s} {r['desc']:30s} {r['return']:>+7.2f}% {r['dd']:>7.2f}% "
          f"{r['sharpe']:>7.2f} {r['vs_bm']:>+8.2f}% {r['trades']:>4d}  {r['holdings']:>3d}")

out = Path(__file__).resolve().parent.parent / "backtest" / "reports" / "k_full_variants.json"
out.parent.mkdir(parents=True, exist_ok=True)
with open(out, "w", encoding="utf-8") as f:
    json.dump({"results": sorted(results, key=lambda x: x['sharpe'], reverse=True),
               "benchmark_return": bm_return, "period": "2025-01-05 ~ 2026-07-01"},
              f, ensure_ascii=False, indent=2)
print(f"\n保存到 {out}")