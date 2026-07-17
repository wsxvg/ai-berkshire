"""拉收益率榜TOP100，逐个分析交易模式"""
import json, sys
from pathlib import Path
from collections import defaultdict
from datetime import datetime

PROJECT = Path(".")
sys.path.insert(0, str(PROJECT))

from tools.jd_finance_api import get_fund_ranking

print("=== Fetching top users from JD ranking ===")
ranking = get_fund_ranking(rank_sort_by="1")  # "1"=收益率榜(百分比)
users = ranking.get("users", [])
print(f"Users: {len(users)}")

trading = json.loads((PROJECT / "backtest/data/trading_by_date_fixed.json").read_text("utf-8"))
now = datetime(2026, 7, 14)

normal, single, zombie, nodata = [], [], [], []
for i, u in enumerate(users):
    uid = str(u.get("userId", u.get("uid", "")))
    uname = u.get("nickName", u.get("userName", ""))
    ret_str = str(u.get("profitRate", u.get("returnRate", u.get("yieldRate", "0"))).replace("%","").replace("+","")
    try: ret = float(ret_str)
    except: ret = 0

    # 本地交易数据
    funds = set()
    last_date = "0000"
    all_trades = 0
    for date_str in sorted(trading.keys()):
        for r in trading[date_str]:
            if str(r.get("_uid", "")) == uid and "买入" in r.get("action", ""):
                funds.add(r.get("fund_name", ""))
                all_trades += 1
                if date_str > last_date: last_date = date_str

    nf = len(funds)
    if all_trades == 0:
        nodata.append((uid, uname, ret, 0, 0, 0))
        continue

    try: last_dt = datetime.strptime(last_date, "%Y-%m-%d")
    except: last_dt = now
    di = (now - last_dt).days
    entry = (uid, uname, ret, nf, di, all_trades)
    if di > 365: zombie.append(entry)
    elif nf <= 3: single.append(entry)
    else: normal.append(entry)

print(f"\nNormal: {len(normal)} | Single: {len(single)} | Zombie: {len(zombie)} | NoData: {len(nodata)}")
total = len(normal) + len(single) + len(zombie)
if total:
    print(f"Single-rate: {len(single)/total*100:.1f}%  Zombie-rate: {len(zombie)/total*100:.1f}%")
    print(f"Qualified (>3 funds, active): {len(normal)/total*100:.1f}%")

if normal:
    print(f"\nNormal TOP20:")
    for uid, uname, ret, nf, di, tr in sorted(normal, key=lambda x: -x[2])[:20]:
        print(f"  ret={ret:+6.1f}% funds={nf:>3} inactive={di:>4}d trades={tr:>5} {uname[:25]}")

if single:
    print(f"\nSingle bet ({len(single)}):")
    for uid, uname, ret, nf, di, tr in sorted(single, key=lambda x: -x[2])[:10]:
        print(f"  ret={ret:+6.1f}% funds={nf:>3} inactive={di:>4}d trades={tr:>5} {uname[:25]}")

if zombie:
    print(f"\nZombie ({len(zombie)}):")
    for uid, uname, ret, nf, di, tr in sorted(zombie, key=lambda x: -x[2])[:10]:
        print(f"  ret={ret:+6.1f}% funds={nf:>3} inactive={di:>4}d trades={tr:>5} {uname[:25]}")

if nodata:
    print(f"\nNo local data ({len(nodata)}):")
    for uid, uname, ret, _, _, _ in nodata[:10]:
        print(f"  ret={ret:+6.1f}% {uname[:30]}")

print(f"\n=== Verdict ===")
print(f"Total shown: {len(users)} users")
print(f"In local data: {total}, Qualified: {len(normal)} ({len(normal)/max(total,1)*100:.0f}%)")
print(f"Expanding to top 100 would add {len(single)+len(zombie)+len(nodata)} more low-quality or unknown users")
