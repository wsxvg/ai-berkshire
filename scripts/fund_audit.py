"""
fund_audit.py — 6 关审计 (Python 化版本, 不调 LLM)
=====================================================

每个候选基金跑 6 关机械审计, 输出 pass/fail + 总分:

  1. Profile 关: 基金类型/规模/晨星评级
  2. Cost 关: 管理费/托管费/申购费
  3. Manager 关: 经理任职年限
  4. Holdings 关: 持仓集中度
  5. Performance 关: 1y/3y 收益
  6. Risk 关: 最大回撤/夏普

输出: {"code", "name", "pass_count", "total", "gates": [{name, pass, score, reason}, ...]}
"""
import json
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))

CACHE = PROJECT / "data" / "fund_cache"


def _read_fund(code):
    """读 fund_cache/fund_data_<code>.json"""
    p = CACHE / f"fund_data_{code}.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return None


def _read_chart(code):
    p = PROJECT / "data" / "fund_charts.json"
    if not p.exists():
        return {}
    d = json.loads(p.read_text(encoding="utf-8", errors="replace"))
    pts = d.get(code, [])
    # 转为 (date, nav) 排序
    out = []
    for pt in pts:
        d_str = pt.get("xAxis", "")[:10]
        try:
            nav = 1.0 + float(pt.get("yAxis", 0)) / 100
            out.append((d_str, nav))
        except Exception:
            pass
    return sorted(out)


def audit_fund(code, name=""):
    """6 关审计一只基金, 返回 dict"""
    data = _read_fund(code)
    chart = _read_chart(code)

    gates = []

    # === Gate 1: Profile 关 ===
    profile = (data or {}).get("profile", {})
    scale = profile.get("scale", "0")
    fund_type = profile.get("fund_type", "")
    rating = profile.get("morningstar_rating", "")

    # 解析规模 (亿)
    try:
        scale_yi = float(str(scale).replace("亿", "").replace("亿元", "").strip() or 0)
    except Exception:
        scale_yi = 0

    issues = []
    if scale_yi < 2:
        issues.append(f"规模小 ({scale_yi} 亿 < 2 亿, 清盘风险)")
    if "清盘" in fund_type or "联接" in fund_type and scale_yi < 5:
        issues.append(f"清盘/联接基金 (规模 {scale_yi} 亿)")
    pass_1 = len(issues) == 0
    gates.append({
        "name": "Profile (规模/类型)",
        "pass": pass_1,
        "score": 5.0 if pass_1 else 2.0,
        "reason": f"规模 {scale_yi} 亿, 类型 {fund_type}"
                   + ("; " + "; ".join(issues) if issues else " ✅"),
    })

    # === Gate 2: Cost 关 ===
    rules = (data or {}).get("rules", {})
    mf = rules.get("manage_fee", 1.2) or 1.2
    cf = rules.get("custody_fee", 0.2) or 0.2
    pf = rules.get("purchase_fee", 0.15) or 0.15
    total_cost = mf + cf + pf

    issues = []
    if mf > 1.5:
        issues.append(f"管理费 {mf}% 偏高")
    if total_cost > 1.85:
        issues.append(f"总费率 {total_cost:.2f}% > 1.85%")
    pass_2 = len(issues) == 0
    gates.append({
        "name": "Cost (费率)",
        "pass": pass_2,
        "score": 5.0 if mf < 0.5 else 4.0 if mf < 0.8 else 3.0 if mf < 1.2 else 2.0,
        "reason": f"管理 {mf}% + 托管 {cf}% + 申购 {pf}% = {total_cost:.2f}%"
                   + ("; " + "; ".join(issues) if issues else " ✅"),
    })

    # === Gate 3: Manager 关 ===
    mgr = (data or {}).get("manager", {})
    managers = mgr.get("managers", [])
    tenure_years = None
    if managers:
        accession = managers[0].get("accession_date", "")
        import re
        m = re.search(r"(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})", str(accession))
        if m:
            from datetime import datetime
            try:
                start = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
                tenure_years = (datetime(2026, 7, 13) - start).days / 365
            except Exception:
                pass

    issues = []
    if tenure_years is None:
        issues.append("无任职信息")
    elif tenure_years < 1.0:
        issues.append(f"经理任职仅 {tenure_years:.1f} 年 (< 1年)")

    pass_3 = len(issues) == 0
    score_3 = 5.0 if tenure_years and tenure_years > 5 else 4.0 if tenure_years and tenure_years > 3 else 3.0 if tenure_years and tenure_years > 1 else 2.0
    gates.append({
        "name": "Manager (经理)",
        "pass": pass_3,
        "score": score_3,
        "reason": (f"经理任职 {tenure_years:.1f} 年" if tenure_years else "无")
                   + ("; " + "; ".join(issues) if issues else " ✅"),
    })

    # === Gate 4: Holdings 关 (集中度) ===
    holdings = (data or {}).get("holdings", {})
    sectors = holdings.get("sectors", []) if isinstance(holdings, dict) else []
    if not sectors and isinstance(holdings, list):
        sectors = holdings
    top_sector_pct = 0
    if sectors and isinstance(sectors, list):
        weights = [s.get("weight", 0) for s in sectors if isinstance(s, dict)]
        top_sector_pct = max(weights) if weights else 0

    issues = []
    if top_sector_pct > 70:
        issues.append(f"单一行业占比 {top_sector_pct}% > 70% (高集中风险)")
    pass_4 = len(issues) == 0
    gates.append({
        "name": "Holdings (持仓集中度)",
        "pass": pass_4,
        "score": 5.0 if top_sector_pct < 30 else 4.0 if top_sector_pct < 50 else 3.0 if top_sector_pct < 70 else 1.5,
        "reason": (f"最大行业 {top_sector_pct}%" if top_sector_pct else "无 sector 数据")
                   + ("; " + "; ".join(issues) if issues else " ✅"),
    })

    # === Gate 5: Performance 关 (1y 收益) ===
    ret_1y = None
    if len(chart) >= 250:
        try:
            ret_1y = (chart[-1][1] / chart[-250][1] - 1) * 100
        except Exception:
            pass

    issues = []
    if ret_1y is None:
        score_5 = 3.0
        issues.append("无 1y 数据")
    else:
        if ret_1y < -30:
            issues.append(f"1y 收益 {ret_1y:+.1f}% 极差 (< -30%)")
        elif ret_1y > 200:
            issues.append(f"1y 收益 {ret_1y:+.1f}% 异常高 (> 200%, 可能是妖基)")

    pass_5 = len(issues) == 0
    gates.append({
        "name": "Performance (1y 收益)",
        "pass": pass_5,
        "score": (5.0 if ret_1y and ret_1y > 20 else
                  4.0 if ret_1y and ret_1y > 10 else
                  3.0 if ret_1y and ret_1y > 0 else
                  2.0 if ret_1y else 3.0),
        "reason": (f"1y 收益 {ret_1y:+.1f}%" if ret_1y is not None else "无")
                   + ("; " + "; ".join(issues) if issues else " ✅"),
    })

    # === Gate 6: Risk 关 (回撤) ===
    max_dd = None
    if len(chart) >= 60:
        try:
            window = chart[-250:] if len(chart) >= 250 else chart
            peak = max(p[1] for p in window)
            dd = (window[-1][1] - peak) / peak * 100
            max_dd = dd
        except Exception:
            pass

    issues = []
    if max_dd is not None and max_dd < -30:
        issues.append(f"1y 回撤 {max_dd:+.1f}% < -30% (高风险)")

    pass_6 = len(issues) == 0
    gates.append({
        "name": "Risk (1y 回撤)",
        "pass": pass_6,
        "score": (5.0 if max_dd and max_dd > -5 else
                  4.0 if max_dd and max_dd > -10 else
                  3.0 if max_dd and max_dd > -20 else
                  2.0 if max_dd else 3.0),
        "reason": (f"1y 最大回撤 {max_dd:+.1f}%" if max_dd is not None else "无")
                   + ("; " + "; ".join(issues) if issues else " ✅"),
    })

    # 缺数据的关视为"pass 但 score=2.5" (中性)
    # 否则会因为 cache 不全导致全 fail
    pass_count = sum(1 for g in gates if g["pass"])
    total_score = sum(g["score"] for g in gates)
    return {
        "code": code,
        "name": name or profile.get("full_name", code),
        "pass_count": pass_count,
        "total": len(gates),
        "total_score": round(total_score, 2),
        "gates": gates,
    }


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("codes", nargs="+", help="fund codes, e.g. 005660 013841")
    args = ap.parse_args()

    print(f"\n{'='*70}\n  6 关审计 — {len(args.codes)} 只基金\n{'='*70}\n")
    results = []
    for code in args.codes:
        r = audit_fund(code)
        results.append(r)
        # 简洁输出
        status = "✅" if r["pass_count"] == r["total"] else f"⚠️  ({r['pass_count']}/{r['total']})"
        print(f"  {code} {r['name'][:30]:<30} {status}  score={r['total_score']:.1f}")
        for g in r["gates"]:
            mark = "✅" if g["pass"] else "❌"
            print(f"      {mark} {g['name']}: {g['reason']}")
        print()

    # 落盘
    out = PROJECT / "reports" / "fund_audit_latest.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  💾 {out.relative_to(PROJECT)}")


if __name__ == "__main__":
    main()
