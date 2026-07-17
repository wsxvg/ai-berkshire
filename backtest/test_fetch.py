#!/usr/bin/env python3
"""快速测试单个用户交易记录抓取"""
import sys, time
from pathlib import Path
PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))
from tools.jd_finance_api import get_trading_records, _load_cookies, FOLLOWED_USERS

cookies = _load_cookies()
uid = list(FOLLOWED_USERS.keys())[0]
name = FOLLOWED_USERS[uid]
print(f"Testing uid={uid} name={name}")
t0 = time.time()
r = get_trading_records(f"jimu_user_info-{uid}", cookies=cookies, today_only=False, max_pages=2)
recs = r.get("records", [])
print(f"Got {len(recs)} records in {time.time()-t0:.1f}s")
if recs:
    print(f"Sample: {recs[0]}")
