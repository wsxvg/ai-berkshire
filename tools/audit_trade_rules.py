#!/usr/bin/env python3
"""审计 273 个 trade_rules_*.json 的 T+N 计算影响范围

输出:
  reports/audit/trade_rules_t_plus_n.csv (含 code, buy_str, confirm_str, old_t, new_t, diff)
  reports/audit/trade_rules_t_plus_n.md (汇总)

用法: py -3.10 tools/audit_trade_rules.py
"""
import sys, json
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))
CACHE = PROJECT / "data" / "fund_cache"
OUT_DIR = PROJECT / "reports" / "audit"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def old_calc(buy_date, confirm_date):
    """原 (c_day - b_day) % 30 算法"""
    if not (buy_date and confirm_date):
        return None
    try:
        c_day = int(confirm_date.split("-")[-1])
        b_day = int(buy_date.split(" ")[0].split("-")[-1])
        diff = (c_day - b_day) % 30
        if diff <= 1: return 1
        if diff <= 2: return 2
        return diff
    except Exception:
        return None


def new_calc(buy_date, confirm_date, asof_year=2026, asof_month=6):
    """新算法: 按月解析 + 真实日历日差 → 工作日"""
    if not (buy_date and confirm_date):
        return None
    try:
        from datetime import datetime as _dt
        b_parts = buy_date.split(" ")[0]
        c_parts = confirm_date.split(" ")[0] if " " in confirm_date else confirm_date
        b_m, b_d = int(b_parts.split("-")[0]), int(b_parts.split("-")[1])
        c_m, c_d = int(c_parts.split("-")[0]), int(c_parts.split("-")[1])
        b_y = asof_year + 1 if b_m < asof_month - 6 else asof_year
        c_y = b_y + 1 if c_m < b_m - 6 else b_y
        b_dt = _dt(b_y, b_m, b_d)
        c_dt = _dt(c_y, c_m, c_d)
        # 工作日近似: 日历日差 * 5/7
        diff = (c_dt - b_dt).days
        if diff <= 0:
            return 1
        return max(1, round(diff * 5 / 7))
    except Exception:
        return None


def main():
    csv_path = OUT_DIR / "trade_rules_t_plus_n.csv"
    md_path = OUT_DIR / "trade_rules_t_plus_n.md"
    rows = []
    diff_count = 0
    extreme_old = []  # 旧算法算出 > 5 的（明显错误）
    for f in sorted(CACHE.glob("trade_rules_*.json")):
        data = json.loads(f.read_text("utf-8"))
        code = data.get("fund_code", f.stem.replace("trade_rules_", ""))
        buy = data.get("buy_date", "")
        cfm = data.get("confirm_date", "")
        old = old_calc(buy, cfm)
        new = new_calc(buy, cfm, 2026, 6)
        diff = (old != new)
        if diff:
            diff_count += 1
        if old is not None and old > 5:
            extreme_old.append((code, buy, cfm, old, new))
        rows.append({
            "code": code, "buy": buy, "confirm": cfm,
            "old_t": old, "new_t": new, "diff": "YES" if diff else "",
        })

    # 写 csv
    import csv as csvmod
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as fp:
        w = csvmod.DictWriter(fp, fieldnames=["code", "buy", "confirm", "old_t", "new_t", "diff"])
        w.writeheader()
        for r in rows:
            w.writerow(r)

    # 写 md
    lines = [
        "# trade_rules T+N 审计报告",
        "",
        f"**审计基金数**: {len(rows)}",
        f"**新旧算法不一致**: {diff_count} ({diff_count/len(rows)*100:.1f}%)",
        f"**旧算法算 > 5 天 (疑似 bug)**: {len(extreme_old)} 只",
        "",
        "## 旧算法算出 > 5 天的基金（高概率 bug 受害）",
        "",
        "| 代码 | buy_date | confirm_date | 旧 T+N | 新 T+N |",
        "|------|----------|--------------|--------|--------|",
    ]
    for code, buy, cfm, old, new in extreme_old[:30]:
        lines.append(f"| {code} | {buy} | {cfm} | {old} | {new} |")

    # 分类统计
    from collections import Counter
    old_dist = Counter(r["old_t"] for r in rows if r["old_t"] is not None)
    new_dist = Counter(r["new_t"] for r in rows if r["new_t"] is not None)
    lines += [
        "",
        "## 旧算法分布",
        "",
        "| T+N | 基金数 |",
        "|-----|--------|",
    ]
    for k in sorted(old_dist.keys(), key=lambda x: (x is None, x)):
        lines.append(f"| {k} | {old_dist[k]} |")
    lines += [
        "",
        "## 新算法分布",
        "",
        "| T+N | 基金数 |",
        "|-----|--------|",
    ]
    for k in sorted(new_dist.keys(), key=lambda x: (x is None, x)):
        lines.append(f"| {k} | {new_dist[k]} |")

    lines += [
        "",
        "## 结论",
        "",
    ]
    if not extreme_old:
        lines.append("- 旧算法未发现 > 5 天的离谱结果，对 6-01~7-11 段（夏季月份）影响很小")
    else:
        lines.append(f"- 旧算法对 {len(extreme_old)} 只基金算出了 > 5 天的错误 T+N（典型是跨月/跨年）")
        lines.append(f"- 这些基金若 6-01~7-11 期间被买入，新算法会显著缩短确认时间，更早入仓")
    lines.append("- 详细 CSV: `reports/audit/trade_rules_t_plus_n.csv`")

    md_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"CSV: {csv_path}")
    print(f"MD:  {md_path}")
    print(f"\n不一致: {diff_count}/{len(rows)} ({diff_count/len(rows)*100:.1f}%)")
    print(f"旧算法 > 5 天 (疑似 bug): {len(extreme_old)}")


if __name__ == "__main__":
    main()
