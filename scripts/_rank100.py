"""拉取收益率榜前100，用 numeric_id 匹配 + 自动补充新用户"""
import json, sys, time
from pathlib import Path
from datetime import datetime

PROJECT = Path(".")
sys.path.insert(0, str(PROJECT))
from tools.jd_finance_api import get_fund_ranking, get_user_holdings, _load_cookies

ck = _load_cookies()
print(f"Cookies: {len(ck)} keys")

# 拉取前100
all_users = []
last = None
for i in range(10):
    r = get_fund_ranking(cookies=ck, rank_sort_by="1", last_id=last)
    users = r.get("users", [])
    all_users.extend(users)
    last = r.get("last_id")
    if r.get("is_end") or not users:
        break
print(f"Page {i+1}: {len(all_users)} users total")

# 现有 FOLLOWED_USERS
from tools.jd_finance_api import FOLLOWED_USERS
existing_ids = set(FOLLOWED_USERS.values())  # numeric IDs we already have

# 匹配本地交易数据
trading = json.loads((PROJECT / "backtest/data/trading_by_date_fixed.json").read_text("utf-8"))
name_to_uid = {}
for dr in trading.values():
    for rec in dr:
        u = rec.get("_user", "")
        uid = rec.get("_uid", "")
        if u and uid:
            name_to_uid[u] = uid

# 分类
now = datetime(2026, 7, 14)
normal, single_bet, zombie, nodata = [], [], [], []

for u in all_users:
    name = u.get("name", "")
    num_id = u.get("numeric_id", "")
    ret_str = str(u.get("return_rate", "0")).replace("%", "").replace("+", "")
    try: ret = float(ret_str)
    except: ret = 0

    # Try to find in trading data by numeric_id or name
    uid = ""
    if num_id:
        uid = num_id
    else:
        uid = name_to_uid.get(name, "")

    if not uid:
        nodata.append((name, num_id, ret))
        continue

    # Check trading data
    funds = set()
    last_date = "0000"
    trades = 0
    for ds in sorted(trading.keys()):
        for rec in trading[ds]:
            if str(rec.get("_uid", "")) == uid and "买入" in rec.get("action", ""):
                funds.add(rec.get("fund_name", ""))
                trades += 1
                if ds > last_date:
                    last_date = ds

    try: last_dt = datetime.strptime(last_date, "%Y-%m-%d")
    except: last_dt = now
    days = (now - last_dt).days
    entry = (name, ret, len(funds), days, trades, num_id)
    if days > 365:
        zombie.append(entry)
    elif len(funds) <= 3:
        single_bet.append(entry)
    else:
        normal.append(entry)

total = len(normal) + len(single_bet) + len(zombie)
print(f"\nNormal: {len(normal)} | Single: {len(single_bet)} | Zombie: {len(zombie)} | NoData: {len(nodata)}")
if total:
    print(f"Qualified: {len(normal)/total*100:.0f}% | Single: {len(single_bet)/total*100:.0f}% | Zombie: {len(zombie)/total*100:.0f}%")

print(f"\nNormal TOP20:")
for name, ret, nf, di, tr, nid in sorted(normal, key=lambda x: -x[1])[:20]:
    print(f"  ret={ret:+6.1f}% funds={nf:>3} inactive={di:>4}d id={nid} {name[:20]}")

if single_bet:
    print(f"\nSingle bet ({len(single_bet)}):")
    for name, ret, nf, di, tr, nid in single_bet[:10]:
        print(f"  ret={ret:+6.1f}% funds={nf:>3} id={nid} {name[:20]}")

if zombie:
    print(f"\nZombie ({len(zombie)}):")
    for name, ret, nf, di, tr, nid in zombie[:10]:
        print(f"  ret={ret:+6.1f}% funds={nf:>3} id={nid} {name[:20]}")

# 新用户（nodata）- 看看要不要加
print(f"\nNo local data: {len(nodata)}")
new_to_add = []
for name, num_id, ret in nodata[:20]:
    in_follow = str(num_id) in existing_ids if num_id else False
    tag = "(已有)" if in_follow else "(NEW)"
    print(f"  ret={ret:+6.1f}% id={num_id} {tag} {name[:25]}")
    if num_id and not in_follow:
        new_to_add.append((name, num_id, ret))

print(f"\n=== Verdict ===")
print(f"Total in ranking: {len(all_users)}")
print(f"With local data: {total} (正常:{len(normal)})")
print(f"No local data: {len(nodata)} (其中已有FOLLOW: {sum(1 for n,i,r in nodata if str(i) in existing_ids)})")
new_count = len([1 for _, nid, _ in nodata if nid and str(nid) not in existing_ids])
print(f"\nNew unseen users to consider: {new_count}")
if new_to_add:
    print(f"Top new users (by return):")
    for name, nid, ret in sorted(new_to_add, key=lambda x: -x[2])[:10]:
        print(f"  {name[:20]} id={nid} ret={ret:+.1f}%")
