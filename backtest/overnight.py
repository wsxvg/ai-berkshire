#!/usr/bin/env python3
"""Overnight: 未曾测试过的策略全量回测"""
import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backtest.engine.backtest import run_backtest

BASE = {'start_date':'2025-01-05','end_date':'2026-07-01',
        'initial_cash':3000,'monthly_injection':3000,
        'weights':{'quality':25,'cost':20,'manager':20,'momentum':15,'smart_money':20}}
K_BASE = {'min_score':0.0,'no_stop_loss':True,'take_profit_pct':1000,
          'profit_mode':'half','cost_penalty':0,'min_consensus':2,
          'fund_type_filter':'all','momentum_sell':0,'max_position_pct':100,
          'exclude_uids':[4968958,16020895,14345330]}
# 最佳行业分散
BEST = {'max_sector_pct':24}

def run_one(name, **o):
    c=dict(BASE);c.update(K_BASE);c.update(BEST);c.update(o)
    run_backtest._last_rank_date=None
    try:
        r=run_backtest(c);ti=r.get('monthly_injections',0)+3000
        return {'name':name,'ret':r['total_return'],'profit':r['daily_values'][-1]['total']-ti,
                'dd':r['max_drawdown'],'trades':r['trade_count'],'hold':r['final_holdings'],
                'sp':r['total_return']/max(r['max_drawdown'],1)}
    except Exception as e: return {'name':name,'ret':-999,'profit':0,'dd':0,'trades':0,'hold':0,'sp':-999}

results = []

# ═══ 1. 浮动止损: 从高点回撤X%就卖 ═══
# 引擎不支持浮动止损，用stop_loss_pct近似
print("=== 浮动止损(用固定止损近似) ===")
for sl in [-5,-8,-10,-12,-15,-20]:
    r=run_one(f'止损{abs(sl)}%',no_stop_loss=False,stop_loss_pct=sl)
    if r: results.append(r);print(f'  止损{abs(sl)}%: ret={r["ret"]:+.2f}% profit={r["profit"]:>7.0f} dd={r["dd"]:.2f}%')

# ═══ 2. 时间止损: 买入后30/60天检查收益 ═══
# 引擎没有时间止损参数，用momentum_sell近似（动量差就卖）
print("\n=== 时间止损(用动量卖出近似) ===")
for mom in [1.5,1.8,2.0,2.2,2.5]:
    r=run_one(f'动量{mom}卖',momentum_sell=mom)
    if r: results.append(r);print(f'  动量{mom}: ret={r["ret"]:+.2f}% profit={r["profit"]:>7.0f} dd={r["dd"]:.2f}%')

# ═══ 3. 动量+行业分散组合 ═══
print("\n=== 动量+行业分散 ===")
for sec in [22,24,25]:
    for mom in [1.8,2.0,2.2]:
        r=run_one(f'M{mom}+行业{sec}',momentum_sell=mom,max_sector_pct=sec)
        if r: results.append(r);print(f'  M{mom}+行业{sec}: ret={r["ret"]:+.2f}% profit={r["profit"]:>7.0f} dd={r["dd"]:.2f}%')

# ═══ 4. 利润保护: 盈利>50%后收紧止损 ═══
print("\n=== 止盈(利润保护) ===")
for tp in [15,20,25,30,40,50,60,80,100]:
    for mode in ['half','quarter']:
        r=run_one(f'TP{tp}-{mode}',take_profit_pct=tp,profit_mode=mode)
        if r: results.append(r);print(f'  TP{tp}-{mode}: ret={r["ret"]:+.2f}% profit={r["profit"]:>7.0f} dd={r["dd"]:.2f}%')

# ═══ 5. 阶梯止盈+行业分散 ═══
print("\n=== 阶梯止盈+行业分散 ===")
for sec in [22,24,25]:
    for tp in [15,20,25,30]:
        r=run_one(f'STEP{tp}+行业{sec}',take_profit_pct=tp,profit_mode='step',max_sector_pct=sec)
        if r: results.append(r);print(f'  STEP{tp}+行业{sec}: ret={r["ret"]:+.2f}% profit={r["profit"]:>7.0f} dd={r["dd"]:.2f}%')

# ═══ 6. 四分止盈+行业分散 ═══
print("\n=== 四分止盈+行业分散 ===")
for sec in [22,24,25]:
    for tp in [20,30,40,50]:
        r=run_one(f'QTR{tp}+行业{sec}',take_profit_pct=tp,profit_mode='quarter',max_sector_pct=sec)
        if r: results.append(r);print(f'  QTR{tp}+行业{sec}: ret={r["ret"]:+.2f}% profit={r["profit"]:>7.0f} dd={r["dd"]:.2f}%')

# ═══ 7. 基准对比 ═══
print("\n=== 基准 ===")
r=run_one('基准-排末3+行业24%')
if r: results.append(r);print(f'  基准: ret={r["ret"]:+.2f}% profit={r["profit"]:>7.0f} dd={r["dd"]:.2f}% sp={r["sp"]:.2f}')

# ═══ 最终排名 ═══
print(f'\n{"="*110}')
print("OVERNIGHT FINAL RANKING (by Sharpe)")
print(f'{"="*110}')
hdr = "{:40s} {:>8s} {:>8s} {:>7s} {:>8s} {:>5s}".format("Strategy","Ret","Profit","DD","Sharpe","Trds")
print(hdr);print('-'*110)
for r in sorted(results,key=lambda x:x['sp'],reverse=True):
    print(f"{r['name']:40s} {r['ret']:>+7.2f}% {r['profit']:>8.0f} {r['dd']:>7.2f}% {r['sp']:>8.2f} {r['trades']:>4d}")

# 按净赚排名
print(f'\n{"="*110}')
print("OVERNIGHT BY PROFIT")
print(f'{"="*110}')
for r in sorted(results,key=lambda x:x['profit'],reverse=True)[:15]:
    print(f"{r['name']:40s} {r['ret']:>+7.2f}% {r['profit']:>8.0f} {r['dd']:>7.2f}% {r['sp']:>8.2f}")

out = Path(__file__).resolve().parent.parent / "backtest" / "reports" / "overnight.json"
json.dump(sorted(results,key=lambda x:x['sp'],reverse=True),open(out,'w',encoding='utf-8'),ensure_ascii=False,indent=2)
print(f'\nSaved to {out}')
