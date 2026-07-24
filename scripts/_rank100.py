"""多维度拉取收益率榜，突破100人限制。
rankType: 400=收益最多, 200=人气最佳, 100=买入最多, 300=持仓大佬 (不设=默认收益率榜)
fundHoldAmountLevel: (Head API未返回选项，暂不使用)
rankSortBy: 0=收益榜(金额), 1=收益率榜(百分比)
timeCycle: 1=近一周, 2=近一月, 5=近一年
"""
import json, sys, time, urllib.request, urllib.parse
from pathlib import Path
from datetime import datetime
from collections import defaultdict

sys.stdout.reconfigure(line_buffering=True)  # 行缓冲，实时输出

PROJECT = Path(".")
sys.path.insert(0, str(PROJECT))
from tools.jd_finance_api import _load_cookies, _JD_BASE, _USER_AGENT, FOLLOWED_USERS

ck = _load_cookies()
print(f"Cookies: {len(ck)} keys, Current: {len(FOLLOWED_USERS)} users")

def fetch_rank(rank_type, hold_level, rank_sort_by="1", time_cycle="5", last_id=None):
    """直接调用排行榜API，支持所有筛选参数。
    注意：time_cycle正确值为1/2/5，旧代码用的401是无效值。"""
    body_data = {
        "lastId": last_id,
        "rankSortBy": rank_sort_by,
        "timeCycle": time_cycle,
    }
    # 只在rank_type有值时才加rankType（不设=默认收益率榜，rankColumnValue才是百分比）
    if rank_type:
        body_data["rankType"] = rank_type
    if hold_level:
        body_data["fundHoldAmountLevel"] = hold_level
    body = f"reqData={urllib.parse.quote(json.dumps(body_data))}".encode("utf-8")
    url = f"{_JD_BASE}/gw2/generic/redEnv001/h5/m/queryFundFirmOfferMultiRank"
    req = urllib.request.Request(url, data=body, headers={
        "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
        "User-Agent": _USER_AGENT,
    })
    req.add_header("Cookie", "; ".join(f"{k}={v}" for k, v in ck.items()))
    try:
        resp = urllib.request.urlopen(req, timeout=15)
        data = json.loads(resp.read())
    except Exception as e:
        return {"users": [], "error": str(e)}

    rd = data.get("resultData", {}).get("data", {})
    raw_users = rd.get("fundRankList", [])
    users = []
    for u in raw_users:
        info = u.get("userInfo", {})
        def _text(v):
            if isinstance(v, dict):
                return v.get("text", "")
            return str(v) if v else ""
        user_uid = info.get("userUid", "")
        numeric_id = user_uid.replace("jimu_user_info-", "") if "jimu_user_info-" in str(user_uid) else user_uid
        users.append({
            "name": info.get("userName", ""),
            "numeric_id": numeric_id,
            "return_rate": _text(u.get("rankColumnValue")),
            "total_return": _text(u.get("rankColumnName")),
            "holdings_value": _text(u.get("showColumnValue", "")),
        })
    return {
        "users": users,
        "last_id": rd.get("lastId"),
        "is_end": rd.get("isEnd") or rd.get("is_end"),
    }

# 多维度组合拉取
# 注意：不同rankType返回的rankColumnValue含义不同！
# 不设rankType(默认) + rankSortBy=1: rankColumnValue=收益率%, rankColumnName=收益额
# rankType=300(持仓大佬): rankColumnValue=持仓金额(非百分比!)
# rankType=200(人气最佳): rankColumnValue=人气值
# rankType=100(买入最多): rankColumnValue=买入额
# 因此只有默认(不设rankType)才能拿到真正的收益率排名
RANK_TYPES = [
    (None, "收益率榜(默认)"),
]
HOLD_LEVELS = [
    (None, "不限"),
]

all_users = []
seen_ids = set()
best_return = {}  # nid -> best return rate

for rt, rt_name in RANK_TYPES:
    for hl, hl_name in HOLD_LEVELS:
        last = None
        for page in range(15):
            r = fetch_rank(rank_type=rt, hold_level=hl, rank_sort_by="1", time_cycle="5", last_id=last)
            users = r.get("users", [])
            if not users:
                break
            new_count = 0
            for u in users:
                nid = str(u.get("numeric_id", ""))
                ret_str = str(u.get("return_rate", "0")).replace("%", "").replace("+", "")
                try:
                    ret = float(ret_str)
                except:
                    ret = 0
                if nid not in seen_ids:
                    seen_ids.add(nid)
                    all_users.append(u)
                    new_count += 1
                # 保留最高收益率
                if nid not in best_return or ret > best_return[nid]:
                    best_return[nid] = ret
            last = r.get("last_id")
            if r.get("is_end") or not users:
                break
            time.sleep(0.3)
        label = f"[{rt_name}/{hl_name}]"
        if len(all_users) % 10 == 0 or new_count > 0:
            print(f"  {label:25s} total={len(all_users)} (new this combo: {new_count})")
        time.sleep(0.2)

print(f"\n=== 总计: {len(all_users)} 位去重大佬 ===")

# 收益率分布
returns = sorted(best_return.values(), reverse=True)
if returns:
    print(f"\n收益率分布:")
    for i in [0, 9, 49, 99, 199, 499, 999]:
        if i < len(returns):
            print(f"  Top{i+1:4d}: {returns[i]:+.1f}%")
    print(f"  最末位: {returns[-1]:+.1f}%")

# 加载本地交易数据
trading = json.loads((PROJECT / "backtest/data/trading_by_date_fixed.json").read_text("utf-8"))
uid_stats = defaultdict(lambda: {"buy": 0, "sell": 0, "funds": set(), "last": "0000"})
for date, trades in trading.items():
    for rec in trades:
        uid = str(rec.get("_uid", ""))
        if not uid:
            continue
        act = rec.get("action", "")
        if "\u4e70\u5165" in act:
            uid_stats[uid]["buy"] += 1
        elif "\u5356\u51fa" in act:
            uid_stats[uid]["sell"] += 1
        uid_stats[uid]["funds"].add(rec.get("fund_name", ""))
        if date > uid_stats[uid]["last"]:
            uid_stats[uid]["last"] = date

# 分析现有大佬
now = datetime(2026, 7, 24)
existing_ids = set(FOLLOWED_USERS.keys())
zombie, single_bet, no_trades, normal = [], [], [], []

for uid, name in FOLLOWED_USERS.items():
    s = uid_stats.get(uid, {"buy": 0, "sell": 0, "funds": set(), "last": "0000"})
    buy = s["buy"]
    nf = len(s["funds"])
    try:
        days = (now - datetime.strptime(s["last"], "%Y-%m-%d")).days
    except:
        days = 9999
    if buy == 0:
        no_trades.append((uid, name))
    elif days > 180:
        zombie.append((uid, name, days, buy, nf))
    elif nf <= 2:
        single_bet.append((uid, name, nf, buy, days))
    else:
        normal.append((uid, name, buy, nf, days))

print(f"\n现有大佬分析 ({len(FOLLOWED_USERS)}人):")
print(f"  正常活跃: {len(normal)}")
print(f"  僵尸(>180天): {len(zombie)}")
print(f"  单押(<=2基金): {len(single_bet)}")
print(f"  无交易记录: {len(no_trades)}")

if zombie:
    print(f"\n--- 僵尸大佬 ---")
    for uid, name, days, buy, nf in sorted(zombie, key=lambda x: -x[2]):
        print(f"  {name:20s} uid={uid:12s} 不活跃{days:4d}天 买入{buy}次 {nf}只基金")

if single_bet:
    print(f"\n--- 单押大佬 ---")
    for uid, name, nf, buy, days in sorted(single_bet, key=lambda x: x[2]):
        print(f"  {name:20s} uid={uid:12s} {nf}只基金 买入{buy}次 不活跃{days}天")

if no_trades:
    print(f"\n--- 无交易记录 ({len(no_trades)}) ---")
    for uid, name in no_trades:
        print(f"  {name:20s} uid={uid:12s}")

# 排行榜中未关注的大佬
ranked_not_followed = []
for u in all_users:
    nid = str(u.get("numeric_id", ""))
    name = u.get("name", "")
    ret = best_return.get(nid, 0)
    if nid not in existing_ids:
        s = uid_stats.get(nid, {"buy": 0, "funds": set(), "last": "0000"})
        ranked_not_followed.append({
            "uid": nid, "name": name, "ret": ret,
            "buy": s["buy"], "funds": len(s["funds"]), "last": s["last"],
        })

ranked_not_followed.sort(key=lambda x: -x["ret"])
print(f"\n=== 未关注大佬: {len(ranked_not_followed)} 人 ===")
print(f"\nTop 50 (按收益率):")
print(f"{'排名':>4s} {'收益率':>8s} {'买入':>4s} {'基金':>4s} {'uid':12s} {'名称'}")
for i, u in enumerate(ranked_not_followed[:50]):
    print(f"{i+1:4d} {u['ret']:+7.1f}% {u['buy']:4d} {u['funds']:4d} {u['uid']:12s} {u['name'][:25]}")

# 当前关注大佬最差收益率
existing_returns = []
for u in all_users:
    nid = str(u.get("numeric_id", ""))
    if nid in existing_ids:
        existing_returns.append((u.get("name", ""), nid, best_return.get(nid, 0)))
existing_returns.sort(key=lambda x: x[2])
print(f"\n当前关注大佬收益率排名:")
print(f"  最差10个:")
for name, uid, ret in existing_returns[:10]:
    print(f"    {ret:+6.1f}%  {name:20s} uid={uid}")
print(f"  最好10个:")
for name, uid, ret in existing_returns[-10:]:
    print(f"    {ret:+6.1f}%  {name:20s} uid={uid}")

# 建议添加：收益率>50% 且有本地交易数据(买入>=5) 且基金数>=3
to_add = [u for u in ranked_not_followed if u["ret"] > 50 and u["buy"] >= 5 and u["funds"] >= 3]
print(f"\n=== 建议添加: {len(to_add)} 人 (ret>50% + buy>=5 + funds>=3) ===")
for u in to_add:
    print(f'    "{u["uid"]}": "{u["name"]}",  # ret={u["ret"]:+.1f}% buy={u["buy"]} funds={u["funds"]}')

# 保存结果
result = {
    "total_ranked": len(all_users),
    "current_followed": len(FOLLOWED_USERS),
    "untracked": len(ranked_not_followed),
    "to_remove_zombie": [{"uid": uid, "name": name} for uid, name in no_trades] +
                         [{"uid": uid, "name": name} for uid, name, *_ in zombie] +
                         [{"uid": uid, "name": name} for uid, name, *_ in single_bet],
    "to_add_qualified": [{"uid": u["uid"], "name": u["name"], "ret": u["ret"]} for u in to_add],
    "all_untracked_top100": [{"uid": u["uid"], "name": u["name"], "ret": u["ret"]} for u in ranked_not_followed[:100]],
}
with open("data/expansion_report.json", "w", encoding="utf-8") as f:
    json.dump(result, f, ensure_ascii=False, indent=2)
print(f"\nSaved to data/expansion_report.json")
