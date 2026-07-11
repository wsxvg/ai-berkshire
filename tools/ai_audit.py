#!/usr/bin/env python3
"""AI 审计自动生成器 (不依赖 IDE / LLM)

读 reports/sim/YYYY-MM-DD.json 机器报告, 跑可机器化的审计维度,
在对应 .md 日报末尾追加 "## AI 审计 (auto)" 区块.

可机器化的维度:
  1. fund-checklist 简化版: 6 关中 4 关机器可判
     - 关1 能力圈: 基金规模 / 存续时间
     - 关2 经理: 经理任职年限 (从 fund_manager cache)
     - 关3 成本: 费率 (从 trade_rules cache)
     - 关4 聪明钱: 大佬近期买卖笔数 (从 trading_history)
  2. fund-sell 简化版: 持仓 P&L > 80% → 止盈; < -15% → 止损
  3. 拦截复查: 拦截原因是否合理 (RSI/规模/费率)

不是替代 LLM, 是给 LLM 一个"已经做完的事实摘要", 节省 token.

用法:
  py -3.10 tools/ai_audit.py                  # 审计今天日报
  py -3.10 tools/ai_audit.py 2026-06-26       # 审计指定日报
  py -3.10 tools/ai_audit.py --all            # 审计所有 sim/*.md
  py -3.10 tools/ai_audit.py --dry-run        # 只看, 不改文件
"""

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
SIM_DIR = PROJECT / "reports" / "sim"
CACHE_DIR = PROJECT / "data" / "fund_cache"
TRADING_HISTORY = PROJECT / "backtest" / "data" / "trading_history_fixed.json"
FUND_NAME_MAP = PROJECT / "data" / "fund_name_map.json"


def load_json(path, default=None):
    if not Path(path).exists():
        return default if default is not None else {}
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return default if default is not None else {}


# ── 机器化审计维度 ──

def check_profile(code):
    """关1 能力圈 (读 fund_profile 缓存)"""
    p = load_json(CACHE_DIR / f"fund_profile_{code}.json", {})
    if not p:
        return {"ok": True, "issues": ["无档案缓存"], "size": None, "age_days": None}
    size_str = p.get("fund_size", "") or p.get("total_asset", "")
    size = None
    if isinstance(size_str, str):
        m = re.search(r"([\d.]+)\s*亿", size_str)
        if m:
            size = float(m.group(1))
    inception = p.get("inception_date", "") or p.get("establish_date", "")
    age_days = None
    if inception:
        try:
            d = datetime.strptime(inception[:10], "%Y-%m-%d")
            age_days = (datetime.now() - d).days
        except Exception:
            pass
    issues = []
    if size is not None and size < 0.5:
        issues.append(f"规模 {size} 亿 < 0.5 亿 (清盘预警)")
    if age_days is not None and age_days < 365:
        issues.append(f"成立 < 1 年 ({age_days} 天, 无足够业绩)")
    return {"ok": len(issues) == 0, "issues": issues, "size_yi": size, "age_days": age_days}


def check_manager(code):
    """关2 经理 (读 fund_manager 缓存)"""
    m = load_json(CACHE_DIR / f"fund_manager_{code}.json", {})
    if not m:
        return {"ok": True, "issues": ["无经理缓存"], "tenure_years": None}
    tenure_str = m.get("tenure", "") or m.get("tenure_years", "")
    tenure = None
    if isinstance(tenure_str, str):
        match = re.search(r"([\d.]+)\s*年", tenure_str)
        if match:
            tenure = float(match.group(1))
    issues = []
    if tenure is not None and tenure < 2:
        issues.append(f"经理任职 {tenure} 年 < 2 年 (稳定性差)")
    return {"ok": len(issues) == 0, "issues": issues, "tenure_years": tenure}


def check_cost(code):
    """关3 成本 (读 trade_rules 缓存)"""
    t = load_json(CACHE_DIR / f"trade_rules_{code}.json", {})
    if not t:
        return {"ok": True, "issues": ["无费率缓存"], "buy_fee": None}
    fee_str = (t.get("buy_fee") or t.get("subscription_fee") or "")
    fee = None
    if isinstance(fee_str, str):
        match = re.search(r"([\d.]+)", fee_str)
        if match:
            fee = float(match.group(1))
    issues = []
    if fee is not None and fee > 1.5:
        issues.append(f"申购费 {fee}% > 1.5% (高成本)")
    return {"ok": len(issues) == 0, "issues": issues, "buy_fee_pct": fee}


def check_smart_money(code, days=30, asof=None):
    """关4 聪明钱 (asof 前 N 天大佬买卖笔数)
    asof: 基准日期 (默认 datetime.now()) - 历史日报审计时传报告日期
    """
    hist = load_json(TRADING_HISTORY, [])
    buys = sells = 0
    users_b = set()
    users_s = set()
    if asof is None:
        asof = datetime.now()
    cutoff = asof.timestamp() - days * 86400
    for rec in hist:
        rec_code = rec.get("fund_code", "")
        if rec_code != code:
            continue
        # 兼容多种日期字段 (date / _full_date)
        date_str = rec.get("date", "") or rec.get("_full_date", "")
        date_str = date_str[:10]
        try:
            d = datetime.strptime(date_str, "%Y-%m-%d")
        except Exception:
            continue
        if d.timestamp() < cutoff:
            continue
        action = rec.get("action", "")
        uid = rec.get("_uid", "")
        if "买入" in action or action == "BUY":
            buys += 1
            users_b.add(uid)
        elif "卖出" in action or action == "SELL":
            sells += 1
            users_s.add(uid)
    consensus = buys - sells
    issues = []
    if consensus < -3:
        issues.append(f"近 {days} 天大佬净卖出 {-consensus} 笔 (共识转空)")
    elif consensus >= 5:
        pass  # 强共识不警告
    return {
        "ok": consensus >= 0,
        "issues": issues,
        "buys": buys,
        "sells": sells,
        "net": consensus,
        "user_count": len(users_b | users_s),
    }


def audit_fund(code, name, asof=None):
    """单只基金四关审计 (机器化部分)"""
    profile = check_profile(code)
    manager = check_manager(code)
    cost = check_cost(code)
    smart = check_smart_money(code, asof=asof)
    score = 3.0
    if not profile["ok"]:
        score -= 0.5
    else:
        score += 0.2
    if not manager["ok"]:
        score -= 0.5
    else:
        score += 0.2
    if not cost["ok"]:
        score -= 0.5
    else:
        score += 0.2
    if not smart["ok"]:
        score -= 0.5
    else:
        score += 0.5
    all_issues = profile["issues"] + manager["issues"] + cost["issues"] + smart["issues"]
    return {
        "code": code,
        "name": name,
        "score": round(score, 2),
        "passed": sum([profile["ok"], manager["ok"], cost["ok"], smart["ok"]]),
        "total": 4,
        "issues": all_issues,
        "details": {
            "profile": {"size_yi": profile.get("size_yi"), "age_days": profile.get("age_days")},
            "manager": {"tenure_years": manager.get("tenure_years")},
            "cost": {"buy_fee_pct": cost.get("buy_fee_pct")},
            "smart_money": {"net": smart.get("net"), "user_count": smart.get("user_count")},
        },
    }


def audit_holding(code, name, pnl_pct, buy_date, asof=None):
    """持仓卖出信号审计"""
    if asof is None:
        asof = datetime.now()
    issues = []
    advice = "持有"
    if pnl_pct >= 80:
        issues.append(f"盈利 +{pnl_pct:.1f}% 触发止盈线 80%")
        advice = "止盈 50%"
    elif pnl_pct <= -15:
        issues.append(f"亏损 {pnl_pct:.1f}% 触发止损线 -15%")
        advice = "止损清仓"
    elif pnl_pct >= 30:
        issues.append(f"盈利 +{pnl_pct:.1f}% 接近止盈, 建议分批止盈")
        advice = "止盈 1/3"
    try:
        d = datetime.strptime(buy_date, "%Y-%m-%d")
        hold_days = (asof - d).days
        if hold_days < 7:
            issues.append(f"持有仅 {hold_days} 天, 费率未回本")
            advice = advice + " (T+7 内不操作)"
    except Exception:
        pass
    smart = check_smart_money(code, days=30, asof=asof)
    if smart.get("net", 0) < -3:
        issues.append(f"近 30 天大佬净卖出 {-smart['net']} 笔")
        advice = "考虑减仓"
    return {
        "code": code,
        "name": name,
        "pnl_pct": round(pnl_pct, 2),
        "buy_date": buy_date,
        "advice": advice,
        "issues": issues,
        "smart_money": smart,
    }


# ── Markdown 渲染 ──

def render_audit_block(date, json_data, audits):
    lines = [
        "",
        f"## AI 审计 (auto) — {date} {datetime.now().strftime('%H:%M')}",
        "",
        "> 由 `tools/ai_audit.py` 自动生成 (机器化 4 关: 能力圈/经理/成本/聪明钱)",
        "> 非完整 SKILL 审计, 但可作为 LLM 二次审计的事实基础。",
        "",
    ]
    buys = json_data.get("buy_recommendations", [])
    if buys:
        lines.append(f"### 买入建议审计 ({len(buys)} 只)")
        lines.append("")
        for b in buys:
            a = audits["buys"].get(b["code"], {})
            score = a.get("score", "?")
            passed = f"{a.get('passed', 0)}/{a.get('total', 4)}"
            issues = a.get("issues", [])
            lines.append(f"**{b['name']} ({b['code']})** — 机器评分 `{score}/5` ({passed} 关过)")
            sm = a.get("details", {}).get("smart_money", {})
            sm_str = f"大佬近30天净买卖 {sm.get('net', 0)} ({sm.get('user_count', 0)} 人)"
            lines.append(f"- 聪明钱: {sm_str}")
            if issues:
                for iss in issues:
                    lines.append(f"- ⚠️ {iss}")
            else:
                lines.append("- ✅ 4 关全过, 可考虑买入")
            lines.append("")
    blocked = json_data.get("blocked_funds", [])
    if blocked:
        lines.append(f"### 风控拦截复查 ({len(blocked)} 只)")
        lines.append("")
        for b in blocked:
            reason = b.get("reason", "未知")
            lines.append(f"**{b['name']} ({b['code']})** — 拦截原因: {reason}")
            if "RSI" in reason or "超买" in reason:
                lines.append("- ✅ 拦截合理 (RSI 是量化指标, 无歧义)")
            elif "规模" in reason:
                lines.append("- ✅ 拦截合理 (规模是清盘预警, 慎重)")
            else:
                lines.append(f"- 🤔 拦截原因需人工复查: {reason}")
            lines.append("")
    holdings = json_data.get("holdings", {})
    if holdings:
        lines.append(f"### 持仓卖出信号 ({len(holdings)} 只在仓)")
        lines.append("")
        lines.append("| 基金 | 盈亏 | 建议 | 信号 |")
        lines.append("|------|------|------|------|")
        for code, h in holdings.items():
            a = audits["holdings"].get(code, {})
            pnl = a.get("pnl_pct", 0)
            advice = a.get("advice", "?")
            sig = []
            if a.get("issues"):
                sig.append(f"{len(a['issues'])} 警")
            sm = a.get("smart_money", {})
            if sm.get("net", 0) < -3:
                sig.append("大佬卖")
            sig_str = " ".join(sig) if sig else "—"
            lines.append(f"| {h.get('name','?')} ({code}) | {pnl:+.1f}% | {advice} | {sig_str} |")
        lines.append("")
    total_pnl = json_data.get("portfolio", {}).get("total_value", 0) - 100000
    pnl_pct = total_pnl / 100000 * 100
    lines.append("### 整体建议")
    lines.append("")
    if pnl_pct > 5:
        lines.append(f"- ✅ 组合盈利 +{pnl_pct:.1f}%, 注意分批止盈 (尤其 +30% 以上持仓)")
    elif pnl_pct < -10:
        lines.append(f"- ⚠️ 组合亏损 {pnl_pct:.1f}%, 检查是否触发止损 (每只 < -15%)")
    else:
        lines.append(f"- 📊 组合 {pnl_pct:+.1f}%, 正常持有")
    cash = json_data.get("portfolio", {}).get("cash", 0)
    if cash > 50000:
        lines.append(f"- 💰 现金 ¥{cash:,.0f} 较多, 考虑加仓高分基金")
    elif cash < 10000:
        lines.append(f"- 💰 现金仅 ¥{cash:,.0f}, 等待卖出回笼")
    lines.append("")
    lines.append("---")
    lines.append(f"*生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | 工具: tools/ai_audit.py*")
    return "\n".join(lines)


def audit_report(date, dry_run=False):
    json_path = SIM_DIR / f"{date}.json"
    md_path = SIM_DIR / f"{date}.md"
    if not json_path.exists():
        return {"date": date, "error": f"找不到 {json_path}"}
    data = load_json(json_path)
    # 基准日期 = 日报日期 (用 asof 限定历史窗口)
    try:
        asof = datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        asof = datetime.now()
    audits = {"buys": {}, "holdings": {}}
    for b in data.get("buy_recommendations", []):
        audits["buys"][b["code"]] = audit_fund(b["code"], b.get("name", b["code"]), asof=asof)
    for code, h in data.get("holdings", {}).items():
        audits["holdings"][code] = audit_holding(
            code, h.get("name", code),
            h.get("pnl_pct", 0), h.get("buy_date", date),
            asof=asof,
        )
    block = render_audit_block(date, data, audits)
    if dry_run:
        return {"date": date, "block": block, "audits": audits}
    if not md_path.exists():
        return {"date": date, "error": f"找不到 {md_path}"}
    md = md_path.read_text(encoding="utf-8")
    md = re.sub(
        r"\n## AI 审计 \(auto\).*?(?=\n## |\Z)",
        "",
        md,
        flags=re.DOTALL,
    )
    if "\n---\n" in md:
        parts = md.rsplit("\n---\n", 1)
        if parts[1].strip():
            new_md = parts[0] + block + "\n---\n" + parts[1]
        else:
            new_md = parts[0] + block
    else:
        new_md = md + block
    md_path.write_text(new_md, encoding="utf-8")
    return {"date": date, "ok": True, "block": block, "audits": audits}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("date", nargs="?", help="审计日期 YYYY-MM-DD (默认今天)")
    ap.add_argument("--all", action="store_true", help="审计所有 sim/*.md")
    ap.add_argument("--dry-run", action="store_true", help="只看, 不改文件")
    args = ap.parse_args()
    if args.all:
        dates = []
        for f in sorted(SIM_DIR.glob("2026-*.json")):
            dates.append(f.stem)
        print(f"审计 {len(dates)} 个日报: {dates}")
        for d in dates:
            r = audit_report(d, dry_run=args.dry_run)
            if r.get("error"):
                print(f"  {d}: ❌ {r['error']}")
            else:
                a = r.get("audits", {})
                n_buy = len(a.get("buys", {}))
                n_hold = len(a.get("holdings", {}))
                print(f"  {d}: ✅ {n_buy} 买入 + {n_hold} 持仓")
        return
    date = args.date or datetime.now().strftime("%Y-%m-%d")
    r = audit_report(date, dry_run=args.dry_run)
    if r.get("error"):
        print(f"❌ {r['error']}")
        sys.exit(1)
    print(f"✅ {date} 审计完成")
    if args.dry_run:
        print(r["block"])
    else:
        a = r.get("audits", {})
        print(f"  买入审计: {len(a.get('buys', {}))} 只")
        print(f"  持仓审计: {len(a.get('holdings', {}))} 只")


if __name__ == "__main__":
    main()
