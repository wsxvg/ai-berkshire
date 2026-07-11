#!/usr/bin/env python3
"""K 无脑跟投的多维度变异回测"""
import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backtest.engine.backtest import run_backtest

BASE = {'start_date':'2025-01-05','end_date':'2026-07-01','initial_cash':10000,'monthly_injection':0,
        'weights':{'quality':25,'cost':20,'manager':20,'momentum':15,'smart_money':20}}

# K 原始基线
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

# ── K 变异的维度探索 ──
VARIANTS = [
    # ── 原始基线 ──
    ("K-原始", "无脑跟投，无任何防护", {}),

    # ── 共识门槛 ──
    ("K-共识3", "3人买才跟", {'min_consensus':3}),
    ("K-共识4", "4人买才跟", {'min_consensus':4}),

    # ── 止盈（卖一半）──
    ("K-止盈15", "15%止盈卖一半", {'take_profit_pct':15}),
    ("K-止盈20", "20%止盈卖一半", {'take_profit_pct':20}),
    ("K-止盈30", "30%止盈卖一半", {'take_profit_pct':30}),
    ("K-止盈50", "50%止盈卖一半", {'take_profit_pct':50}),
    ("K-早止盈全卖", "15%止盈全卖", {'take_profit_pct':15, 'profit_mode':'all'}),
    ("K-阶梯止盈", "20%起阶梯卖", {'take_profit_pct':20, 'profit_mode':'step'}),
    ("K-四分止盈", "30%止盈卖1/4", {'take_profit_pct':30, 'profit_mode':'quarter'}),

    # ── 止损──
    ("K-止损5", "-5%止损", {'stop_loss_pct':-5, 'no_stop_loss':False}),
    ("K-止损10", "-10%止损", {'stop_loss_pct':-10, 'no_stop_loss':False}),
    ("K-止损15", "-15%止损", {'stop_loss_pct':-15, 'no_stop_loss':False}),
    ("K-止损20", "-20%止损", {'stop_loss_pct':-20, 'no_stop_loss':False}),

    # ── 分散──
    ("K-分散10", "单只上限10%", {'max_position_pct':10}),
    ("K-分散15", "单只上限15%", {'max_position_pct':15}),
    ("K-分散20", "单只上限20%", {'max_position_pct':20}),
    ("K-分散25", "单只上限25%", {'max_position_pct':25}),

    # ── 动量──
    ("K-动量温和", "动量<2.0卖出", {'momentum_sell':2.0}),
    ("K-动量严格", "动量<2.5卖出", {'momentum_sell':2.5}),
    ("K-动量激进", "动量<3.0卖出", {'momentum_sell':3.0}),

    # ── 类型──
    ("K-主动", "只跟主动基金", {'fund_type_filter':'active'}),

    # ── 限购感知──
    ("K-限购加分", "有限额+0.5分", {'limit_boost':0.5}),
    ("K-限购加分中", "有限额+1.0分", {'limit_boost':1.0}),
    ("K-限购加分强", "有限额+2.0分", {'limit_boost':2.0}),

    # ── 双向信号（止盈+止损）──
    ("K-止盈30+止损10", "止盈30%+止损-10%",
     {'take_profit_pct':30, 'stop_loss_pct':-10, 'no_stop_loss':False}),
    ("K-止盈20+止损5", "止盈20%+止损-5%",
     {'take_profit_pct':20, 'stop_loss_pct':-5, 'no_stop_loss':False}),

    # ── 多维组合──
    ("K-防护型", "止盈30+止损10+分散15+共识3",
     {'take_profit_pct':30, 'stop_loss_pct':-10, 'no_stop_loss':False,
      'max_position_pct':15, 'min_consensus':3}),
    ("K-保守型", "止盈15+止损5+分散10+共识3",
     {'take_profit_pct':15, 'stop_loss_pct':-5, 'no_stop_loss':False,
      'max_position_pct':10, 'min_consensus':3, 'profit_mode':'all'}),
    ("K-中庸型", "止盈30+止损15+分散20+动量2.0",
     {'take_profit_pct':30, 'stop_loss_pct':-15, 'no_stop_loss':False,
      'max_position_pct':20, 'momentum_sell':2.0}),
    ("K-激进型", "止盈50+止损20+分散25",
     {'take_profit_pct':50, 'stop_loss_pct':-20, 'no_stop_loss':False,
      'max_position_pct':25}),
    ("K-完整防护", "止盈30+止损10+分散15+共识3+限购加分",
     {'take_profit_pct':30, 'stop_loss_pct':-10, 'no_stop_loss':False,
      'max_position_pct':15, 'min_consensus':3, 'limit_boost':0.5}),
]

results = []
for name, desc, overrides in VARIANTS:
    print(f"\n{'='*50}")
    print(f"K变异 {name}: {desc}")
    print(f"{'='*50}")
    r = run_one(name, desc, **overrides)
    if r:
        results.append(r)
        irr = ((1 + r['return']/100) ** (12/18) - 1) * 100
        print(f"  收益: {r['return']:+.2f}% (年化{irr:+.1f}%)")
        print(f"  回撤: {r['dd']:.2f}%  夏普: {r['sharpe']:.2f}")
        print(f"  交易: {r['trades']}次 持仓{r['holdings']}只 费用:{r['fees']:.0f}")
        print(f"  vs基准: {r['vs_bm']:+.2f}%")

# 排序展示
bm_return = 27.37
print(f"\n\n{'='*80}")
print(f"K变异对比 (2025-01-05 ~ 2026-07-01, 18个月, 基准+{bm_return}%)")
print(f"{'='*80}")
print(f"{'策略':20s} {'类型':30s} {'收益':>8s} {'回撤':>8s} {'夏普':>8s} {'超额':>8s} {'交易':>6s}")
print(f"{'-'*80}")
for r in sorted(results, key=lambda x: x['sharpe'], reverse=True):
    label = r['name'][:20]
    desc = r['desc'][:30]
    print(f"{label:20s} {desc:30s} {r['return']:>+7.2f}% {r['dd']:>7.2f}% "
          f"{r['sharpe']:>7.2f} {r['vs_bm']:>+8.2f}% {r['trades']:>5d}")

# 另按收益排序
print(f"\n{'='*80}")
print(f"按收益排名")
print(f"{'='*80}")
for r in sorted(results, key=lambda x: x['return'], reverse=True):
    print(f"{r['name']:20s} {r['return']:>+7.2f}%  夏普{r['sharpe']:.2f}  回撤{r['dd']:.2f}%  交易{r['trades']}")

# 保存
out = Path(__file__).resolve().parent.parent / "backtest" / "reports" / "k_variants.json"
out.parent.mkdir(parents=True, exist_ok=True)
with open(out, "w", encoding="utf-8") as f:
    json.dump({"results": sorted(results, key=lambda x: x['sharpe'], reverse=True),
               "benchmark_return": bm_return, "period": "2025-01-05 ~ 2026-07-01",
               "count": len(results)},
              f, ensure_ascii=False, indent=2)
print(f"\n保存到 {out}")