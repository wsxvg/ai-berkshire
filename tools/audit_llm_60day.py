#!/usr/bin/env python3
"""审计 LLM 60 天决策结果 vs 机器 baseline

检查项:
1. 命中率实际多少
2. LLM 决策有没有用未来函数 (看 logic 字段有没有引用未来日期)
3. 6-02 那天的关键时序问题
4. LLM 输出结构是否完整
"""
import json
from pathlib import Path

PROJECT = Path(".").resolve()
llm_path = PROJECT / "reports/llm-decision-review" / "llm_60day_buys.json"
machine_path = PROJECT / "reports/sim" / "virtual_portfolio.json"
sim_dir = PROJECT / "reports" / "sim"

if not llm_path.exists():
    print("ERROR: llm_60day_buys.json not found")
    raise SystemExit(1)

llm = json.loads(llm_path.read_text(encoding="utf-8"))
machine_vp = json.loads(machine_path.read_text(encoding="utf-8"))

# 1. 命中率
print("=" * 60)
print("【1. 命中率审计】")
print("=" * 60)

# 机器每天实际 buy 是从 daily_live.py 日志推, 但 machine_vp 没记 history
# 我们从各日的 .json 日报里读 buy_recommendations
machine_buys = {}
for jf in sorted(sim_dir.glob("2026-*.json")):
    if jf.name in ("virtual_portfolio_1month.json", "virtual_portfolio_1month_baseline.json"):
        continue
    date = jf.stem
    try:
        d = json.loads(jf.read_text(encoding="utf-8"))
        buys = d.get("buy_recommendations", [])
        codes = sorted(set(b.get("code", "") for b in buys if b.get("code")))
        if codes:
            machine_buys[date] = codes
    except Exception:
        pass

print(f"机器有 buy 的日期数: {len(machine_buys)}")
for d, c in sorted(machine_buys.items()):
    print(f"  {d}: {c}")

# LLM 解析
llm_buys = {}
llm_issues = []
for date, info in llm.items():
    if not isinstance(info, dict):
        llm_issues.append(f"{date}: not dict, got {type(info).__name__}")
        continue
    buys = info.get("buy", [])
    if not isinstance(buys, list):
        llm_issues.append(f"{date}: 'buy' not list, got {type(buys).__name__}")
        buys = []
    if buys:
        llm_buys[date] = sorted(buys)

print(f"\nLLM 有 buy 的日期数: {len(llm_buys)}")
for d, c in sorted(llm_buys.items()):
    print(f"  {d}: {c}")

# 逐日对比
print("\n" + "=" * 60)
print("【2. 逐日对比】")
print("=" * 60)
all_dates = sorted(set(machine_buys.keys()) | set(llm_buys.keys()))
hit_count = 0
miss_count = 0
extra_count = 0
for d in all_dates:
    m = set(machine_buys.get(d, []))
    l = set(llm_buys.get(d, []))
    overlap = m & l
    only_machine = m - l
    only_llm = l - m
    if m and l:
        status = "HIT" if overlap == m and m == l else "PARTIAL" if overlap else "MISS"
    elif m and not l:
        status = "MACHINE_ONLY"
    elif l and not m:
        status = "LLM_ONLY"
    else:
        continue
    if status == "HIT":
        hit_count += 1
    elif status == "MISS":
        miss_count += 1
    elif status == "LLM_ONLY":
        extra_count += 1
    print(f"  {d} [{status}]")
    print(f"    machine: {sorted(m) or '-'}")
    print(f"    llm:     {sorted(l) or '-'}")
    if overlap:
        print(f"    overlap: {sorted(overlap)}")
    if only_machine:
        print(f"    only_machine: {sorted(only_machine)}")
    if only_llm:
        print(f"    only_llm: {sorted(only_llm)}")

total_machine_buys = sum(len(v) for v in machine_buys.values())
total_llm_buys = sum(len(v) for v in llm_buys.values())
total_overlap = sum(len(set(machine_buys.get(d, [])) & set(llm_buys.get(d, []))) for d in all_dates)
print(f"\n汇总:")
print(f"  机器 total buys: {total_machine_buys} 只 (跨 {len(machine_buys)} 个日期)")
print(f"  LLM total buys:  {total_llm_buys} 只 (跨 {len(llm_buys)} 个日期)")
print(f"  重合: {total_overlap} 只")
hit_rate = total_overlap / total_machine_buys * 100 if total_machine_buys else 0
print(f"  命中率: {hit_rate:.1f}%")

# 3. 反未来函数检查
print("\n" + "=" * 60)
print("【3. 反未来函数检查 (logic 字段引用未来日期)】")
print("=" * 60)
# 简单启发式: logic 字段里如果出现"6 月涨"等描述未来表现的词, 标红
suspicious = []
for date, info in llm.items():
    if not isinstance(info, dict):
        continue
    logic = info.get("logic", "")
    # 任何提到"7-11"/"今天"/"之后"等模糊未来词
    flags = []
    for kw in ["今天", "目前", "已涨", "已涨", "后市", "接下来", "未来", "近期表现"]:
        if kw in logic:
            flags.append(kw)
    if flags:
        suspicious.append((date, logic[:80], flags))
if suspicious:
    for d, l, f in suspicious[:10]:
        print(f"  ⚠️ {d}: {f} -- {l}")
else:
    print("  未发现明显未来函数引用 (但 LLM 可能用更隐晦的方式)")

# 4. 关键日期时序问题
print("\n" + "=" * 60)
print("【4. 关键时序问题: 6-01 vs 6-02】")
print("=" * 60)
print("""已知问题 (见 reports/llm-decision-review/REPORT.md):
- 6-01: 机器实际 pending 中 (T+1), LLM 看到 holdings=0
- 6-02: 机器 actual_buys=5 (024239/016664/013841/017731/501226)
- LLM 在 6-02 看到 holdings=1 (501226 6-02 settle)
- 这导致 LLM 6-02 算相关性时用了 1 只持仓, 机器用了 1 只
- 实际 6-02 机器买了 5 只, 但 LLM 6-02 算相关性可能过滤掉很多

如果 LLM 6-02 输出 buys 数 < 5, 那 100% 命中率就是数据造假
""")
if "2026-06-02" in llm_buys:
    print(f"  LLM 6-02 buys: {llm_buys['2026-06-02']}")
else:
    print(f"  LLM 6-02 buys: (空)")
if "2026-06-02" in machine_buys:
    print(f"  机器 6-02 buys: {machine_buys['2026-06-02']}")
else:
    print(f"  机器 6-02 buys: (空)")

# 5. 输出结构完整性
print("\n" + "=" * 60)
print("【5. 输出结构完整性】")
print("=" * 60)
print(f"  总日期数: {len(llm)}")
expected = {"2026-04-13", "2026-04-14", "2026-04-15", "2026-04-16", "2026-04-17",
            "2026-04-20", "2026-04-21", "2026-04-22", "2026-04-23", "2026-04-24",
            "2026-04-27", "2026-04-28", "2026-04-29", "2026-04-30",
            "2026-05-06", "2026-05-07", "2026-05-08",
            "2026-05-11", "2026-05-12", "2026-05-13", "2026-05-14", "2026-05-15",
            "2026-05-18", "2026-05-19", "2026-05-20", "2026-05-21", "2026-05-22",
            "2026-05-25", "2026-05-26", "2026-05-27", "2026-05-28", "2026-05-29",
            "2026-06-01", "2026-06-02", "2026-06-03", "2026-06-04", "2026-06-05",
            "2026-06-08", "2026-06-09", "2026-06-10", "2026-06-11", "2026-06-12",
            "2026-06-15", "2026-06-16", "2026-06-17", "2026-06-18", "2026-06-19",
            "2026-06-22", "2026-06-23", "2026-06-24", "2026-06-25", "2026-06-26",
            "2026-06-29", "2026-06-30", "2026-07-01", "2026-07-11"}
missing = expected - set(llm.keys())
extra = set(llm.keys()) - expected
print(f"  缺失日期 ({len(missing)}): {sorted(missing) or '无'}")
print(f"  多余日期 ({len(extra)}): {sorted(extra) or '无'}")

# 6. 看 logic 字段
print("\n" + "=" * 60)
print("【6. logic 字段示例 (前 5 个有 buy 的日期)】")
print("=" * 60)
for d in sorted(llm_buys.keys())[:5]:
    info = llm.get(d, {})
    print(f"  {d}: buy={info.get('buy', [])}")
    print(f"    logic: {info.get('logic', '(无)')[:200]}")
