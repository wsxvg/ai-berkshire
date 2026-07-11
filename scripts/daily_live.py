#!/usr/bin/env python3
"""每日实盘模拟 — 自选列表 + 大佬信号 + 回测引擎同款评分

每天 14:30 由 GitHub Actions 自动运行。
评分逻辑 = backtest/engine/backtest.py 的 score_fund_backtest()
大佬信号 = backtest/data/trading_by_date_fixed.json
参数 = data/evolution/best_config.json
"""

import json, sys, os, glob
from datetime import datetime
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))

from tools.jd_finance_api import get_watchlist, _ensure_cookies, _verify_cookies
from tools.technical_indicators import compute_entry_timing_score

TODAY = datetime.now().strftime("%Y-%m-%d")
TODAY_CN = datetime.now().strftime("%Y年%m月%d日")

# ── 进化最优参数 ──
EVO_PATH = PROJECT / "data" / "evolution" / "best_config.json"
if EVO_PATH.exists():
    evo = json.loads(EVO_PATH.read_text("utf-8"))
    BEST_GENE = evo["gene"]
    print(f"进化参数: 年化={evo['annualized']:.1f}% 夏普={evo['sharpe']:.2f}")
else:
    BEST_GENE = {"bear_market_no_buy": False, "take_profit_pct": 80, "stop_loss_pct": -15, "ml_weight": 1.5,
                 "min_score_bull": 2.5, "min_score_neutral": 3.0, "min_score_bear": 3.5}

# ── 大佬交易记录（回测同款）──
trading_by_date = {}
tp = PROJECT / "backtest" / "data" / "trading_by_date_fixed.json"
if tp.exists():
    trading_by_date = json.loads(tp.read_text("utf-8"))
    print(f"大佬交易: {len(trading_by_date)} 个交易日")
else:
    print("[WARN] 无大佬交易记录")

# ── 基金数据 ──
CACHE_DIR = PROJECT / "data" / "fund_cache"
def load_cache(prefix):
    data = {}
    for f in glob.glob(str(CACHE_DIR / f"{prefix}_*.json")):
        code = Path(f).stem.replace(f"{prefix}_", "", 1)
        try: data[code] = json.loads(open(f, "r", encoding="utf-8").read())
        except: pass
    return data

fund_rules = load_cache("trade_rules")
fund_managers = load_cache("fund_manager")
fund_profiles = load_cache("fund_profile")

charts_path = PROJECT / "data" / "fund_charts.json"
fund_charts = json.loads(charts_path.read_text("utf-8")) if charts_path.exists() else {}

# ── 虚拟持仓 ──
SIM_DIR = PROJECT / "reports" / "sim"
SIM_DIR.mkdir(parents=True, exist_ok=True)
VP_PATH = SIM_DIR / "virtual_portfolio.json"

INITIAL_CASH = 100000
BUY_AMOUNT = 5000
MAX_POSITIONS = 8


def get_t_plus_n(code):
    """获取基金 T+N 确认天数（从 fund_rules 缓存）"""
    rules = fund_rules.get(code, {})
    confirm = rules.get("confirm_date", "")
    buy_date = rules.get("buy_date", "")
    if confirm and buy_date:
        try:
            c_day = int(confirm.split("-")[-1])
            b_day = int(buy_date.split(" ")[0].split("-")[-1])
            diff = (c_day - b_day) % 30
            if diff <= 1: return 1
            if diff <= 2: return 2
            return diff
        except: pass
    # Fallback: 根据基金类型判断
    profile = fund_profiles.get(code, {})
    ft = profile.get("fund_type", "")
    if "QDII" in ft: return 2
    return 1


def add_biz_days(date_str, n):
    """简单加 N 个日历日（近似交易日）"""
    try:
        from datetime import timedelta
        dt = datetime.strptime(date_str[:10], "%Y-%m-%d")
        return (dt + timedelta(days=n + max(0, n // 5 * 2))).strftime("%Y-%m-%d")
    except:
        return date_str


def redemption_fee(days_held, code):
    """赎回费率（按持有天数）"""
    rules = fund_rules.get(code, {})
    tiers = rules.get("redeem_fees", [])
    for t in tiers:
        interval = t.get("interval", "")
        rate = float(t.get("rate", 0))
        # 简化为: 直接用费率区分
        if days_held < 7 and "＜7" in interval:
            return rate / 100
        elif 7 <= days_held < 365 and "7日≤" in interval and "＜365" in interval:
            return rate / 100
    # 兜底
    if days_held < 7: return 0.015
    if days_held < 30: return 0.0075
    if days_held < 365: return 0.005
    return 0.0


def load_vp():
    if VP_PATH.exists():
        vp = json.loads(VP_PATH.read_text("utf-8"))
        vp.setdefault("pending", [])
        for h in vp.get("holdings", {}).values():
            h.setdefault("confirmed", True)
        return vp
    return {"created": TODAY, "initial_cash": INITIAL_CASH, "cash": INITIAL_CASH,
            "total_invested": 0, "total_fees": 0,
            "holdings": {}, "pending": [], "history": [], "snapshots": []}

def save_vp(vp):
    VP_PATH.write_text(json.dumps(vp, ensure_ascii=False, indent=2), encoding="utf-8")


def score_fund(code, name, cutoff):
    """回测引擎同款评分 — 包含大佬 smart_money 维度"""
    from backtest.engine.backtest import score_fund_backtest
    fs = score_fund_backtest(
        code, name, fund_charts, None,
        fund_rules.get(code), fund_managers.get(code),
        cutoff, trading_by_date,  # ← 大佬交易信号！
        fund_profiles.get(code),
    )
    return fs.total if hasattr(fs, 'total') else 3.0


def layer1_check(code, cutoff):
    chart_pts = fund_charts.get(code, [])
    if len(chart_pts) < 60:
        return True, ""
    timing = compute_entry_timing_score(chart_pts, cutoff)
    if timing.get("should_warn"):
        return False, f"RSI超买 择时={timing.get('entry_score',0):.1f}"
    return True, ""


def run():
    print(f"=== 实盘模拟 {TODAY_CN} ===")

    # Cookie
    cookies = _ensure_cookies(offline=True)
    if not cookies:
        cp = PROJECT / "data" / "jd_auth" / "cookies.json"
        if cp.exists():
            cookies = json.loads(cp.read_text("utf-8"))
    if not cookies:
        print("[ERROR] 无 Cookie"); return

    valid, info = _verify_cookies(cookies)
    print(f"Cookie: {'有效' if valid else '无效'}")

    # 自选列表
    print("1. 自选列表...")
    wl = get_watchlist(cookies=cookies)
    if not wl or not wl.get("funds"):
        print(f"   DEBUG: {json.dumps(wl, ensure_ascii=False)[:500]}")
        print("[ERROR] 自选列表为空 (Cookie可能过期或API变更)"); return
    funds = {f["fund_code"]: f for f in wl["funds"]}
    print(f"   {len(funds)} 只")

    # 虚拟持仓
    vp = load_vp()

    # ── T+N 结算: 确认到期的待确认买入 ──
    settled_count = 0
    remaining = []
    for pb in vp.get("pending", []):
        if pb.get("confirm_date", "9999") <= TODAY:
            code = pb["code"]
            vp["holdings"][code] = {
                "name": pb["name"], "cost_basis": pb["amount"],
                "buy_date": pb["date"], "buy_score": pb.get("buy_score", 0),
                "confirmed": True, "t_plus_n": pb.get("t_plus_n", 1),
            }
            settled_count += 1
        else:
            remaining.append(pb)
    vp["pending"] = remaining
    if settled_count > 0:
        print(f"   T+N 确认: {settled_count} 笔")

    print(f"   持仓 {len(vp['holdings'])} 只 (含待确认{len(vp['pending'])}笔), 现金 {vp['cash']:,.0f}")

    # 评分
    print("2. 评分 (五维+大佬信号)...")
    results = []
    for code, info in funds.items():
        name = info.get("fund_name", code)
        ok, warn = layer1_check(code, TODAY)
        if not ok:
            results.append({"code": code, "name": name, "score": 0, "blocked": True, "reason": warn})
            print(f"   BLOCKED {name}: {warn}")
            continue
        if code in fund_charts:
            s = score_fund(code, name, TODAY)
        else:
            mo = info.get("month_return", 0) or 0
            s = max(1.0, min(5.0, 3.0 + mo * 0.05))
        results.append({"code": code, "name": name, "score": s, "blocked": False, "reason": ""})
        print(f"   {name} ({code}): {s:.1f}")
    results.sort(key=lambda x: -x["score"])

    # 决策
    print("3. 决策...")
    today_actions = []

    # 卖出检查 (含 T+N 锁定 + 赎回费)
    confirmed_count = sum(1 for h in vp["holdings"].values() if h.get("confirmed", True))
    for code, h in list(vp["holdings"].items()):
        if not h.get("confirmed", True):
            continue  # 待确认，不能卖
        info = funds.get(code, {})
        day_ret = info.get("day_return", 0) or 0
        buy_date = h.get("buy_date", TODAY)
        try:
            days_held = (datetime.strptime(TODAY, "%Y-%m-%d") - datetime.strptime(buy_date, "%Y-%m-%d")).days
        except:
            days_held = 0
        redeem_rate = redemption_fee(days_held, code)

        sell_reason = None
        if day_ret < -12:
            sell_reason = f"大跌 {day_ret:.1f}% (赎回费{redeem_rate*100:.1f}%)"
        elif days_held >= 30 and (info.get("total_pnl_pct") or 0) > 30:
            sell_reason = f"止盈 {info['total_pnl_pct']:.0f}% (持有{days_held}天)"

        if sell_reason:
            amount = h["cost_basis"] * (1 + (info.get("total_pnl_pct", 0) or 0) / 100)
            fee = amount * redeem_rate
            t_n = get_t_plus_n(code)
            today_actions.append({
                "action": "SELL", "code": code, "name": h["name"],
                "amount": round(amount, 2), "reason": sell_reason,
                "fee": round(fee, 2), "redeem_t_plus": t_n,
            })
            vp["cash"] += amount - fee
            vp["total_fees"] += fee
            del vp["holdings"][code]

    # 买入 (T+N 确认)
    available = MAX_POSITIONS - len(vp["holdings"]) - len(vp["pending"])
    for r in results:
        if available <= 0: break
        if r["blocked"] or r["code"] in vp["holdings"]: continue
        # 检查是否已在待确认队列
        if any(p["code"] == r["code"] for p in vp["pending"]): continue
        if r["score"] < 3.0: continue

        t_n = get_t_plus_n(r["code"])
        confirm_date = add_biz_days(TODAY, t_n)
        fee = BUY_AMOUNT * 0.0015  # 申购费 0.15%
        today_actions.append({
            "action": "BUY", "code": r["code"], "name": r["name"],
            "amount": BUY_AMOUNT, "reason": f"评分 {r['score']:.1f} (T+{t_n})",
            "t_plus_n": t_n, "confirm_date": confirm_date,
        })
        vp["cash"] -= BUY_AMOUNT + fee
        vp["total_invested"] += BUY_AMOUNT
        vp["total_fees"] += fee
        vp["pending"].append({
            "code": r["code"], "name": r["name"], "amount": BUY_AMOUNT,
            "date": TODAY, "buy_score": r["score"],
            "t_plus_n": t_n, "confirm_date": confirm_date,
        })
        available -= 1

    # 保存
    for a in today_actions:
        vp["history"].append({**a, "date": TODAY})
    # 总资产 = 现金 + 已确认持仓成本 + 待确认买入金额
    total_val = vp["cash"] + sum(h["cost_basis"] for h in vp["holdings"].values()) + sum(p["amount"] for p in vp["pending"])
    vp["snapshots"].append({"date": TODAY, "total_value": round(total_val, 2),
                            "cash": round(vp["cash"], 2), "holdings": len(vp["holdings"]),
                            "pending": len(vp["pending"]), "actions": len(today_actions)})
    save_vp(vp)

    # 日报
    print("4. 日报...")
    lines = [
        f"# 实盘模拟日报 {TODAY_CN}",
        f"",
        f"> 自选 {len(funds)} 只 | 大佬信号 {len(trading_by_date)}天 | 进化参数",
        f"",
        f"## 今日操作", "",
    ]
    if today_actions:
        lines.append("| 操作 | 基金 | 金额 | 原因 |")
        lines.append("|------|------|------|------|")
        for a in today_actions:
            act = "买入" if a["action"] == "BUY" else "卖出"
            lines.append(f"| {act} | {a['name']} ({a['code']}) | {a['amount']:,.0f} | {a['reason']} |")
    else:
        lines.append("无操作")

    lines += ["", "## 组合", "| 指标 | 值 |", "|------|------|",
              f"| 总资产 | {total_val:,.2f} |", f"| 现金 | {vp['cash']:,.2f} |",
              f"| 持仓 | {len(vp['holdings'])} 只 |",
              f"| 收益率 | {((total_val-INITIAL_CASH)/INITIAL_CASH*100):+.2f}% |",
              "", "## 评分 TOP 5", "| 基金 | 评分 |", "|------|------|"]
    for r in results[:5]:
        flag = " ⚠️" if r["blocked"] else ""
        lines.append(f"| {r['name']} ({r['code']}){flag} | {r['score']:.1f} |")

    blocked = [r for r in results if r["blocked"]]
    if blocked:
        lines += ["", "## 风控拦截", ""]
        for r in blocked:
            lines.append(f"- {r['name']} ({r['code']}): {r['reason']}")

    lines += ["", "---", f"*{TODAY_CN} 14:30 CST*"]
    (SIM_DIR / f"{TODAY}.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"   日报已保存")

    print(f"\n=== 完成: 总资产 {total_val:,.0f} ({((total_val-INITIAL_CASH)/INITIAL_CASH*100):+.2f}%) 操作 {len(today_actions)} 笔 ===")


if __name__ == "__main__":
    run()
