#!/usr/bin/env python3
"""审计 LLM 60天 v2 结果 (只否决, 不买)"""
import json
from pathlib import Path

PROJECT = Path(".").resolve()
llm_path = PROJECT / "reports/llm-decision-review" / "llm_60day_vetos_v2.json"
sim_dir = PROJECT / "reports" / "sim"

llm = json.loads(llm_path.read_text(encoding="utf-8"))

# 机器每日 buy_recommendations
machine_buys = {}
for jf in sorted(sim_dir.glob("2026-*.json")):
    if jf.name in ("virtual_portfolio_1month.json", "virtual_portfolio_1month_baseline.json"):
        continue
    date = jf.stem
    try:
        d = json.loads(jf.read_text(encoding="utf-8"))
        recs = d.get("buy_recommendations", [])
        codes = sorted(set(r.get("code", "") for r in recs if r.get("code")))
        if codes:
            machine_buys[date] = codes
    except Exception:
        pass

print("=" * 60)
print("【1. 机器有 buy 的日期 + LLM 是否否决】")
print("=" * 60)
total_machine_buys = 0
total_vetoed = 0
all_vetoes = []
for d in sorted(machine_buys.keys()):
    m = set(machine_buys.get(d, []))
    info = llm.get(d, {})
    if not isinstance(info, dict):
        print(f"  {d} [BAD FORMAT]: {info}")
        continue
    vetoes = info.get("veto", [])
    if not isinstance(vetoes, list):
        vetoes = []
    vetoed = m & set(vetoes)
    only_machine = m - set(vetoes)
    total_machine_buys += len(m)
    total_vetoed += len(vetoed)
    all_vetoes.extend([(d, v) for v in vetoed])
    if vetoed or only_machine:
        print(f"  {d}:")
        print(f"    机器 buy: {sorted(m)}")
        print(f"    LLM veto: {vetoes}")
        if vetoed:
            print(f"    [VETO] 真否决: {sorted(vetoed)}")
        if only_machine:
            print(f"    [MISS] 漏否决: {sorted(only_machine)}")

print(f"\n汇总:")
print(f"  机器总 buy: {total_machine_buys} 只")
print(f"  LLM 真否决: {total_vetoed} 只")
if total_machine_buys:
    print(f"  否决命中率: {total_vetoed/total_machine_buys*100:.1f}%")
print(f"  LLM 总 veto 数: {sum(len(llm.get(d, {}).get('veto', [])) for d in llm)}")

# 检查 6-22 LLM 是否否决 501226
print("\n" + "=" * 60)
print("【2. 6-22 那天 LLM 对 501226 的判断】")
print("=" * 60)
info_622 = llm.get("2026-06-22", {})
print(f"  veto: {info_622.get('veto', [])}")
print(f"  reason: {info_622.get('reason', '(无)')[:300]}")
print(f"  机器 6-22 实际 buy: {machine_buys.get('2026-06-22', [])}")

# 反未来函数检查
print("\n" + "=" * 60)
print("【3. 反未来函数检查 (reason 字段)】")
print("=" * 60)
suspicious = []
for d, info in llm.items():
    if not isinstance(info, dict):
        continue
    reason = str(info.get("reason", ""))
    # 找"6-22 后"的引用 (LLM 跑的时候是 7-11, 容易引用未来)
    for future_date in ["2026-07", "07-01", "07-11", "已涨", "后市"]:
        if future_date in reason and d < "2026-07":
            suspicious.append((d, future_date, reason[:100]))
            break
if suspicious:
    for d, kw, r in suspicious[:10]:
        print(f"  [FUTURE] {d}: 含 '{kw}' -- {r}")
else:
    print("  未发现明显未来函数引用")

# 6-22 那天 LLM "否决 501226" 是否真正确
# 看 501226 在 6-23 ~ 7-01 的 chart 表现
print("\n" + "=" * 60)
print("【4. 501226 真实表现 (6-22 买入后)】")
print("=" * 60)
charts = json.loads((PROJECT / "data" / "fund_charts.json").read_text(encoding="utf-8"))
pts = charts.get("501226", [])
# 找 6-22 ~ 7-11 的点
target_dates = ["2026-06-22", "2026-06-23", "2026-06-24", "2026-06-25", "2026-06-26",
                "2026-06-29", "2026-06-30", "2026-07-01", "2026-07-11"]
p622 = None
for p in pts:
    if p.get("xAxis", "")[:10] == "2026-06-22":
        p622 = p
        break
if p622:
    buy_y = float(p622.get("yAxis", 0))
    print(f"  6-22 累计收益: {buy_y:+.2f}%")
    for td in target_dates:
        for p in pts:
            if p.get("xAxis", "")[:10] == td:
                cur_y = float(p.get("yAxis", 0))
                # 6-22 之后净值变化: 累计收益从 buy_y 涨到 cur_y, 真实盈亏 = (1+cur_y/100)/(1+buy_y/100) - 1
                if (1 + buy_y/100) > 0:
                    ret = ((1 + cur_y/100) / (1 + buy_y/100) - 1) * 100
                else:
                    ret = 0
                days_diff = (int(td[8:10]) - 22) if td[:7] == "2026-06" else (int(td[8:10]) + 7)  # 7月近似
                print(f"  {td} (T+{days_diff}): 累计 {cur_y:+.2f}% → 实际盈亏 {ret:+.2f}%")
                break
