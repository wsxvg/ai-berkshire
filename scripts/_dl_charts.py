import json, sys, time
from pathlib import Path
PROJECT = Path(".")
sys.path.insert(0, str(PROJECT))
charts = json.loads((PROJECT/"backtest/data/fund_charts.json").read_text("utf-8"))
nm = json.loads((PROJECT/"data/fund_name_map.json").read_text("utf-8"))
cookies = json.loads((PROJECT/"data/jd_auth/cookies.json").read_text("utf-8"))
missing = sorted(set(nm.values()) - set(charts.keys()))
print(f"Missing charts: {len(missing)}")
if not missing: print("done!"); exit()
from tools.jd_finance_api import _api_post
ok=fail=0
for i,code in enumerate(missing):
    try:
        data=_api_post("gw/generic/jj/h5/m/getFundHistoryNetValuePageInfo",
                       {"fundCode":code,"pageNum":1,"pageSize":2000},cookies=cookies)
        nav=data.get("resultData",{}).get("datas",{}).get("netValueList",[])
        if nav:
            nav.sort(key=lambda x:x.get("date",""))
            base=next((float(n["netValue"]) for n in nav if float(n.get("netValue",0))>0),None)
            if base:
                pts=[{"xAxis":n["date"],"yAxis":round((float(n["netValue"])/base-1)*100,4)}
                     for n in nav if float(n.get("netValue",0))>0]
                if pts: charts[code]=pts; ok+=1
                else: fail+=1
            else: fail+=1
        else: fail+=1
    except: fail+=1
    if (i+1)%50==0:
        print(f"  {i+1}/{len(missing)} ok:{ok} fail:{fail}")
        (PROJECT/"backtest/data/fund_charts.json").write_text(json.dumps(charts,ensure_ascii=False))
    time.sleep(0.2)
(PROJECT/"backtest/data/fund_charts.json").write_text(json.dumps(charts,ensure_ascii=False))
trading=json.loads((PROJECT/"backtest/data/trading_by_date_fixed.json").read_text("utf-8"))
resolved=sum(1 for dr in trading.values() for r in dr if "买入" in r.get("action","") and nm.get(r.get("fund_name",""),"") in charts)
total=sum(1 for dr in trading.values() for r in dr if "买入" in r.get("action",""))
print(f"Charts: {len(charts)}, Coverage: {resolved}/{total} ({resolved/total*100:.1f}%)")
