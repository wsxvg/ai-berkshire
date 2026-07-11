#!/usr/bin/env python3
"""精细扫描 行业19-28% + 创意组合"""
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

def run_one(name, **o):
    c=dict(BASE);c.update(K_BASE);c.update(o)
    run_backtest._last_rank_date=None
    try:
        r=run_backtest(c);ti=r.get('monthly_injections',0)+3000
        return {'name':name,'ret':r['total_return'],'profit':r['daily_values'][-1]['total']-ti,
                'dd':r['max_drawdown'],'trades':r['trade_count'],'hold':r['final_holdings'],
                'sp':r['total_return']/max(r['max_drawdown'],1)}
    except Exception as e: print(f'FAIL {name}: {e}');return None

R=[]
for pct in [19,20,21,22,23,24,25,26,27,28]:
    r=run_one(f'行业{pct}%',max_sector_pct=pct)
    if r: R.append(r)

# 行业22%+创意组合
for tp in [0,30,50]:
    for mom in [0,1.8,2.0]:
        opts={'max_sector_pct':22}
        label=f'行业22%'
        if mom>0: opts['momentum_sell']=mom;label+=f'+M{mom}'
        if tp>0: opts.update({'take_profit_pct':tp,'profit_mode':'half'});label+=f'+TP{tp}'
        r=run_one(label,**opts)
        if r: R.append(r)

# 行业22%+QDII限制
for qdii in [30,40,50]:
    r=run_one(f'行业22%+QDII{qdii}',max_sector_pct=22,max_qdii_pct=qdii)
    if r: R.append(r)

# 创新想法：行业22%+共识3
r=run_one('行业22%+共识3',max_sector_pct=22,min_consensus=3)
if r: R.append(r)

# 基线
r=run_one('基线(排末3)')
if r: R.append(r)

hdr = "{:36s} {:>8s} {:>8s} {:>7s} {:>7s} {:>4s}".format("Strategy","Ret","Profit","DD","Sharpe","Hold")
print(f'\n{hdr}')
print('-'*75)
for r in sorted(R,key=lambda x:x['sp'],reverse=True):
    n=r['name'];rt=r['ret'];pf=r['profit'];dd=r['dd'];sp=r['sp'];hd=r['hold']
    print(f'{n:36s} {rt:>+7.2f}% {pf:>8.0f} {dd:>7.2f}% {sp:>7.2f} {hd:>4d}')

json.dump(sorted(R,key=lambda x:x['sp'],reverse=True),
          open(Path(__file__).resolve().parent.parent/'backtest/reports/fine_scan.json','w',encoding='utf-8'),
          ensure_ascii=False,indent=2)
print('\nSaved')