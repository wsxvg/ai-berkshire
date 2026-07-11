#!/usr/bin/env python3
"""DCA月定投3000场景下的策略对比"""
import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backtest.engine.backtest import run_backtest

BASE = {'start_date':'2025-01-05','end_date':'2026-07-01',
        'initial_cash':3000, 'monthly_injection':3000,
        'weights':{'quality':25,'cost':20,'manager':20,'momentum':15,'smart_money':20}}

# 无防护跟投基线
K_BASE = {'min_score':0.0, 'no_stop_loss':True, 'take_profit_pct':1000,
          'profit_mode':'half', 'cost_penalty':0, 'min_consensus':2,
          'fund_type_filter':'all', 'momentum_sell':0, 'max_position_pct':100}

def run_one(name, desc, **overrides):
    cfg = dict(BASE)
    cfg.update(K_BASE)
    cfg.update(overrides)
    try:
        r = run_backtest(cfg)
        total_in = r.get('monthly_injections', 0) + cfg.get('initial_cash', 0)
        return {
            "name": name, "desc": desc,
            "return": r['total_return'],
            "final_val": r['daily_values'][-1]['total'] if r.get('daily_values') else 0,
            "total_in": total_in,
            "profit": (r['daily_values'][-1]['total'] - total_in) if r.get('daily_values') else 0,
            "dd": r['max_drawdown'],
            "trades": r['trade_count'],
            "holdings": r['final_holdings'],
            "sharpe": r['total_return'] / max(r['max_drawdown'], 1),
            "fees": r.get('total_fees', 0),
        }
    except Exception as e:
        print(f"  FAILED {name}: {e}")
        import traceback; traceback.print_exc()
        return None

VARIANTS = [
    # ── DCA基线 ──
    ("纯定投不买基金", "每月3000只存钱不投资", {'min_consensus':99}),

    # ── 跟投系（无脑跟）──
    ("DCA-跟投原始", "原始无脑跟投", {}),
    ("DCA-跟卖2人", "跟投+跟卖2人", {'sell_consensus':2}),
    ("DCA-买卖对称3", "3人买+3人卖", {'min_consensus':3, 'sell_consensus':3}),
    ("DCA-净信号", "买入>卖出才买", {'net_signal':True}),

    # ── 动量系（最佳方案）──
    ("DCA-M20纯", "动量2.0卖出", {'momentum_sell':2.0}),
    ("DCA-M18纯", "动量1.8卖出", {'momentum_sell':1.8}),

    # ── 动量+分散──
    ("DCA-M20+分散15", "动量2.0+分散15", {'momentum_sell':2.0, 'max_position_pct':15}),
    ("DCA-M20+分散10", "动量2.0+分散10", {'momentum_sell':2.0, 'max_position_pct':10}),

    # ── 动量+止盈──
    ("DCA-M20+TP30", "动量2.0+止盈30", {'momentum_sell':2.0, 'take_profit_pct':30}),
    ("DCA-M20+TP50", "动量2.0+止盈50", {'momentum_sell':2.0, 'take_profit_pct':50}),

    # ── 动量+跟卖──
    ("DCA-M20+跟卖2", "动量2.0+跟卖2人", {'momentum_sell':2.0, 'sell_consensus':2}),
    ("DCA-M20+跟卖3", "动量2.0+跟卖3人", {'momentum_sell':2.0, 'sell_consensus':3}),

    # ── 全防护──
    ("DCA-M20+分散15+TP30", "动量2.0+分散15+止盈30",
     {'momentum_sell':2.0, 'max_position_pct':15, 'take_profit_pct':30}),
    ("DCA-M20+跟卖2+TP30+持仓5", "动量2.0+跟卖2+止盈30+持仓5",
     {'momentum_sell':2.0, 'sell_consensus':2, 'take_profit_pct':30, 'max_holdings':5}),
]

results = []
for name, desc, overrides in VARIANTS:
    print(f"\n{'='*40}")
    print(f"{name}: {desc}")
    print(f"{'='*40}")
    r = run_one(name, desc, **overrides)
    if r:
        results.append(r)
        print(f"  最终总资产:{r['final_val']:>8.0f}  投入共:{r['total_in']:>5.0f}  净赚:{r['profit']:>+7.0f}")
        print(f"  收益率:{r['return']:>+7.2f}%  回撤:{r['dd']:>6.2f}%  夏普:{r['sharpe']:>6.2f}")
        print(f"  交易:{r['trades']:>3d}次  最终持仓:{r['holdings']}只")

print(f"\n\n{'='*90}")
print("DCA月定投3000场景对比 (2025-01~2026-07, 18个月)")
print(f"{'='*90}")
print(f"{'策略':26s} {'最终':>8s} {'投入':>6s} {'净赚':>8s} {'收益':>8s} {'回撤':>8s} {'夏普':>8s} {'交易':>5s}")
print(f"{'-'*90}")
for r in sorted(results, key=lambda x: x['sharpe'], reverse=True):
    label = r['name'][:26]
    print(f"{label:26s} {r['final_val']:>8.0f} {r['total_in']:>6.0f} "
          f"{r['profit']:>+8.0f} {r['return']:>+7.2f}% {r['dd']:>7.2f}% "
          f"{r['sharpe']:>7.2f} {r['trades']:>4d}")

out = Path(__file__).resolve().parent.parent / "backtest" / "reports" / "dca_results.json"
out.parent.mkdir(parents=True, exist_ok=True)
with open(out, "w", encoding="utf-8") as f:
    json.dump({"results": sorted(results, key=lambda x: x['sharpe'], reverse=True),
               "period": "2025-01-05 ~ 2026-07-01", "monthly": 3000},
              f, ensure_ascii=False, indent=2)
print(f"\n保存到 {out}")