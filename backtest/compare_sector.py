#!/usr/bin/env python3
import json, glob, os, sys
sys.stdout.reconfigure(encoding='utf-8')
from collections import Counter

def name_sector(name):
    name = name or ""
    if "半导体" in name or "芯片" in name: return "半导体"
    if "AI" in name or "人工智能" in name: return "AI"
    if "科技" in name or "信息" in name: return "科技"
    if "医疗" in name or "医药" in name: return "医疗"
    if "消费" in name: return "消费"
    if "新能源" in name or "能源" in name: return "新能源"
    if "金融" in name or "银行" in name: return "金融"
    if "地产" in name or "基建" in name: return "地产基建"
    if "军工" in name or "国防" in name: return "军工"
    if "农业" in name or "养殖" in name: return "农业"
    if "港股" in name or "恒生" in name: return "港股"
    if "红利" in name or "股息" in name: return "红利"
    if "债券" in name or "债" in name: return "债券"
    if "货币" in name: return "货币"
    if "混合" in name or "成长" in name or "价值" in name: return "混合"
    if "指数" in name or "ETF" in name or "联接" in name: return "指数"
    return "其他"

def stock_sec(name):
    n = name or ''
    if '半导体' in n or '芯片' in n or '科创' in n: return '半导体'
    if '科技' in n or '软件' in n or '信息' in n or '通信' in n or '电子' in n: return '科技'
    if '医疗' in n or '医药' in n or '生物' in n or '药' in n: return '医疗'
    if '新能源' in n or '光伏' in n or '风电' in n or '电池' in n or '锂' in n: return '新能源'
    if '消费' in n or '白酒' in n or '食品' in n or '饮料' in n or '家电' in n: return '消费'
    if '金融' in n or '银行' in n or '证券' in n or '保险' in n: return '金融'
    if '地产' in n or '基建' in n or '建筑' in n: return '地产基建'
    if '军工' in n or '国防' in n or '航天' in n: return '军工'
    if '能源' in n or '石油' in n or '煤炭' in n or '矿' in n: return '能源'
    if '汽车' in n or '车' in n: return '汽车'
    if '传媒' in n or '游戏' in n or '互联' in n: return '传媒互联网'
    return '其他'

holdings = {}
for f in glob.glob('data/fund_cache/fund_holdings_*.json'):
    try:
        d = json.load(open(f,'r',encoding='utf-8'))
        stocks = d.get('top_stocks',[])
        if stocks: holdings[d.get('fund_code','')] = stocks
    except: pass

profiles = {}
for f in glob.glob('data/fund_cache/fund_profile_*.json'):
    try:
        d = json.load(open(f,'r',encoding='utf-8'))
        profiles[d['fund_code']] = d.get('full_name','')
    except: pass

print("Holdings-based sector vs Name-based sector comparison:")
print("")
mismatch = 0
for code in sorted(holdings.keys()):
    fn = profiles.get(code, '')
    ns = name_sector(fn)
    stocks = holdings[code]
    sr = Counter()
    for s in stocks:
        sec = stock_sec(s.get('name',''))
        r = float(str(s.get('ratio','0')).replace('%',''))
        sr[sec] += r
    top3 = sr.most_common(3)
    hs = top3[0][0] if top3 else '无'
    if ns != hs:
        mismatch += 1
        top3_str = '; '.join(["%s(%.0f%%)" % (s, r) for s, r in top3[:3]])
        stock_names = ', '.join([s["name"] for s in stocks[:5]])
        print("❌ %s %s" % (code, fn[:35]))
        print("   名字分类: %s  持仓分类: %s" % (ns, hs))
        print("   TOP3: %s" % top3_str)
        print("   前5持仓: %s" % stock_names)
        print("")

total = len(holdings)
print("结果: %d/%d 不匹配 (%.0f%% 匹配率)" % (mismatch, total, (1-mismatch/total)*100))