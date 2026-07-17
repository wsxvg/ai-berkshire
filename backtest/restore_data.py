#!/usr/bin/env python3
"""恢复交易数据：从京东金融抓取所有关注用户的完整交易记录，合并到 backtest/data/"""
import sys, json, time
from pathlib import Path
from datetime import date as dt_date
from concurrent.futures import ThreadPoolExecutor, as_completed

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))

from tools.jd_finance_api import get_trading_records, _load_cookies, FOLLOWED_USERS

print(f"=== 恢复交易数据: {len(FOLLOWED_USERS)} 个用户 ===")

cookies = _load_cookies()
if not cookies:
    print("ERROR: 无有效 cookie")
    sys.exit(1)

# 抓取所有用户的完整交易记录
all_records = []
t0 = time.time()

def fetch_one(uid, name):
    try:
        full_uid = f"jimu_user_info-{uid}" if not uid.startswith("jimu") else uid
        result = get_trading_records(full_uid, cookies=cookies, today_only=False, max_pages=200)
        records = result.get("records", [])
        for r in records:
            r["_user"] = name
            r["_uid"] = uid
        return uid, name, records
    except Exception as e:
        print(f"  [{name}] FAILED: {e}")
        return uid, name, []

with ThreadPoolExecutor(max_workers=10) as pool:
    futures = {pool.submit(fetch_one, uid, name): (uid, name) for uid, name in FOLLOWED_USERS.items()}
    for i, fut in enumerate(as_completed(futures)):
        uid, name, records = fut.result()
        all_records.extend(records)
        if (i+1) % 10 == 0:
            print(f"  进度: {i+1}/{len(FOLLOWED_USERS)} 用户, {len(all_records)} 条记录")

elapsed = time.time() - t0
print(f"\n抓取完成: {len(all_records)} 条记录 ({elapsed:.0f}s)")

# 保存到 trading_records_cache.json
cache_path = PROJECT / "data" / "trading_records_cache.json"
cache_path.write_text(json.dumps(all_records, ensure_ascii=False), encoding="utf-8")
print(f"保存: {cache_path}")

# ── 内联合并逻辑（不依赖 auto_pipeline 模块）──
trading_by_date_path = PROJECT / "backtest" / "data" / "trading_by_date_fixed.json"
existing = {}
if trading_by_date_path.exists():
    existing = json.loads(trading_by_date_path.read_text("utf-8"))

# 去重 key set
existing_keys = set()
for date_str, day_records in existing.items():
    for r in day_records:
        uid = str(r.get("_uid", ""))
        fname = r.get("fund_name", "")
        action = r.get("action", "")
        existing_keys.add((date_str, uid, fname, action))

today = dt_date.today()
current_month = today.month
added = 0
skipped = 0

for r in all_records:
    summary = str(r.get("summary", ""))
    date_str = ""
    if summary and "-" in summary:
        time_part = summary.split(" ")[0]
        parts = time_part.split("-")
        if len(parts) >= 3:
            try:
                d = dt_date(int(parts[0]), int(parts[1]), int(parts[2]))
                date_str = d.isoformat()
            except ValueError:
                pass
        elif len(parts) >= 2:
            try:
                mm, dd = int(parts[0]), int(parts[1])
                year = today.year
                if mm > current_month + 1:
                    year -= 1
                d = dt_date(year, mm, dd)
                date_str = d.isoformat()
            except ValueError:
                pass
    if not date_str:
        continue

    uid = str(r.get("_uid", ""))
    fname = r.get("fund_name", "")
    action = r.get("action", "")

    if not uid or not fname or not action:
        continue

    key = (date_str, uid, fname, action)
    if key in existing_keys:
        skipped += 1
        continue

    clean = {
        "_user": r.get("_user", ""),
        "_uid": uid,
        "fund_name": fname,
        "action": action,
        "amount": r.get("amount", ""),
        "_fund_id": r.get("_fund_id", ""),
    }
    # 补 fund_code
    fund_id = r.get("_fund_id", "")
    if fund_id and fund_id.isdigit() and len(fund_id) == 6:
        clean["fund_code"] = fund_id

    if date_str not in existing:
        existing[date_str] = []
    existing[date_str].append(clean)
    existing_keys.add(key)
    added += 1

# 保存
trading_by_date_path.write_text(json.dumps(existing, ensure_ascii=False), encoding="utf-8")
print(f"合并: +{added} 新增, -{skipped} 重复跳过")

# 验证
dates = [k for k in existing if "2025-01-05" <= k <= "2026-07-01"]
records_count = sum(len(existing[k]) for k in dates)
print(f"\n验证: {len(dates)} 天, {records_count} 条记录")
print(f"文件大小: {trading_by_date_path.stat().st_size} bytes")
