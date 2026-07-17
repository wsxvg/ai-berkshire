"""从 fund_profile 文件直接匹配 fund_name → fund_code"""
import json, glob, os
from pathlib import Path

PROJECT = Path(".")
nm = json.loads((PROJECT / "data/fund_name_map.json").read_text("utf-8"))
trading = json.loads((PROJECT / "backtest/data/trading_by_date_fixed.json").read_text("utf-8"))

# 收集未映射基金名（按频率排序）
from collections import Counter
unmapped_freq = Counter()
for dr in trading.values():
    for r in dr:
        fn = r.get("fund_name", "")
        if fn not in nm and "买入" in r.get("action", ""):
            unmapped_freq[fn] += 1

print(f"未映射: {len(unmapped_freq)} 个基金名, 总买入: {unmapped_freq.total()}")

# 加载所有 profile 的 full_name → code
added = 0
for fpath in Path("data/fund_cache").glob("fund_profile_*.json"):
    code = fpath.stem.replace("fund_profile_", "")
    try:
        data = json.loads(fpath.read_text("utf-8"))
        fname = data.get("full_name", data.get("fundFullName", data.get("fundName", "")))
        if fname and fname in unmapped_freq and fname not in nm:
            nm[fname] = code
            added += 1
        # 也试 normalized (去括号)
        import re
        norm = re.sub(r'[（(][^)）]*[)）]$', '', fname).strip()
        if norm != fname and norm in unmapped_freq and norm not in nm:
            nm[norm] = code
            added += 1
    except: pass

# 全半角括号互换
bracket_added = 0
for fn in list(unmapped_freq.keys()):
    if fn in nm: continue
    # 全角→半角
    fn2 = fn.replace("\uff08", "(").replace("\uff09", ")")
    if fn2 in nm and nm[fn2] in {v for v in nm.values()}:
        nm[fn] = nm[fn2]
        bracket_added += 1

print(f"Profile match: +{added}, bracket: +{bracket_added}")
print(f"Total map: {len(nm)}")

(PROJECT / "data/fund_name_map.json").write_text(json.dumps(nm, ensure_ascii=False, indent=2), encoding="utf-8")

# 覆盖率
chars = json.loads((PROJECT / "backtest/data/fund_charts.json").read_text("utf-8"))
res = sum(1 for dr in trading.values() for r in dr if "买入" in r.get("action", "") and nm.get(r.get("fund_name", ""), "") in chars)
tot = sum(1 for dr in trading.values() for r in dr if "买入" in r.get("action", ""))
print(f"Coverage: {res}/{tot} ({res/tot*100:.1f}%)")
