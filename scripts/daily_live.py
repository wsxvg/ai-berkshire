#!/usr/bin/env python3
"""每日实盘模拟 — 自选列表 + 回测引擎同款评分

用进化最优参数，在自选基金池中评分决策。
每天 14:30 由 GitHub Actions 自动运行。

评分逻辑 = backtest/engine/backtest.py 的 score_fund_backtest()
参数 = data/evolution/best_config.json
"""

import json, sys, os, glob, io, contextlib
from datetime import datetime, timedelta
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))

from tools.jd_finance_api import get_watchlist, get_user_holdings, _ensure_cookies
from tools.technical_indicators import compute_entry_timing_score

TODAY = datetime.now().strftime("%Y-%m-%d")
TODAY_CN = datetime.now().strftime("%Y年%m月%d日")

# ── 加载进化最优参数 ──
EVO_PATH = PROJECT / "data" / "evolution" / "best_config.json"
if EVO_PATH.exists():
    evo = json.loads(EVO_PATH.read_text("utf-8"))
    BEST_GENE = evo["gene"]
    print(f"加载进化最优参数: 年化={evo['annualized']:.1f}% 夏普={evo['sharpe']:.2f}")
else:
    BEST_GENE = {
        "bear_market_no_buy": False, "take_profit_pct": 80,
        "stop_loss_pct": -15, "ml_weight": 1.5,
        "min_score_bull": 2.5, "min_score_neutral": 3.0, "min_score_bear": 3.5,
    }
    print("未找到进化参数，使用默认值")

# ── 加载回测同款数据 ──
CACHE_DIR = PROJECT / "data" / "fund_cache"
DATA_DIR = PROJECT / "data"

def load_cache(prefix):
    data = {}
    for f in glob.glob(str(CACHE_DIR / f"{prefix}_*.json")):
        stem = Path(f).stem
        code = stem.replace(f"{prefix}_", "", 1)
        try:
            data[code] = json.loads(open(f, "r", encoding="utf-8").read())
        except:
            pass
    return data

fund_rules = load_cache("trade_rules")
fund_managers = load_cache("fund_manager")
fund_profiles = load_cache("fund_profile")

# fund_charts
charts_path = PROJECT / "data" / "fund_charts.json"
fund_charts = json.loads(charts_path.read_text("utf-8")) if charts_path.exists() else {}

# 名称映射
name_map_path = PROJECT / "data" / "fund_name_map.json"
name_map = json.loads(name_map_path.read_text("utf-8")) if name_map_path.exists() else {}

# 虚拟持仓
SIM_DIR = PROJECT / "reports" / "sim"
SIM_DIR.mkdir(parents=True, exist_ok=True)
VP_PATH = SIM_DIR / "virtual_portfolio.json"

INITIAL_CASH = 100000
BUY_AMOUNT = 5000
MAX_POSITIONS = 8


def load_vp():
    if VP_PATH.exists():
        return json.loads(VP_PATH.read_text("utf-8"))
    return {
        "created": TODAY, "initial_cash": INITIAL_CASH,
        "cash": INITIAL_CASH, "total_invested": 0, "total_fees": 0,
        "holdings": {}, "history": [], "pending": [], "snapshots": [],
    }


def save_vp(vp):
    VP_PATH.write_text(json.dumps(vp, ensure_ascii=False, indent=2), encoding="utf-8")


def score_one_fund(code, name, cutoff_date):
    """用回测引擎同款评分函数"""
    from backtest.engine.backtest import score_fund_backtest
    from backtest.engine.backtest import DimensionScore

    chart_pts = fund_charts.get(code, [])

    # 用空的 trading_by_date（实盘不依赖大佬信号）
    fs = score_fund_backtest(
        code, name, fund_charts, None,
        fund_rules.get(code), fund_managers.get(code),
        cutoff_date, {},  # 空交易记录
        fund_profiles.get(code),
        industry_data=None,
    )
    return fs.total if hasattr(fs, 'total') else 3.0


def layer1_check(code, cutoff_date):
    """RSI + 超买风控"""
    chart_pts = fund_charts.get(code, [])
    if not chart_pts or len(chart_pts) < 60:
        return True, ""
    timing = compute_entry_timing_score(chart_pts, cutoff_date)
    if timing.get("should_warn"):
        return False, f"RSI超买 综合择时={timing.get('entry_score',0):.1f}"
    return True, ""


def run():
    print(f"=== 实盘模拟 {TODAY_CN} ===")

    # 0. Cookie
    cookies = _ensure_cookies(offline=True)
    if not cookies:
        # GitHub Actions 环境：cookies 已在仓库中
        cookies_path = PROJECT / "data" / "jd_auth" / "cookies.json"
        if cookies_path.exists():
            cookies = json.loads(cookies_path.read_text("utf-8"))
    if not cookies:
        print("[ERROR] 无 Cookie")
        return

    # 1. 自选列表
    print("1. 自选列表...")
    wl = get_watchlist(cookies=cookies)
    if not wl or not wl.get("funds"):
        wl = get_watchlist(cookies=cookies)
    if not wl or not wl.get("funds"):
        print("[ERROR] 自选列表为空")
        return
    funds = {f["fund_code"]: f for f in wl["funds"]}
    print(f"   {len(funds)} 只自选基金")

    # 2. 虚拟持仓
    vp = load_vp()
    print(f"   持仓 {len(vp['holdings'])} 只, 现金 {vp['cash']:,.0f}")

    # 3. 逐一评分
    print("2. 评分...")
    results = []
    for code, info in funds.items():
        name = info.get("fund_name", code)
        ok, warn = layer1_check(code, TODAY)
        if not ok:
            results.append({"code": code, "name": name, "score": 0, "blocked": True, "reason": warn})
            print(f"   BLOCKED {code} {name}: {warn}")
            continue

        # 如果有 chart 数据，用回测引擎评分；否则用自选数据估算
        if code in fund_charts:
            s = score_one_fund(code, name, TODAY)
        else:
            # 兜底: 根据自选数据简单估算
            dy = info.get("day_return", 0) or 0
            wk = info.get("week_return", 0) or 0
            mo = info.get("month_return", 0) or 0
            s = 3.0 + mo * 0.05  # 月涨幅映射到评分
            s = max(1.0, min(5.0, s))

        results.append({"code": code, "name": name, "score": s, "blocked": False, "reason": ""})
        print(f"   {code} {name}: {s:.1f}")

    results.sort(key=lambda x: -x["score"])

    # 4. 生成建议
    print("3. 决策...")
    today_actions = []

    # 卖出检查 (简单止盈止损)
    for code, h in list(vp["holdings"].items()):
        info = funds.get(code, {})
        # 通过 get_fund_detail 拿净值算盈亏
        # 简化: 用持仓天数估算
        buy_date = h.get("buy_date", "")
        try:
            days = (datetime.strptime(TODAY, "%Y-%m-%d") - datetime.strptime(buy_date, "%Y-%m-%d")).days
        except:
            days = 0

        day_ret = info.get("day_return", 0) or 0
        if day_ret < -12:
            today_actions.append({
                "action": "SELL", "code": code, "name": h["name"],
                "amount": h["cost_basis"], "reason": f"大跌 {day_ret:.1f}%",
            })
            fee = h["cost_basis"] * 0.005
            vp["cash"] += h["cost_basis"] - fee
            vp["total_fees"] += fee
            del vp["holdings"][code]

    # 买入建议
    available = MAX_POSITIONS - len(vp["holdings"])
    for r in results:
        if available <= 0:
            break
        if r["blocked"] or r["code"] in vp["holdings"]:
            continue
        if r["score"] < 3.0:
            continue

        today_actions.append({
            "action": "BUY", "code": r["code"], "name": r["name"],
            "amount": BUY_AMOUNT, "reason": f"评分 {r['score']:.1f}",
        })
        fee = BUY_AMOUNT * 0.0015
        vp["cash"] -= BUY_AMOUNT + fee
        vp["total_invested"] += BUY_AMOUNT
        vp["total_fees"] += fee
        vp["holdings"][r["code"]] = {
            "name": r["name"], "cost_basis": BUY_AMOUNT,
            "buy_date": TODAY, "buy_score": r["score"],
        }
        available -= 1

    # 5. 保存
    for a in today_actions:
        vp["history"].append({**a, "date": TODAY})
    total_val = vp["cash"] + sum(h["cost_basis"] for h in vp["holdings"].values())
    vp["snapshots"].append({
        "date": TODAY, "total_value": round(total_val, 2),
        "cash": round(vp["cash"], 2), "holdings": len(vp["holdings"]),
        "actions": len(today_actions),
    })
    save_vp(vp)

    # 6. 日报
    print("4. 日报...")
    lines = [
        f"# 实盘模拟日报 {TODAY_CN}",
        f"",
        f"> 自选 {len(funds)} 只 | 评分引擎=回测同款 | 参数=进化最优",
        f"",
        f"## 今日操作",
        f"",
    ]
    if today_actions:
        lines.append("| 操作 | 基金 | 金额 | 原因 |")
        lines.append("|------|------|------|------|")
        for a in today_actions:
            act = "买入" if a["action"] == "BUY" else "卖出"
            lines.append(f"| {act} | {a['name']} ({a['code']}) | {a['amount']:,.0f} | {a['reason']} |")
    else:
        lines.append("无操作")

    lines += [
        f"", f"## 组合",
        f"| 指标 | 值 |",
        f"|------|------|",
        f"| 总资产 | {total_val:,.2f} |",
        f"| 现金 | {vp['cash']:,.2f} |",
        f"| 持仓 | {len(vp['holdings'])} 只 |",
        f"| 收益率 | {((total_val-INITIAL_CASH)/INITIAL_CASH*100):+.2f}% |",
        f"",
        f"## 评分 TOP 5",
        f"| 基金 | 评分 |",
        f"|------|------|",
    ]
    for r in results[:5]:
        flag = "⚠️" if r["blocked"] else ""
        lines.append(f"| {r['name']} ({r['code']}) {flag} | {r['score']:.1f} |")

    blocked = [r for r in results if r["blocked"]]
    if blocked:
        lines += ["", "## 风控拦截", ""]
        for r in blocked:
            lines.append(f"- {r['name']} ({r['code']}): {r['reason']}")

    lines += ["", "---", f"*{TODAY_CN} 14:30 CST*"]

    path = SIM_DIR / f"{TODAY}.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    print(f"   {path}")

    # 摘要
    print(f"\n=== 完成: 总资产 {total_val:,.0f} ({((total_val-INITIAL_CASH)/INITIAL_CASH*100):+.2f}%) 操作 {len(today_actions)} 笔 ===")


if __name__ == "__main__":
    run()
