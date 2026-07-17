"""补充 fund_charts.json 中缺失的基金净值数据（不重爬已有的）"""
import json, urllib.request, urllib.parse, time, sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))

# 加载现有数据
name_map = json.loads((PROJECT / "data/fund_name_map.json").read_text("utf-8"))
charts = json.loads((PROJECT / "backtest/data/fund_charts.json").read_text("utf-8"))
trading = json.loads((PROJECT / "backtest/data/trading_by_date_fixed.json").read_text("utf-8"))

# 收集所有基金名
all_names = set()
for day_records in trading.values():
    for r in day_records:
        fn = r.get("fund_name", "")
        if fn: all_names.add(fn)

print(f"总基金名: {len(all_names)}")
print(f"已有映射: {len(name_map)}")
print(f"已有净值: {len(charts)}")

# Step 1: 搜索 API 映射未匹配的基金名
unmapped = all_names - set(name_map.keys())
print(f"\n未映射: {len(unmapped)}")
if unmapped:
    print("搜索映射中...")
    added = 0
    fail = 0
    for i, fn in enumerate(sorted(unmapped)):
        try:
            keyword = urllib.parse.quote(fn[:30])
            url = f"https://ms.jr.jd.com/gw/generic/jj/h5/m/searchFund?keyword={keyword}&pageIndex=1&pageSize=5"
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0",
                "Referer": "https://jdjr.jd.com/"
            })
            resp = urllib.request.urlopen(req, timeout=8)
            data = json.loads(resp.read())
            results = data.get("resultData", {}).get("data", {}).get("fundList", [])
            if results:
                name_map[fn] = results[0].get("fundCode", "")
                added += 1
            else:
                fail += 1
            if (i + 1) % 50 == 0:
                print(f"  {i+1}/{len(unmapped)} mapped:{added} failed:{fail}")
            time.sleep(0.3)  # 限速
        except Exception as e:
            fail += 1
    print(f"  完成: mapped={added}, failed={fail}")
    # 保存 name_map
    (PROJECT / "data/fund_name_map.json").write_text(
        json.dumps(name_map, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  name_map 已更新: {len(name_map)} 条")

# Step 2: 找缺少净值的 code
all_codes = {name_map.get(fn, "") for fn in all_names if name_map.get(fn)}
missing = all_codes - set(charts.keys())
missing.discard("")
print(f"\n缺少净值: {len(missing)} 个代码")

if not missing:
    print("全部齐全!")
    exit(0)

# Step 3: 下载净值
print("下载净值...")
from tools.jd_finance_api import get_fund_chart_data
success = 0
fail = 0
for i, code in enumerate(sorted(missing)):
    try:
        chart = get_fund_chart_data(code, full_history=True, page_size=2000)
        if chart and chart.get("chartPoints"):
            charts[code] = chart["chartPoints"]
            success += 1
        else:
            fail += 1
    except Exception as e:
        fail += 1
    if (i + 1) % 20 == 0:
        print(f"  {i+1}/{len(missing)} ok:{success} fail:{fail}")
    time.sleep(0.5)

# 保存
(PROJECT / "backtest/data/fund_charts.json").write_text(
    json.dumps(charts, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"\n完成: ok={success}, fail={fail}, total charts={len(charts)}")
