"""从 tmp 缓存直接提取 fund_code → 覆盖率暴涨"""
import json
from pathlib import Path

PROJECT = Path(".")
name_map = json.loads((PROJECT / "data/fund_name_map.json").read_text("utf-8"))
charts = json.loads((PROJECT / "backtest/data/fund_charts.json").read_text("utf-8"))
trading = json.loads((PROJECT / "backtest/data/trading_by_date_fixed.json").read_text("utf-8"))

# 加载 tmp 缓存
cache = json.loads((PROJECT / "data/trading_records_cache.tmp").read_text("utf-8"))
funds = cache.get("funds", {})
added = 0
for name, info in funds.items():
    fc = info.get("fund_code", "")
    fn = info.get("fund_name", name)
    if fn and fc and fn not in name_map:
        name_map[fn] = fc
        added += 1
    # 也加 name 本身
    if name and fc and name not in name_map:
        name_map[name] = fc
        added += 1

print(f"Cache added: {added}, total map: {len(name_map)}")

# 保存
(PROJECT / "data/fund_name_map.json").write_text(
    json.dumps(name_map, ensure_ascii=False, indent=2), encoding="utf-8")

# 覆盖率
resolved = sum(1 for day_recs in trading.values() for r in day_recs
               if "买入" in r.get("action", "") and name_map.get(r.get("fund_name", ""), "") in charts)
total = sum(1 for day_recs in trading.values() for r in day_recs
            if "买入" in r.get("action", ""))
print(f"Coverage: {resolved}/{total} ({resolved/total*100:.1f}%)")

# 保存缺失净值列表供参考
missing_charts = set(name_map.values()) - set(charts.keys())
print(f"Missing charts (mapped but no data): {len(missing_charts)}")
