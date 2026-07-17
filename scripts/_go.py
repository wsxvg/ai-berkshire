"""完整分类：持仓数 + 最后活跃日期"""
import json, sys, time
from pathlib import Path
from datetime import datetime

PROJECT = Path(".")
sys.path.insert(0, str(PROJECT))
from tools.jd_finance_api import get_fund_ranking, _load_cookies, _api_form

ck = _load_cookies()
all_u = []
last = None
for i in range(10):
    r = get_fund_ranking(cookies=ck, rank_sort_by="1", last_id=last)
    users = r.get("users", [])
    all_u.extend(users)
    last = r.get("last_id")
    if r.get("is_end") or not users: break

trading = json.loads((PROJECT / "backtest/data/trading_by_date_fixed.json").read_text("utf-8"))
now = datetime(2026, 7, 14)

# 从本地交易数据构建每个用户的状态
local = {}
for ds in sorted(trading.keys()):
    for rec in trading[ds]:
        uid = rec.get("_uid", "")
        if uid not in local:
            local[uid] = {"funds": set(), "last_date": "0000"}
        if "买入" in rec.get("action", ""):
            local[uid]["funds"].add(rec.get("fund_name", ""))
        if ds > local[uid]["last_date"]:
            local[uid]["last_date"] = ds

normal = 0; single = 0; zombie = 0; nodata = 0
need_api = []

for i, u in enumerate(all_u):
    nid = u.get("numeric_id", "")
    name = u.get("name", "")
    ret = u.get("return_rate", "0")
    
    ld = local.get(nid, {})
    if ld and ld.get("trades", 0) > 0:
        # 有本地交易数据
        nf = len(ld.get("funds", set()))
        last_str = ld.get("last_date", "0000")
        try: last_dt = datetime.strptime(last_str, "%Y-%m-%d")
        except: last_dt = now
        di = (now - last_dt).days
        
        if di > 365: zombie += 1
        elif nf <= 3: single += 1
        else: normal += 1
    else:
        need_api.append((nid, name, ret))

# 对无本地数据的，调 API 看最后交易时间
print(f"Local data: {len(all_u) - len(need_api)}, Need API: {len(need_api)}")

for nid, name, ret in need_api:
    try:
        # 调持仓接口看基金数
        body = {
            "contentId": f"jimu_user_info-{nid}",
            "contentType": "personal",
            "pageSize": 1,
            "userType": "18"
        }
        data = _api_form("gw2/generic/redEnv001/h5/m/queryUserFundHoldingInfo", body, cookies=ck)
        funds = data.get("resultData", {}).get("data", {}).get("holdings", [])
        nf = len(funds)
        
        # 再看最近交易时间 - 用getTradingRecords 1条
        try:
            body2 = {
                "pageId": "11568", "pageType": "11568",
                "buildCodes": ["common", "feeds", "errorConfig", "topData"],
                "pageSize": 5,
                "busData": {"isFirstFeed": True, "pageSize": "5", "lastId": "", "end": False},
                "extParams": {"requestFrom": "pc", "targetUid": nid},
                "pageNum": 1, "clientVersion": "9.9.9", "clientType": "android"
            }
            data2 = _api_form("gw2/generic/aladdin/h5/m/getPageMutilData?pageId=11568", body2, cookies=ck)
            feeds = data2.get("resultData", {}).get("resultList", [])
            last_date = "0000"
            for feed in feeds:
                summary = feed.get("templateData", {}).get("transactionData", {}).get("cardHead", {}).get("tradeTime", "")
                if summary and len(summary) > 15:
                    last_date = summary[:10]
                elif summary and len(summary) >= 5:
                    # MM-DD format
                    mm, dd = summary[:2], summary[3:5]
                    last_date = f"2026-{mm}-{dd}"
            try: last_dt = datetime.strptime(last_date, "%Y-%m-%d")
            except: last_dt = datetime(2026, 1, 1)
            di = (now - last_dt).days
        except:
            di = 0  # can't determine, assume active
        
        if di > 365:
            zombie += 1
        elif nf <= 3:
            single += 1
        else:
            normal += 1
    except:
        nodata += 1
    time.sleep(0.4)

print(f"\nNORMAL: {normal} | SINGLE: {single} | ZOMBIE: {zombie} | NODATA: {nodata}")
total = normal + single + zombie + nodata
print(f"Normal rate: {normal}/{total} ({normal/total*100:.0f}%)")
print(f"Low-quality: {single+zombie+nodata} ({ (single+zombie+nodata)/total*100:.0f}%)")
