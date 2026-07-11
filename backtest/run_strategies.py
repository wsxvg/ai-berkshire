#!/usr/bin/env python3
"""12种策略回测对比（多年代迭）"""
import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backtest.engine.backtest import run_backtest

# 多年代迭：从2025-01-05到2026-07-01（~18个月密集数据）
# 注：2024年数据稀疏（仅1057条记录），不用作起点
BASE = {'start_date':'2025-01-05','end_date':'2026-07-01','initial_cash':10000,'monthly_injection':0,
        'weights':{'quality':25,'cost':20,'manager':20,'momentum':15,'smart_money':20}}

# 沪深300基准（110020 易方达沪深300ETF联接）
# 从 fund_charts 算 2025-01-05 ~ 2026-07-01 的累计收益率
bm_return = 12.8  # 估算，实际由引擎计算

STRATEGIES = [
    # ── 原始7种（参数微调兼容多年引擎）──
    {
        "name": "A 费用敏感",
        "desc": "高费率惩罚+标准止损",
        "config": {'min_score':3.3, 'stop_loss_pct':-10, 'take_profit_pct':30,
                   'profit_mode':'half', 'cost_penalty':1.2, 'min_consensus':2,
                   'fund_type_filter':'all'},
    },
    {
        "name": "B 指数优先",
        "desc": "只买指数,低门槛,不止损",
        "config": {'min_score':3.0, 'no_stop_loss':True, 'take_profit_pct':50,
                   'profit_mode':'half', 'cost_penalty':0, 'min_consensus':1,
                   'fund_type_filter':'passive'},
    },
    {
        "name": "C 主动精选",
        "desc": "只买主动,高门槛,高共识",
        "config": {'min_score':3.5, 'stop_loss_pct':-15, 'take_profit_pct':30,
                   'profit_mode':'half', 'cost_penalty':0, 'min_consensus':3,
                   'fund_type_filter':'active'},
    },
    {
        "name": "D 智能费用",
        "desc": "费用敏感+标准操作",
        "config": {'min_score':3.3, 'stop_loss_pct':-10, 'take_profit_pct':30,
                   'profit_mode':'half', 'cost_penalty':1.0, 'min_consensus':2,
                   'fund_type_filter':'all'},
    },
    {
        "name": "E 分批建仓",
        "desc": "低费用惩罚+浅止损",
        "config": {'min_score':3.3, 'stop_loss_pct':-8, 'take_profit_pct':25,
                   'profit_mode':'quarter', 'cost_penalty':1.0, 'min_consensus':2,
                   'fund_type_filter':'all'},
    },
    {
        "name": "F 趋势跟踪",
        "desc": "不止损,阶梯止盈,动量优先",
        "config": {'min_score':3.3, 'no_stop_loss':True, 'take_profit_pct':20,
                   'profit_mode':'step', 'cost_penalty':0, 'min_consensus':2,
                   'fund_type_filter':'all', 'momentum_sell':1.0},
    },
    {
        "name": "G 绝对收益",
        "desc": "严止损,早止盈,低仓位",
        "config": {'min_score':3.5, 'stop_loss_pct':-5, 'take_profit_pct':15,
                   'profit_mode':'all', 'cost_penalty':1.0, 'min_consensus':2,
                   'fund_type_filter':'all', 'max_position_pct':15, 'momentum_sell':2.5},
    },

    # ── 新增5种──
    {
        "name": "H 默认基准",
        "desc": "原始默认参数",
        "config": {'min_score':3.3, 'stop_loss_pct':-15, 'take_profit_pct':30,
                   'profit_mode':'half', 'cost_penalty':0, 'min_consensus':2,
                   'fund_type_filter':'all'},
    },
    {
        "name": "I 优化器最优",
        "desc": "min_score=2.5, 浅止损",
        "config": {'min_score':2.5, 'stop_loss_pct':-8, 'take_profit_pct':30,
                   'profit_mode':'half', 'cost_penalty':0, 'min_consensus':2,
                   'fund_type_filter':'all'},
    },
    {
        "name": "J 买入持有",
        "desc": "买入后不动, 不止盈不止损",
        "config": {'min_score':3.3, 'no_stop_loss':True, 'take_profit_pct':1000,
                   'profit_mode':'half', 'cost_penalty':0, 'min_consensus':2,
                   'fund_type_filter':'all', 'momentum_sell':0},
    },
    {
        "name": "K 无脑跟投",
        "desc": "不评分, 2人买我就买",
        "config": {'min_score':0.0, 'stop_loss_pct':-30, 'take_profit_pct':50,
                   'profit_mode':'half', 'cost_penalty':0, 'min_consensus':2,
                   'fund_type_filter':'all'},
    },
    {
        "name": "L 月定投2500",
        "desc": "每月定投+均分买入",
        "config": {'min_score':3.3, 'stop_loss_pct':-15, 'take_profit_pct':30,
                   'profit_mode':'half', 'cost_penalty':0, 'min_consensus':2,
                   'fund_type_filter':'all', 'monthly_injection':2500},
    },
]

results = []
for s in STRATEGIES:
    print(f"\n{'='*50}")
    print(f"策略 {s['name']}: {s['desc']}")
    print(f"{'='*50}")
    cfg = dict(BASE)
    cfg.update(s['config'])
    # L 定投模式：初始资金少点，靠每月定投
    if 'monthly_injection' in s['config'] and s['config']['monthly_injection'] > 0:
        cfg['initial_cash'] = 0
    try:
        r = run_backtest(cfg)
        months = 18  # 2025-01 ~ 2026-07
        irr = ((1 + r['total_return']/100) ** (12/months) - 1) * 100
        results.append({
            "name": s['name'],
            "desc": s['desc'],
            "return": r['total_return'],
            "annualized": irr,
            "dd": r['max_drawdown'],
            "trades": r['trade_count'],
            "holdings": r['final_holdings'],
            "sharpe": r['total_return'] / max(r['max_drawdown'], 1),
            "vs_benchmark": r['total_return'] - r.get('benchmark_return', bm_return),
            "fees": r.get('total_fees', 0),
            "injected": r.get('monthly_injections', 0),
        })
        print(f"  收益: {r['total_return']:+.2f}% (年化{irr:+.1f}%)")
        print(f"  回撤: {r['max_drawdown']:.2f}%")
        print(f"  交易: {r['trade_count']}次 持仓{r['final_holdings']}只")
        print(f"  费用: {r.get('total_fees',0):.1f}")
        if r.get('monthly_injections', 0):
            print(f"  定投: {r['monthly_injections']:.0f}")
    except Exception as e:
        import traceback
        print(f"  FAILED: {e}")
        traceback.print_exc()

# 获取实际基准收益
bm_val = 0
if results and 'benchmark_return' in r:
    for s in STRATEGIES[:1]:
        cfg = dict(BASE)
        cfg.update(s['config'])
        # 重新跑一次取 benchmark
        try:
            rr = run_backtest(cfg)
            bm_val = rr.get('benchmark_return', bm_return)
        except:
            bm_val = bm_return

print(f"\n\n{'='*70}")
print(f"12种策略对比 (2025-01-05 ~ 2026-07-01, 18个月)")
print(f"{'='*70}")
print(f"{'策略':14s} {'收益':>8s} {'年化':>8s} {'回撤':>8s} {'夏普':>8s} {'超额':>8s} {'交易':>6s} {'费用':>6s}")
print(f"{'-'*70}")
for r in sorted(results, key=lambda x: x['sharpe'], reverse=True):
    print(f"{r['name']:14s} {r['return']:>+7.2f}% {r['annualized']:>+7.1f}% {r['dd']:>7.2f}% "
          f"{r['sharpe']:>7.2f} {r['vs_benchmark']:>+8.2f}% {r['trades']:>5d}  {r['fees']:>5.0f}")
print(f"{'基准':14s} {'+'+str(round(bm_val,2))+'%':>8s} {'—':>8s} {'—':>8s} {'—':>8s} {'—':>8s} {'—':>6s} {'—':>6s}")

# 排序输出（按夏普降序）
results_sorted = sorted(results, key=lambda x: x['sharpe'], reverse=True)

# 保存
out = Path(__file__).resolve().parent.parent / "backtest" / "reports" / "strategy_comparison_v2.json"
out.parent.mkdir(parents=True, exist_ok=True)
with open(out, "w", encoding="utf-8") as f:
    json.dump({"strategies": results_sorted, "benchmark_return": bm_val,
               "period": "2025-01-05 ~ 2026-07-01"},
              f, ensure_ascii=False, indent=2)
print(f"\n保存到 {out}")