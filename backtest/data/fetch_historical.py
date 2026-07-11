#!/usr/bin/env python3
"""Step 1: 拉取历史数据（一次性）。
- 21位大佬的交易记录（1月~7月）
- 376只基金的 chart_data（240点/只）
- 所有基金的基本信息（费率、经理、类型）

输出到 backtest/data/ 目录。
"""
import json, sys, time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tools.jd_finance_api import (
    FOLLOWED_USERS, _ensure_cookies,
    get_trading_records, get_fund_chart_data,
    get_fund_trade_rules, get_fund_manager,
    get_fund_profile, get_fund_holdings_distribution,
)
from tools.fund_scorer import score_fund, FundScore

BACKTEST_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BACKTEST_DIR / "data"
PROJECT_DIR = BACKTEST_DIR.parent
CACHE_DIR = PROJECT_DIR / "data" / "fund_cache"

def fetch_all_trading_history(max_pages=50):
    """拉取所有大佬的全部历史交易记录（不按 today_only 过滤）。"""
    cookies = _ensure_cookies()
    all_records = []
    total_pulled = 0

    for nid, name in FOLLOWED_USERS.items():
        uid = f"jimu_user_info-{nid}"
        print(f"  [{name}] ", end="", flush=True)
        try:
            result = get_trading_records(uid, size=20, cookies=cookies,
                                         max_pages=max_pages, today_only=False)
            records = result.get("records", [])
            for r in records:
                r["_user"] = name
                r["_uid"] = nid
            all_records.extend(records)
            total_pulled += len(records)
            print(f"{len(records)} records")
        except Exception as e:
            print(f"FAILED: {e}")

        time.sleep(0.3)  # be polite

    print(f"\n  总计: {total_pulled} 条记录")
    return all_records


def fetch_all_fund_charts(fund_codes, max_workers=10):
    """批量拉取基金 chart_data（净值序列）。"""
    charts = {}
    done = 0

    def fetch(code):
        try:
            c = get_fund_chart_data(code)
            pts = c.get("chart_points", [])
            return code, pts
        except Exception:
            return code, []

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futs = {pool.submit(fetch, c): c for c in fund_codes}
        for fut in as_completed(futs):
            code, pts = fut.result()
            if pts:
                charts[code] = pts
            done += 1
            if done % 50 == 0:
                print(f"    {done}/{len(fund_codes)}")

    print(f"  Chart data: {len(charts)}/{len(fund_codes)} funds")
    return charts


def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # ── 1. 交易记录 ──
    history_file = DATA_DIR / "trading_history.json"
    if history_file.exists():
        print(f"  交易记录已存在 ({history_file})，跳过拉取")
        with open(history_file, "r", encoding="utf-8") as f:
            all_records = json.load(f)
    else:
        print("拉取全部历史交易记录...")
        all_records = fetch_all_trading_history(max_pages=50)
        with open(history_file, "w", encoding="utf-8") as f:
            json.dump(all_records, f, ensure_ascii=False, indent=2)
        print(f"  已保存到 {history_file}")

    # ── 2. 按日期分组 ──
    by_date = {}
    for r in all_records:
        d = r.get("_date_prefix", "")[:5]
        if not d:
            continue
        by_date.setdefault(d, []).append(r)
    dates = sorted(by_date.keys())
    print(f"  日期范围: {dates[0]} ~ {dates[-1]} ({len(dates)} 个交易日)")

    date_file = DATA_DIR / "trading_by_date.json"
    # 只保留日期键，便于回测读取
    by_date_simple = {d: [{
        "fund_name": r.get("fund_name", ""),
        "action": r.get("action", ""),
        "amount": r.get("amount", ""),
        "_user": r.get("_user", ""),
    } for r in records] for d, records in by_date.items()}
    with open(date_file, "w", encoding="utf-8") as f:
        json.dump(by_date_simple, f, ensure_ascii=False, indent=2)
    print(f"  按日期分组已保存 ({date_file})")

    # ── 3. 收集所有在交易记录中出现的基金代码 ──
    fund_names = set()
    for r in all_records:
        fn = r.get("fund_name", "")
        if fn:
            fund_names.add(fn)

    # 从交易记录的 detail 字段提取基金代码
    import re
    name_to_code = {}
    for r in all_records:
        detail = r.get("detail", "")
        fn = r.get("fund_name", "")
        m = re.search(r"基金(\d{6})", detail)
        if m and fn:
            name_to_code[fn] = m.group(1)

    # 也从 holdings_snapshot 补充
    snap_file = PROJECT_DIR / "data" / "holdings_snapshot.json"
    if snap_file.exists():
        snap = json.loads(snap_file.read_text("utf-8"))
        for user, funds in snap.get("holdings", {}).items():
            for f in funds if isinstance(funds, list) else []:
                if isinstance(f, dict) and f.get("name") and f.get("code"):
                    name_to_code[f["name"]] = f["code"]

    known_codes = set(name_to_code.values())
    print(f"  已知基金代码: {len(known_codes)} 只")
    # 展示前 10 个
    for i, (name, code) in enumerate(sorted(name_to_code.items())[:10]):
        print(f"    {code} = {name[:20]}")

    # ── 4. 拉取 chart_data ──
    charts_file = DATA_DIR / "fund_charts.json"
    if charts_file.exists():
        print(f"  Chart 数据已存在，跳过拉取")
        with open(charts_file, "r", encoding="utf-8") as f:
            charts = json.load(f)
    else:
        print(f"  拉取 {len(known_codes)} 只基金的 chart_data...")
        charts = fetch_all_fund_charts(list(known_codes))
        with open(charts_file, "w", encoding="utf-8") as f:
            json.dump(charts, f, ensure_ascii=False)
        print(f"  已保存到 {charts_file}")

    print(f"\nDone! Data saved to {DATA_DIR}")
    print(f"  交易记录: {len(all_records)} 条")
    print(f"  有交易的日期: {len(dates)} 天")
    print(f"  Chart 数据: {len(charts)} 只基金")


if __name__ == "__main__":
    main()