"""从 holdings + fund_cache 直接取代码，不绕名字匹配"""
import json, traceback
from pathlib import Path

PROJECT = Path(".")
name_map = json.loads((PROJECT / "data/fund_name_map.json").read_text("utf-8"))
trading = json.loads((PROJECT / "backtest/data/trading_by_date_fixed.json").read_text("utf-8"))
charts = json.loads((PROJECT / "backtest/data/fund_charts.json").read_text("utf-8"))

unmapped = set()
for day_recs in trading.values():
    for r in day_recs:
        fn = r.get("fund_name", "")
        if fn and fn not in name_map and "买入" in r.get("action", ""):
            unmapped.add(fn)

print(f"Unmapped: {len(unmapped)}")

# 数据源1: 所有 holdings_snapshot 文件
added = 0
for spath in sorted(Path("data").glob("holdings_snapshot*.json")):
    try:
        snap = json.loads(spath.read_text("utf-8"))
        for uid, funds in snap.get("holdings", {}).items():
            for f in (funds if isinstance(funds, list) else []):
                if not isinstance(f, dict): continue
                fn = f.get("name", f.get("fundName", ""))
                fc = f.get("code", f.get("fundCode", ""))
                if fn in unmapped and fc:
                    name_map[fn] = fc
                    unmapped.discard(fn)
                    added += 1
    except: pass
print(f"holdings: +{added}, remaining: {len(unmapped)}")

# 数据源2: trading_records_cache 和其他 trading_records 文件
for rpath in sorted(Path("data").glob("trading_records*.json")):
    try:
        recs = json.loads(rpath.read_text("utf-8"))
        for r in (recs if isinstance(recs, list) else []):
            fn = r.get("fund_name", "")
            fc = r.get("fund_code", r.get("fundCode", ""))
            if fn in unmapped and fc:
                name_map[fn] = fc
                unmapped.discard(fn)
                added += 1
    except: pass
print(f"trading_records: +{added}, remaining: {len(unmapped)}")

# 数据源3: fund_cache 中所有 profile 里的 fundName → code
for fpath in Path("data/fund_cache").glob("fund_data_*.json"):
    try:
        data = json.loads(fpath.read_text("utf-8"))
        profile = data.get("profile", {})
        fname = profile.get("fundFullName", profile.get("fundName", ""))
        fcode = fpath.stem.replace("fund_data_", "")
        if fname and fname in unmapped and fcode:
            name_map[fname] = fcode
            unmapped.discard(fname)
            added += 1
    except: pass
print(f"fund_cache: +{added}, remaining: {len(unmapped)}")

# 数据源4: fund_holdings cache 文件中的 name→code
for fpath in Path("data/fund_cache").glob("fund_holdings_*.json"):
    try:
        data = json.loads(fpath.read_text("utf-8"))
        for item in data.get("top_stocks", []):
            pass  # stock holdings don't have fund name
    except: pass

# 保存
(PROJECT / "data/fund_name_map.json").write_text(
    json.dumps(name_map, ensure_ascii=False, indent=2), encoding="utf-8")

# Coverage
resolved = sum(1 for day_recs in trading.values() for r in day_recs
               if "买入" in r.get("action", "") and name_map.get(r.get("fund_name", ""), "") in charts)
total = sum(1 for day_recs in trading.values() for r in day_recs
            if "买入" in r.get("action", ""))
print(f"\n=== FINAL ===")
print(f"map: {len(name_map)} entries, charts: {len(charts)} funds")
print(f"Coverage: {resolved}/{total} ({resolved/total*100:.1f}%)")
