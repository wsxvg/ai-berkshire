#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generate fund-monitor style report + fund-checklist deep analysis from pipeline cache.

Reads:
  data/trading_records_cache.json
  data/holdings_snapshot.json
  data/holdings_diff_cache.json

Outputs:
  reports/auto/daily-{YYYY-MM-DD}.md  (fund-monitor format)
  reports/fund-checklist/{code}/checklist-{YYYYMMDD}.md  (per fund)

Usage:
  python scripts/generate_report.py
"""
import json
import os
import sys
import time
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

# Import API functions directly for structured dict data
from tools.jd_finance_api import (
    FOLLOWED_USERS,
    batch_get_fund_data,
    get_fund_holdings_distribution,
    get_fund_manager,
    get_fund_performance,
    get_fund_profile,
    get_fund_trade_rules,
    get_fund_chart_data,
)

DATA_DIR = _PROJECT_ROOT / "data"
REPORTS_DIR = _PROJECT_ROOT / "reports"
CHECKLIST_DIR = REPORTS_DIR / "fund-checklist"


# ── helpers ─────────────────────────────────────────────────────────────


def _today_str():
    return date.today().isoformat()


def _now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _ensure_dirs():
    for d in (CHECKLIST_DIR,):
        d.mkdir(parents=True, exist_ok=True)


def _load_json(path, default=None):
    p = Path(path)
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            print(f"  [WARN] Failed to load {p.name}: {e}")
    return default if default is not None else {}


def _parse_amount(amt_str):
    if not amt_str:
        return 0.0
    s = str(amt_str).replace(",", "").replace("¥", "").replace("￥", "").replace("+", "").replace("元", "").strip()
    try:
        return float(s)
    except (ValueError, TypeError):
        return 0.0


def _extract_code(detail):
    """Extract fund numeric code from '基金XXXXXX'."""
    if detail and detail.startswith("基金"):
        return detail[2:]
    return ""


def _get_fund_code(fdata):
    # Prefer fund_code injected by auto-pipeline (from holdings cross-ref)
    fc = fdata.get("fund_code", "")
    if fc:
        return fc
    # Fallback: _fund_ids 7-digit → 6-digit
    for fid in fdata.get("_fund_ids", []):
        if len(fid) == 7 and fid.startswith("1"):
            return fid[1:]
    # Last resort: regex from detail
    for r in fdata.get("records", []):
        c = _extract_code(r.get("detail", ""))
        if c:
            return c
    return ""


# ── Load Data ─────────────────────────────────────────────────────────────


def _load_data():
    trading = _load_json(DATA_DIR / "trading_records_cache.json", {})
    snapshot = _load_json(DATA_DIR / f"holdings_snapshot_{_today_str()}.json", {})
    diff = _load_json(DATA_DIR / "holdings_diff_cache.json", {})
    print(f"  Loaded: {len(trading.get('funds', {}))} funds from trading_records")
    return trading, snapshot, diff


# ─── Classify ─────────────────────────────────────────────────────────────


def _classify_funds(trading):
    funds = trading.get("funds", {})
    strong_buy = []
    buy_signal = []
    others = []

    for fname, fdata in funds.items():
        bc = fdata.get("buy_count", 0)
        sc = fdata.get("sell_count", 0)

        total_buy = sum(
            _parse_amount(r.get("amount", "0"))
            for r in fdata.get("records", [])
            if "买入" in r.get("action", "")
        )

        item = {
            "name": fname,
            "code": _get_fund_code(fdata),
            "buy_count": bc,
            "sell_count": sc,
            "buy_users": fdata.get("buy_users", []),
            "sell_users": fdata.get("sell_users", []),
            "records": fdata.get("records", []),
            "total_buy_amount": total_buy,
        }

        if bc >= 3 and bc > sc:
            item["signal"] = "strong_buy"
            strong_buy.append(item)
        elif bc >= 2 and bc > sc:
            item["signal"] = "buy"
            buy_signal.append(item)
        else:
            item["signal"] = "neutral"
            others.append(item)

    strong_buy.sort(key=lambda x: (x["buy_count"], x["total_buy_amount"]), reverse=True)
    buy_signal.sort(key=lambda x: (x["buy_count"], x["total_buy_amount"]), reverse=True)
    return strong_buy, buy_signal, others


# ── Report Generation ─────────────────────────────────────────────────────


def _gen_per_user_breakdown(strong_buy, buy_signal):
    user_ops = defaultdict(lambda: {"buy": [], "sell": []})
    for item in strong_buy + buy_signal:
        for r in item["records"]:
            u = r.get("user", "")
            act = r.get("action", "")
            amt = r.get("amount", "")
            if "买入" in act:
                user_ops[u]["buy"].append(f"{item['name']} {amt}")
            elif "卖出" in act:
                user_ops[u]["sell"].append(f"{item['name']} {amt}")
    return user_ops


def _generate_report(strong_buy, buy_signal, others):
    today = _today_str()
    lines = []

    # ── Header ──
    lines.append(f"# 🏦 每日基金监控报告 — {today}")
    lines.append("")
    lines.append(f"> **报告时间**：{_now_str()}")
    lines.append(f"> **监控大佬**：{len(FOLLOWED_USERS)} 人")
    total_records = sum(len(s["records"]) for s in strong_buy + buy_signal + others)
    lines.append(f"> **今日记录**：{total_records} 条")
    lines.append(f"> **数据来源**：京东金融 API 实时抓取")
    lines.append("")

    # ── Section 1: 买入共识 ──
    lines.append("## 🟢 一、今日买入共识")
    lines.append("")
    lines.append("> 交易流水反映大佬**当下**的判断，权重大于持仓快照。")
    lines.append("")

    if strong_buy:
        lines.append("### 强共识信号（≥3人买入）")
        lines.append("")
        cols = "| # | 基金 | 代码 | 买入人数 | 总金额 | 参与大佬 | 深度分析 |"
        lines.append(cols)
        lines.append("|---|------|------|:-------:|:------:|---------|:--------:|")
        for i, item in enumerate(strong_buy, 1):
            users_str = ", ".join(item["buy_users"])
            total_str = f"¥{item['total_buy_amount']:,.0f}" if item["total_buy_amount"] > 0 else "—"
            lines.append(
                f"| {i} | {item['name']} | {item['code'] or '?'} | {item['buy_count']} | {total_str} | {users_str} | [查看↓](#checklist-{i}) |"
            )
        lines.append("")
        lines.append("*强共识 = ≥3人同期买入，大概率是好基金，建议深入分析。*")
        lines.append("")

    if buy_signal:
        lines.append("### 买入确认信号（2人买入）")
        lines.append("")
        lines.append("| 基金 | 代码 | 买入人数 | 总金额 | 参与大佬 |")
        lines.append("|------|------|:-------:|:----:|---------|")
        for item in buy_signal:
            users_str = ", ".join(item["buy_users"])
            total_str = f"¥{item['total_buy_amount']:,.0f}" if item["total_buy_amount"] > 0 else "—"
            lines.append(
                f"| {item['name']} | {item['code'] or '?'} | {item['buy_count']} | {total_str} | {users_str} |"
            )
        lines.append("")

    # ── Section 2: 操作详情 ──
    lines.append("## 👤 二、今日操作详情")
    lines.append("")

    user_ops = _gen_per_user_breakdown(strong_buy, buy_signal)
    all_user_names: set[str] = set()
    for item in strong_buy + buy_signal + others:
        for r in item.get("records", []):
            u = r.get("user", "")
            if u:
                all_user_names.add(u)

    active_users: set[str] = set()
    for uname in sorted(all_user_names):
        ops = user_ops.get(uname, {"buy": [], "sell": []})
        if ops["buy"] or ops["sell"]:
            active_users.add(uname)
            lines.append(f"### {uname}")
            if ops["buy"]:
                for b in ops["buy"]:
                    lines.append(f"  🟢 买入 {b}")
            if ops["sell"]:
                for s in ops["sell"]:
                    lines.append(f"  🔴 卖出 {s}")
            lines.append("")

    inactive = sorted(all_user_names - active_users)
    if inactive:
        lines.append("### 今日无交易")
        lines.append(f"{'、'.join(inactive)}")
        lines.append("")

    # ── Section 3: Deep analysis summary ──
    lines.append("## 🔬 三、强共识基金深度分析")
    lines.append("")

    if strong_buy:
        lines.append("以下对 **strong_buy（≥3人买入）** 基金自动执行买入前 Checklist 分析：")
        lines.append("")
        for i, item in enumerate(strong_buy):
            code = item["code"]
            amt_str = f"¥{item['total_buy_amount']:,.0f}" if item["total_buy_amount"] > 0 else "—"
            lines.append(f"<a id='checklist-{i+1}'></a>")
            lines.append(f"### {i+1}. {item['name']}（{code}）")
            lines.append("")
            lines.append(f"**共识强度**：{item['buy_count']} 位大佬买入 | **总金额**：{amt_str}")
            lines.append("")
            lines.append(
                f"> 📋 [完整 Checklist 分析报告](reports/fund-checklist/{code}/checklist-{_today_str().replace('-', '')}.md)"
            )
            lines.append("")
    else:
        lines.append("（今日无强共识基金）")
        lines.append("")

    # ── System Status ──
    lines.append("## ⚙️ 系统状态")
    lines.append("")
    lines.append("| 项目 | 状态 |")
    lines.append("|------|------|")
    lines.append("| 数据采集 | ✅ 已完成")
    lines.append(f"| 覆盖大佬 | {len(all_user_names)} 人有操作")
    lines.append(f"| 报告生成 | {_now_str()}")
    lines.append("")

    # ── Disclaimer ──
    lines.append("---")
    lines.append("")
    lines.append("> ⚠️ **免责声明**：本报告基于公开数据自动生成，不构成投资建议。")
    lines.append("> 大佬买 ≠ 你该买。大佬的仓位、期限、目标可能与你不同。")
    return "\n".join(lines)


# ── Fund Checklist (per fund deep analysis) ──────────────────────────────


def _run_fund_checklist(strong_buy):
    _ensure_dirs()
    today_compact = _today_str().replace("-", "")
    results = []

    import concurrent.futures as _cf
    t0 = time.time()

    def fetch_one(item):
        code = item["code"]
        name = item["name"]
        if not code:
            return (item, {}, {}, "no code")
        # Core 5: batch_get_fund_data does profile+perf+rules+holdings+manager concurrently
        fund_data = batch_get_fund_data([code], use_cache=False)
        row = fund_data.get(code, {})
        if "error" in row:
            profile = get_fund_profile(code, use_cache=False)
            perf = get_fund_performance(code, use_cache=False)
            manager_data = get_fund_manager(code)
            holdings = get_fund_holdings_distribution(code, use_cache=False)
            rules = get_fund_trade_rules(code, use_cache=False)
        else:
            profile = row.get("fund_profile")
            perf = row.get("fund_perf")
            holdings = row.get("holdings")
            rules = row.get("trade_rules")
            manager_data = row.get("manager")
        # Bonus: chart data (demo.md verified, no cookie)
        chart = get_fund_chart_data(code)
        core = {"profile": profile, "perf": perf, "holdings": holdings, "rules": rules, "manager": manager_data}
        extra = {"chart": chart}
        return (item, core, extra, None)

    item_list = list(strong_buy)
    with _cf.ThreadPoolExecutor(max_workers=min(len(item_list), 15)) as pool:
        futs = {pool.submit(fetch_one, item): item for item in item_list}
        for future in _cf.as_completed(futs):
            item, core, extra, err = future.result()
            code = item["code"]
            name = item["name"]
            if err:
                print(f"  [SKIP] {name} - {err}")
                continue
            print(f"  [OK] {name} ({code})")
            report = _gen_checklist_report(code, name, item, core, extra)
            report_file = CHECKLIST_DIR / code / f"checklist-{today_compact}.md"
            report_file.parent.mkdir(parents=True, exist_ok=True)
            report_file.write_text(report, encoding="utf-8")
            results.append({"code": code, "name": name, "file": str(report_file)})

    elapsed = time.time() - t0
    print(f"\n  → {len(results)}/{len(strong_buy)} checklist reports generated ({elapsed:.1f}s)")
    return results


def _gen_checklist_report(code, name, item, core, extras):
    """Generate checklist from core data + extras + scoring engine."""
    profile = core.get("profile")
    perf = core.get("perf")
    holdings = core.get("holdings")
    rules = core.get("rules")
    manager_data = core.get("manager")
    chart = extras.get("chart", {})
    today = _today_str()

    # Load scoring data from pipeline (if available)
    _score_info = None
    _status = _load_json(DATA_DIR / "auto" / "status.json", {})
    _fund_scores = _status.get("fund_scores", {})
    if code in _fund_scores:
        _score_info = _fund_scores[code]

    lines = []

    lines.append(f"# 📋 基金买入前 Checklist — {name}")
    lines.append("")
    lines.append(f"> **代码**：{code} ｜ **分析日期**：{today}")
    lines.append(f"> **触发条件**：今日 {item['buy_count']} 位大佬同时买入（strong_buy 强共识）")
    lines.append("")

    # 1. Profile
    lines.append("## 一、基金概况")
    lines.append("")
    if profile and profile.get("full_name"):
        lines.append("| 项目 | 内容 |")
        lines.append("|------|------|")
        lines.append(f"| 全称 | {profile.get('full_name', '—')} |")
        lines.append(f"| 成立日期 | {profile.get('established', '—')} |")
        lines.append(f"| 资产规模 | {profile.get('scale', '—')} |")
        lines.append(f"| 管理公司 | {profile.get('manager_company', '—')} |")
        lines.append(f"| 托管人 | {profile.get('custodian', '—')} |")
        lines.append("")
    else:
        lines.append("（数据暂不可用）")
        lines.append("")

    # 2. Consensus
    lines.append("## 二、共识信号验证")
    lines.append("")
    lines.append("| 维度 | 数值 |")
    lines.append("|------|------|")
    lines.append(f"| 买入人数 | {item['buy_count']} 人 |")
    lines.append(f"| 买入总金额 | ¥{item['total_buy_amount']:,.0f}" if item['total_buy_amount'] > 0 else "| 买入总金额 | — |")
    lines.append(f"| 参与大佬 | {', '.join(item['buy_users'])} |")
    lines.append(f"| 卖出人数 | {item['sell_count']} 人 |")
    lines.append("")
    if item["buy_count"] >= 5:
        lines.append("**信号强度**：⭐⭐⭐ 极强共识")
    elif item["buy_count"] >= 3:
        lines.append("**信号强度**：⭐⭐ 强共识")
    lines.append("")

    # 2b. Five-dimension scoring (from auto-pipeline)
    if _score_info:
        _st = _score_info.get("total", 0)
        _vd = _score_info.get("verdict", "")
        _vd_label = {"buy": "建议买入", "watch": "值得关注", "pass": "建议跳过"}.get(_vd, _vd)
        _vd_color = {"buy": "🟢", "watch": "🟡", "pass": "⚪"}.get(_vd, "⚪")
        lines.append("### 五维评分（自动评分引擎）")
        lines.append("")
        lines.append(f"| 维度 | 说明 |")
        lines.append(f"|------|------|")
        lines.append(f"| 总分 | **{_st:.1f}** / 5.0 {_vd_color} {_vd_label} |")
        lines.append(f"| 评分依据 | 质量×25% + 成本×20% + 经理×20% + 动量×15% + 聪明钱×20% |")
        lines.append(f"| 数据来源 | `tools/fund_scorer.py`，数值计算（非LLM） |")
        lines.append("")
        if _st >= 4.0:
            lines.append(f"> 🟢 **评分≥4.0**：基本面过硬，建议买入（与大佬共识一致→信心增强）")
        elif _st >= 3.3:
            lines.append(f"> 🟡 **评分3.3~4.0**：基本面合格但有短板，需结合风险偏好判断")
        else:
            lines.append(f"> ⚪ **评分<3.3**：基本面不达标，即使大佬买入也不建议跟进")
        lines.append("")

    # 3. Performance
    lines.append("## 三、历史业绩")
    lines.append("")
    if perf and perf.get("performance"):
        lines.append("| 时间段 | 收益率 | 同类排名 |")
        lines.append("|--------|:------:|:--------:|")
        perf_list = perf.get("performance", [])
        for p in perf_list[:8]:
            r = p.get("return")
            r_str = f"{r:.2f}%" if r is not None else "—"
            lines.append(f"| {p.get('period', '')} | {r_str} | {p.get('rank', '—')} |")
        lines.append("")
    else:
        lines.append("（数据暂不可用）")
        lines.append("")

    # 4. Manager
    lines.append("## 四、基金经理")
    lines.append("")
    if manager_data:
        for m in manager_data.get("managers", []):
            lines.append(f"- **{m.get('name', '—')}**")
            lines.append(f"  - 任职：{m.get('tenure', '—')}")
            radar = m.get("radar", {})
            if radar:
                items_str = " | ".join(f"{k}: {v:.1f}" for k, v in radar.items())
                lines.append(f"  - 能力雷达：{items_str}")
            score = m.get("total_score")
            if score:
                lines.append(f"  - 综合评分：{score}")
            lines.append("")
    else:
        lines.append("（数据暂不可用）")
        lines.append("")

    # 5. Holdings
    lines.append("## 五、持仓穿透")
    lines.append("")
    if holdings:
        if holdings.get("invest_date"):
            lines.append(f"> 数据截至：{holdings['invest_date']}")
            lines.append("")
        if holdings.get("allocation"):
            lines.append("### 资产配置")
            for k, v in holdings["allocation"].items():
                lines.append(f"- {k}: {v}%")
            lines.append("")
        top = holdings.get("top_stocks", [])
        if top:
            lines.append("### 前十大持仓")
            lines.append("")
            lines.append("| # | 股票 | 占比 | 变动 |")
            lines.append("|---|------|:---:|:---:|")
            for i, s in enumerate(top[:10], 1):
                lines.append(f"| {i} | {s.get('name', '')} | {s.get('ratio', '')}% | {s.get('change', '')} |")
            lines.append("")
        else:
            lines.append("（无持股数据）")
            lines.append("")
    else:
        lines.append("（数据暂不可用）")
        lines.append("")

    # 6. Fees
    lines.append("## 六、费率和限额")
    lines.append("")
    if rules:
        lines.append("| 项目 | 数值 |")
        lines.append("|------|------|")
        lines.append(f"| 申购费 | {rules.get('purchase_fee', '—')}% (原价 {rules.get('purchase_fee_original', '—')}%) |")
        lines.append(f"| 管理费 | {rules.get('manage_fee', '—')}%/年 |")
        lines.append(f"| 托管费 | {rules.get('custody_fee', '—')}%/年 |")
        lines.append(f"| 日申购限额 | {rules.get('day_limit', '—')} 元 |")
        lines.append(f"| 最低申购 | {rules.get('min_purchase', '—')} 元 |")
        lines.append("")
    else:
        lines.append("（数据暂不可用）")
        lines.append("")

    # 7. Chart data (demo.md verified)
    pts = chart.get("chart_points", [])
    if pts:
        lines.append("## 七、净值走势参考")
        lines.append("")
        for pt in pts[:5]:
            dt = pt.get("date", str(pt)) if isinstance(pt, dict) else str(pt)
            vl = pt.get("value", pt.get("close", "")) if isinstance(pt, dict) else ""
            lines.append(f"- {dt}: {vl}")
        lines.append("")

    # 8. Recommendation
    lines.append("## 八、买入建议")
    lines.append("")

    is_qdii = "QDII" in name
    is_index = any(kw in name for kw in ["指数", "ETF联接", "ETF"])
    is_c_share = name.endswith("C")

    if is_qdii:
        fund_type = "QDII被动指数" if is_index else "QDII主动"
        lines.append(f"### 基金类型")
        lines.append(f"- 类型：{fund_type}基金")
        lines.append(f"- 份额：{'C类（适合短期持有）' if is_c_share else 'A类（适合长期持有）'}")
        lines.append("")
        lines.append(f"### ✅ 买入策略：{'定投（DCA）' if is_index else '分批建仓'}")
        lines.append("")
        lines.append("| 项目 | 建议 |")
        lines.append("|------|------|")
        lines.append(f"| 方式 | {'日/周定投，持续3-6个月' if is_index else '分3批买入，每批间隔1周'} |")
        lines.append("| 单笔上限 | ¥5,000（保守）/ ¥10,000（进取） |")
        lines.append("| 总仓位上限 | ≤总资金15%（QDII为卫星仓位） |")
        lines.append("| 持有周期 | ≥6个月（QDII赎回到账T+7~T+10） |")
        lines.append("| 止盈线 | +20%（被动）/ +30%（主动） |")
        lines.append("| 止损逻辑 | 不设止损（被动）/ -20%反思（主动） |")
        lines.append("")
        lines.append("### ⚠️ QDII 特有风险")
        lines.append("- 汇率风险：人民币升值侵蚀收益")
        lines.append("- 到账慢：赎回需 T+7~T+10")
        lines.append("- 额度有限：可能触发限购")
        lines.append("")
    elif is_index:
        lines.append("### ✅ 买入策略：定投（DCA）")
        lines.append("")
        lines.append("| 项目 | 建议 |")
        lines.append("|------|------|")
        lines.append("| 方式 | 周定投 |")
        lines.append("| 单次金额 | ¥500-¥2,000 |")
        lines.append("| 总仓位上限 | ≤总资金20% |")
        lines.append("| 止盈 | PE历史分位>80%时减仓1/2 |")
        lines.append("| 止损 | 不设止损（指数不死） |")
        lines.append("")
    else:
        lines.append("### ✅ 买入策略：分批建仓")
        lines.append("")
        lines.append("| 项目 | 建议 |")
        lines.append("|------|------|")
        lines.append("| 方式 | 分3批买入，每批间隔1周 |")
        lines.append("| 单笔上限 | ¥3,000（保守）/ ¥6,000（进取） |")
        lines.append("| 总仓位上限 | ≤总资金10%（单只主动基金） |")
        lines.append("| 持有周期 | ≥1年 |")
        lines.append("| 止盈线 | +30%~+50% |")
        lines.append("| 止损线 | -20%（经理变更即清仓） |")
        lines.append("")

    lines.append("### 🔴 证伪条件（触发即卖出）")
    if is_qdii and is_index:
        lines.append("1. 跟踪指数发生根本性变化")
        lines.append("2. 基金规模<1亿 → 清盘风险")
        lines.append("3. 大佬集体清仓≥3人 → 共识逆转")
    elif is_qdii:
        lines.append("1. 基金经理变更 → 主动基金核心是经理本人")
        lines.append("2. 大佬集体清仓≥3人 → 共识逆转")
        lines.append("3. 基金规模<1.5亿 → 清盘风险")
        lines.append("4. QDII额度用尽 → 暂停申购")
    else:
        lines.append("1. 基金经理变更 → 主动基金核心是经理本人")
        lines.append("2. 大佬集体清仓≥3人 → 共识逆转")
        lines.append("3. 基金规模<1.5亿 → 清盘风险")
    lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("> ⚠️ **免责声明**：以上分析基于公开数据自动生成，不构成投资建议。")
    lines.append("> 大佬信号是参考，不是决策依据。请结合自身情况做出最终决定。")
    return "\n".join(lines)


# ── Main ──────────────────────────────────────────────────────────────────


def _console_safe(text):
    """Strip emoji for Windows console."""
    try:
        text.encode("stdout")
        return text
    except (UnicodeEncodeError, UnicodeDecodeError):
        import re
        return re.sub(r'[^\x00-\x7F\u4e00-\u9fff\u3000-\u303f\uff00-\uffef]', '', text)


def main():
    # Windows console UTF-8 fix
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        # Also set environment for subprocess
        os.environ["PYTHONIOENCODING"] = "utf-8"

    print(f"\n{'='*60}")
    print("  Generate Fund-Monitor Report + Fund-Checklist Analysis")
    print(f"{'='*60}\n")

    trading, snapshot, diff = _load_data()
    strong_buy, buy_signal, others = _classify_funds(trading)

    print(f"  strong_buy (≥3人): {len(strong_buy)}")
    print(f"  buy (==2人):       {len(buy_signal)}")
    print(f"  neutral:           {len(others)}")
    for item in strong_buy:
        print(f"    [{item['buy_count']}人] {item['name']} ({item['code']})")

    # ── Generate fund-monitor report ──
    report = _generate_report(strong_buy, buy_signal, others)
    today = _today_str()

    report_path = REPORTS_DIR / "auto" / f"daily-{today}.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding="utf-8")

    latest_path = REPORTS_DIR / "auto" / "latest.md"
    latest_path.write_text(report, encoding="utf-8")
    print(f"\n  ✅ Report → {report_path.relative_to(_PROJECT_ROOT)}")

    # ── Run fund-checklist for strong_buy ──
    if strong_buy:
        print(f"\n{'='*60}")
        print("  Running Fund-Checklist Deep Analysis for Strong Buy Funds")
        print(f"{'='*60}\n")
        _run_fund_checklist(strong_buy)

    print(f"\n{'='*60}")
    print("  ✅ Done!")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
