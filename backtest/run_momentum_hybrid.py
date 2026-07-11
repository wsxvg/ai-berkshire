#!/usr/bin/env python3
"""K-动量温和 + 分散 杂交深度测试"""
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
        return None

VARIANTS = [
    # ── 动量不同阈值 + 分散15 ──
    ("M1.4+D15", "动量1.4卖+分散15", {'momentum_sell':1.4, 'max_position_pct':15}),
    ("M1.6+D15", "动量1.6卖+分散15", {'momentum_sell':1.6, 'max_position_pct':15}),
    ("M1.8+D15", "动量1.8卖+分散15", {'momentum_sell':1.8, 'max_position_pct':15}),
    ("M2.0+D15", "动量2.0卖+分散15", {'momentum_sell':2.0, 'max_position_pct':15}),
    ("M2.2+D15", "动量2.2卖+分散15", {'momentum_sell':2.2, 'max_position_pct':15}),
    ("M2.4+D15", "动量2.4卖+分散15", {'momentum_sell':2.4, 'max_position_pct':15}),
    ("M2.6+D15", "动量2.6卖+分散15", {'momentum_sell':2.6, 'max_position_pct':15}),
    ("M2.8+D15", "动量2.8卖+分散15", {'momentum_sell':2.8, 'max_position_pct':15}),
    ("M3.0+D15", "动量3.0卖+分散15", {'momentum_sell':3.0, 'max_position_pct':15}),

    # ── 动量2.0 + 不同分散 ──
    ("M2.0+D10", "动量2.0+分散10", {'momentum_sell':2.0, 'max_position_pct':10}),
    ("M2.0+D20", "动量2.0+分散20", {'momentum_sell':2.0, 'max_position_pct':20}),
    ("M2.0+D25", "动量2.0+分散25", {'momentum_sell':2.0, 'max_position_pct':25}),

    # ── 动量2.0+分散15+止盈 ──
    ("M2.0+D15+TP20", "+止盈20%卖一半", {'momentum_sell':2.0, 'max_position_pct':15, 'take_profit_pct':20}),
    ("M2.0+D15+TP30", "+止盈30%卖一半", {'momentum_sell':2.0, 'max_position_pct':15, 'take_profit_pct':30}),
    ("M2.0+D15+TP50", "+止盈50%卖一半", {'momentum_sell':2.0, 'max_position_pct':15, 'take_profit_pct':50}),

    # ── 动量2.0+分散15+阶梯止盈 ──
    ("M2.0+D15+STEP", "+阶梯止盈20%起", {'momentum_sell':2.0, 'max_position_pct':15, 'take_profit_pct':20, 'profit_mode':'step'}),

    # ── 动量2.0+分散15+止损 ──
    ("M2.0+D15+SL5", "+止损-5%", {'momentum_sell':2.0, 'max_position_pct':15, 'no_stop_loss':False, 'stop_loss_pct':-5}),
    ("M2.0+D15+SL10", "+止损-10%", {'momentum_sell':2.0, 'max_position_pct':15, 'no_stop_loss':False, 'stop_loss_pct':-10}),

    # ── 动量2.0+分散15+共识3 ──
    ("M2.0+D15+C3", "+共识3人", {'momentum_sell':2.0, 'max_position_pct':15, 'min_consensus':3}),

    # ── 三合一 ──
    ("M2.0+D15+TP30+SL10", "全防护(止盈30+止损10)", {'momentum_sell':2.0, 'max_position_pct':15, 'take_profit_pct':30, 'no_stop_loss':False, 'stop_loss_pct':-10}),
    ("M2.0+D15+TP20+C3", "止盈20+共识3", {'momentum_sell':2.0, 'max_position_pct':15, 'take_profit_pct':20, 'min_consensus':3}),

    # ── 纯动量（无分散）阈值扫描 ──
    ("M1.6-纯", "纯动量1.6卖", {'momentum_sell':1.6}),
    ("M1.8-纯", "纯动量1.8卖", {'momentum_sell':1.8}),
    ("M2.0-纯", "纯动量2.0卖", {'momentum_sell':2.0}),
    ("M2.2-纯", "纯动量2.2卖", {'momentum_sell':2.2}),
    ("M2.4-纯", "纯动量2.4卖", {'momentum_sell':2.4}),
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
        print(f"  收益:{r['return']:>+8.2f}%  年化:{irr:>+6.1f}%  回撤:{r['dd']:>6.2f}%  夏普:{r['sharpe']:>6.2f}  交易:{r['trades']:>3d}  持仓:{r['holdings']}")

# 排序展示
bm_return = 27.37
print(f"\n\n{'='*100}")
print(f"动量杂交深度测试 (基准+{bm_return}%)")
print(f"{'='*100}")
print(f"{'策略':20s} {'说明':30s} {'收益':>8s} {'回撤':>8s} {'夏普':>8s} {'超额':>8s} {'交易':>5s} {'持仓':>4s}")
print(f"{'-'*100}")

# 按夏普排名
for r in sorted(results, key=lambda x: x['sharpe'], reverse=True):
    print(f"{r['name']:20s} {r['desc']:30s} {r['return']:>+7.2f}% {r['dd']:>7.2f}% "
          f"{r['sharpe']:>7.2f} {r['vs_bm']:>+8.2f}% {r['trades']:>4d}  {r['holdings']:>3d}")

# 保存
out = Path(__file__).resolve().parent.parent / "backtest" / "reports" / "momentum_hybrid.json"
out.parent.mkdir(parents=True, exist_ok=True)
with open(out, "w", encoding="utf-8") as f:
    json.dump({"results": sorted(results, key=lambda x: x['sharpe'], reverse=True),
               "benchmark_return": bm_return, "period": "2025-01-05 ~ 2026-07-01",
               "count": len(results)},
              f, ensure_ascii=False, indent=2)
print(f"\n保存到 {out}")