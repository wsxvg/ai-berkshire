import json, sys
from pathlib import Path
from datetime import datetime

PROJECT = Path(".")
sys.path.insert(0, str(PROJECT))
from tools.jd_finance_api import get_fund_ranking, _load_cookies

ck = _load_cookies()
all_users = []
last = None
for i in range(10):
    r = get_fund_ranking(cookies=ck, rank_sort_by="1", last_id=last)
    users = r.get("users", [])
    all_users.extend(users)
    last = r.get("last_id")
    if r.get("is_end") or not users: break

trading = json.loads((PROJECT / "backtest/data/trading_by_date_fixed.json").read_text("utf-8"))
now = datetime(2026, 7, 14)

print(f"TOP {len(all_users)} USER RANKING")
print(f"Rank  Name                         Return    Funds  Active  Type")
print("-" * 80)

for i, u in enumerate(all_users):
    name = u.get("name", "?")
    nid = u.get("numeric_id", "")
    ret_str = str(u.get("return_rate", "0"))
    
    funds = set()
    last_date = "0000"
    for ds in sorted(trading.keys()):
        for rec in trading[ds]:
            if str(rec.get("_uid", "")) == nid and "买入" in rec.get("action", ""):
                funds.add(rec.get("fund_name", ""))
                if ds > last_date: last_date = ds
    
    nf = len(funds)
    try: last_dt = datetime.strptime(last_date, "%Y-%m-%d")
    except: last_dt = now
    di = (now - last_dt).days
    
    if nf == 0:
        tp = "NODATA"
    elif di > 365:
        tp = "ZOMBIE"
    elif nf <= 3:
        tp = "SINGLE"
    else:
        tp = "NORMAL"
    
    print(f"{i+1:>4}  {name[:28]:28s} {ret_str:>8s}  {nf:>5}  {di:>4}d  {tp}")
