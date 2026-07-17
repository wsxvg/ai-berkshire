"""检查高频基金的覆盖率 + 直接用 fund_code 重建 map"""
import json, re
from collections import Counter
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent

hist = json.loads((PROJECT / "backtest/data/trading_history_fixed.json").read_text("utf-8"))
charts = json.loads((PROJECT / "backtest/data/fund_charts.json").read_text("utf-8"))
name_map = json.loads((PROJECT / "data/fund_name_map.json").read_text("utf-8"))

# 统计最常交易的基金名
buys = Counter()
for r in hist:
    if "买入" in r.get("action", ""):
        buys[r.get("fund_name", "")] += 1

total_buys = buys.total()
print(f"总买入记录: {total_buys}, 不同基金: {len(buys)}")

# 现有映射
name_to_code = dict(name_map)
# 加标准化匹配
_SUFFIX = re.compile(r'[ACHIRachir][类类]?$')
_BRACKET = re.compile(r'\([ACHIRachir]\)$')
for fn in buys:
    if fn in name_to_code: continue
    norm = _BRACKET.sub('', fn).strip()
    norm = _SUFFIX.sub('', norm).strip()
    # 在已有映射中找
    for exist_name, code in name_map.items():
        exist_norm = _BRACKET.sub('', exist_name).strip()
        exist_norm = _SUFFIX.sub('', exist_norm).strip()
        if norm == exist_norm and code in charts:
            name_to_code[fn] = code
            break

# 统计覆盖
covered = 0
covered_buys = 0
for name, cnt in buys.most_common():
    code = name_to_code.get(name, "")
    if code and code in charts:
        covered += 1
        covered_buys += cnt

print(f"\n已覆盖: {covered}/{len(buys)} 基金名, {covered_buys}/{total_buys} 买入记录 ({covered_buys/total_buys*100:.1f}%)")
print(f"name_map: {len(name_to_code)} 条")

# Top 30
print(f"\nTop 30 高频基金:")
for name, cnt in buys.most_common(30):
    code = name_to_code.get(name, "")
    status = "OK" if (code and code in charts) else "MISS"
    print(f"  {cnt:>5}x {name[:40]:40s} {status}")

# 保存扩展后的 map
if len(name_to_code) > len(name_map):
    (PROJECT / "data/fund_name_map.json").write_text(
        json.dumps(name_to_code, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nmap 更新: {len(name_map)} → {len(name_to_code)}")
