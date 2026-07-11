#!/usr/bin/env python3
"""每日模拟实盘 — 基于自选列表的虚拟交易

通过 GitHub Actions 每天 14:30 自动运行：
1. 拉取自选列表 + 真实持仓
2. Layer 1 风控：RSI/超买/估值拦截
3. Layer 2 五维评分
4. 对比昨日虚拟持仓 → 生成买卖建议
5. 更新 virtual_portfolio.json
6. 生成 reports/sim/YYYY-MM-DD.md 日报

Cookie 通过环境变量 JD_COOKIES 传入（GitHub Secrets）
"""

import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tools.jd_finance_api import (
    get_watchlist, get_user_holdings, get_fund_detail,
    get_fund_chart_data, get_fund_trade_rules, _ensure_cookies,
)
from tools.technical_indicators import compute_rsi, compute_entry_timing_score


# ── 配置 ──
INITIAL_CASH = 100000  # 虚拟本金
BUY_AMOUNT = 5000      # 每笔买入金额
MAX_POSITIONS = 8       # 最大持仓数
TAKE_PROFIT_PCT = 30    # 止盈线
STOP_LOSS_PCT = -15     # 止损线
TRAILING_TP_ACTIVATE = 15  # 移动止盈激活
TRAILING_TP_DRAWDOWN = 8   # 移动止盈回撤幅度

SIM_DIR = PROJECT_ROOT / "reports" / "sim"
SIM_DIR.mkdir(parents=True, exist_ok=True)
VP_PATH = SIM_DIR / "virtual_portfolio.json"

TODAY = datetime.now().strftime("%Y-%m-%d")
TODAY_CN = datetime.now().strftime("%Y年%m月%d日")


# ── 工具函数 ──
def _float(v, default=0.0):
    try: return float(v)
    except: return default


def load_virtual_portfolio():
    """加载虚拟持仓"""
    if VP_PATH.exists():
        return json.loads(VP_PATH.read_text("utf-8"))
    # 初始化
    return {
        "created": TODAY,
        "initial_cash": INITIAL_CASH,
        "cash": INITIAL_CASH,
        "total_invested": 0,
        "total_fees": 0,
        "holdings": {},        # {code: {name, shares, cost_basis, buy_date, buy_price}}
        "history": [],         # [{date, action, code, name, amount, price, reason}]
        "pending_buys": [],    # T+1 确认中的买入
        "daily_snapshots": [], # 每日净值快照
    }


def save_virtual_portfolio(vp):
    """保存虚拟持仓"""
    VP_PATH.write_text(json.dumps(vp, ensure_ascii=False, indent=2), encoding="utf-8")


def compute_fund_score(code, name, cookies):
    """简化的五维评分（适配 GitHub Actions）"""
    score = 3.0
    details = {}

    try:
        detail = get_fund_detail(code, cookies=cookies)
        if detail:
            # 费率
            fee = detail.get("fee_info", {})
            mf_text = fee.get("buy_fee", "")
            try:
                import re
                nums = re.findall(r'[\d.]+', mf_text)
                mf = float(nums[0]) if nums else 1.0
            except:
                mf = 1.0
            if mf < 0.5: score += 0.5
            elif mf > 1.5: score -= 0.5

            # 业绩
            perf = detail.get("performance", {}).get("performance", [])
            for p in perf:
                period = p.get("period", "")
                rank_pct = p.get("rank_pct")
                if "近6月" in period and rank_pct is not None:
                    if rank_pct > 0.7: score += 0.5
                    elif rank_pct < 0.3: score -= 0.5
                if "近1年" in period and rank_pct is not None:
                    if rank_pct > 0.7: score += 0.5
                    elif rank_pct < 0.3: score -= 0.5

            details["fee"] = mf
            details["fund_type"] = detail.get("profile", {}).get("fund_type", "")
    except Exception:
        pass

    return min(5.0, max(1.0, score)), details


def layer1_risk_check(code, cookies):
    """Layer 1 风控：RSI + 超买检测"""
    warnings = []
    try:
        pts = get_fund_chart_data(code).get("chart_points", [])
        if len(pts) < 60:
            return {"pass": True, "warnings": []}

        yaxis = [_float(p.get("yAxis", 0)) for p in pts]
        navs = [(100 + v) / 100 for v in yaxis]  # 累计收益% → 净值

        rsi = compute_rsi(navs)
        timing = compute_entry_timing_score(pts, TODAY)

        if timing.get("should_warn"):
            warnings.append(f"RSI={rsi:.1f} 超买警告，综合择时评分={timing.get('entry_score',0):.1f}")

        # 近期涨幅过大警告
        if len(navs) >= 20:
            ret_1m = (navs[-1] - navs[-20]) / navs[-20] * 100
            if ret_1m > 15:
                warnings.append(f"近1月涨幅 {ret_1m:.1f}%，追高风险")

        return {
            "pass": len(warnings) == 0,
            "warnings": warnings,
            "rsi": round(rsi, 1),
            "timing_score": timing.get("entry_score", 0),
        }
    except Exception:
        return {"pass": True, "warnings": []}


# ── 主流程 ──
def run():
    print(f"=== 每日模拟实盘 {TODAY} ===")

    # 0. 认证
    cookies_str = os.environ.get("JD_COOKIES", "")
    if cookies_str:
        # 从 GitHub Secrets JSON 字符串加载
        try:
            cookies = json.loads(cookies_str)
        except json.JSONDecodeError:
            # 尝试 key=value; 格式
            cookies = {}
            for part in cookies_str.split(";"):
                if "=" in part:
                    k, v = part.strip().split("=", 1)
                    cookies[k.strip()] = v.strip()
        # 保存临时 cookies 供 API 使用
        auth_dir = PROJECT_ROOT / "data" / "jd_auth"
        auth_dir.mkdir(parents=True, exist_ok=True)
        (auth_dir / "cookies.json").write_text(json.dumps(cookies, ensure_ascii=False), encoding="utf-8")
    else:
        print("[ERROR] 未设置 JD_COOKIES 环境变量")
        # 尝试用本地 cookies
        cookies = _ensure_cookies(offline=True)
        if not cookies:
            return

    # 1. 拉取数据
    print("1. 拉取自选列表...")
    wl = get_watchlist(cookies=cookies)
    if not wl or not wl.get("funds"):
        print("[ERROR] 无法获取自选列表")
        return
    watchlist = {f["fund_code"]: f for f in wl["funds"]}
    print(f"   自选基金: {len(watchlist)} 只")

    # 2. 加载虚拟持仓
    vp = load_virtual_portfolio()
    print(f"   当前虚拟持仓: {len(vp['holdings'])} 只, 现金 ¥{vp['cash']:,.0f}")

    # 3. Layer 1 & Layer 2 逐一分析
    print("2. 评分 + 风控...")
    candidates = []
    warnings = []

    for code, info in list(watchlist.items())[:50]:  # 限制50只防止超时
        name = info.get("fund_name", code)
        print(f"   {code} {name}...", end=" ")

        # Layer 1
        risk = layer1_risk_check(code, cookies)
        if not risk["pass"]:
            warnings.append({"code": code, "name": name, "warnings": risk["warnings"],
                             "rsi": risk.get("rsi")})
            print(f"BLOCKED (RSI={risk.get('rsi')})")
            continue

        # Layer 2
        score, details = compute_fund_score(code, name, cookies)
        print(f"score={score:.1f}")
        candidates.append({
            "code": code, "name": name,
            "score": score, "details": details,
            "day_return": info.get("day_return", 0),
        })

    # 4. 排序 + 生成建议
    candidates.sort(key=lambda x: -x["score"])
    print(f"\n3. 候选基金: {len(candidates)} 只 (通过风控), 高危拦截: {len(warnings)} 只")

    today_actions = []

    # 卖出检查
    for code, h in list(vp["holdings"].items()):
        info = watchlist.get(code, {})
        current_price_pct = info.get("total_pnl_pct", 0)
        # 简化: 用自选盈亏近似 (不够精确但可行)
        # 实际应该从 get_fund_detail 拿净值算

        sell_reason = None
        if current_price_pct >= TAKE_PROFIT_PCT:
            sell_reason = f"止盈 {current_price_pct:.1f}%"
        elif current_price_pct <= STOP_LOSS_PCT:
            sell_reason = f"止损 {current_price_pct:.1f}%"

        if sell_reason:
            amount = h["cost_basis"] * (1 + current_price_pct / 100)
            today_actions.append({
                "action": "SELL", "code": code, "name": h["name"],
                "amount": round(amount, 2), "reason": sell_reason,
            })
            # 卖出手续费 0.5%
            fee = amount * 0.005
            vp["cash"] += amount - fee
            vp["total_fees"] += fee
            del vp["holdings"][code]

    # 买入建议
    available_slots = MAX_POSITIONS - len(vp["holdings"])
    buy_count = 0
    for c in candidates:
        if buy_count >= available_slots:
            break
        if c["code"] in vp["holdings"]:
            continue  # 已持有
        if c["score"] < 3.0:
            continue  # 分数太低

        today_actions.append({
            "action": "BUY", "code": c["code"], "name": c["name"],
            "amount": BUY_AMOUNT, "reason": f"评分 {c['score']:.1f}",
        })
        fee = BUY_AMOUNT * 0.0015
        vp["cash"] -= BUY_AMOUNT + fee
        vp["total_invested"] += BUY_AMOUNT
        vp["total_fees"] += fee
        vp["holdings"][c["code"]] = {
            "name": c["name"],
            "cost_basis": BUY_AMOUNT,
            "buy_date": TODAY,
            "buy_score": c["score"],
        }
        buy_count += 1

    # 5. 记录历史
    if today_actions:
        for a in today_actions:
            vp["history"].append({**a, "date": TODAY})

    # 当日净值快照
    total_value = vp["cash"] + sum(
        h["cost_basis"] for h in vp["holdings"].values()
    )
    vp["daily_snapshots"].append({
        "date": TODAY,
        "total_value": round(total_value, 2),
        "cash": round(vp["cash"], 2),
        "holdings_count": len(vp["holdings"]),
        "actions_today": len(today_actions),
    })

    save_virtual_portfolio(vp)

    # 6. 生成日报
    print("\n4. 生成日报...")
    report_lines = [
        f"# 模拟实盘日报 — {TODAY_CN}",
        "",
        f"> 自动生成于 GitHub Actions | 自选基金 {len(watchlist)} 只",
        "",
        "## 今日操作建议",
        "",
    ]

    if today_actions:
        report_lines.append(f"| 操作 | 基金 | 金额 | 原因 |")
        report_lines.append(f"|------|------|------|------|")
        for a in today_actions:
            action_cn = "买入" if a["action"] == "BUY" else "卖出"
            report_lines.append(f"| {action_cn} | {a['name']} ({a['code']}) | ¥{a['amount']:,.0f} | {a['reason']} |")
    else:
        report_lines.append("今日无操作建议。")

    report_lines += [
        "",
        "## 组合状态",
        "",
        f"| 指标 | 值 |",
        f"|------|------|",
        f"| 总资产 | ¥{total_value:,.2f} |",
        f"| 现金 | ¥{vp['cash']:,.2f} |",
        f"| 持仓数 | {len(vp['holdings'])} 只 |",
        f"| 已投入 | ¥{vp['total_invested']:,.0f} |",
        f"| 手续费累计 | ¥{vp['total_fees']:,.2f} |",
        f"| 总收益率 | {((total_value - INITIAL_CASH) / INITIAL_CASH * 100):+.2f}% |",
        "",
        "## 当前持仓",
        "",
    ]
    if vp["holdings"]:
        report_lines.append(f"| 基金 | 成本 | 买入日期 | 买入评分 |")
        report_lines.append(f"|------|------|----------|----------|")
        for code, h in vp["holdings"].items():
            report_lines.append(f"| {h['name']} ({code}) | ¥{h['cost_basis']:,.0f} | {h['buy_date']} | {h['buy_score']:.1f} |")
    else:
        report_lines.append("空仓")

    if warnings:
        report_lines += [
            "",
            "## ⚠️ 风控拦截（不建议买入）",
            "",
        ]
        for w in warnings:
            report_lines.append(f"- **{w['name']} ({w['code']})**: {'; '.join(w['warnings'])}")

    report_lines += [
        "",
        "## 评分排行 TOP 5",
        "",
        f"| 基金 | 评分 | 状态 |",
        f"|------|------|------|",
    ]
    for c in candidates[:5]:
        status = "已持仓" if c["code"] in vp["holdings"] else "可买入"
        report_lines.append(f"| {c['name']} ({c['code']}) | {c['score']:.1f} | {status} |")

    report_lines += [
        "",
        "---",
        f"*下次运行: {datetime.now() + timedelta(days=1)} 14:30 CST*",
    ]

    report_path = SIM_DIR / f"{TODAY}.md"
    report_path.write_text("\n".join(report_lines), encoding="utf-8")
    print(f"   日报已保存: {report_path}")

    # 7. 输出摘要
    print(f"\n=== 完成 ===")
    print(f"总资产: ¥{total_value:,.2f} ({((total_value-INITIAL_CASH)/INITIAL_CASH*100):+.2f}%)")
    print(f"今日操作: {len(today_actions)} 笔")
    print(f"风控拦截: {len(warnings)} 只")

    return total_value


if __name__ == "__main__":
    run()
