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


def load_vp():
    if VP_PATH.exists():
        return json.loads(VP_PATH.read_text("utf-8"))
    return {"created": TODAY, "initial_cash": INITIAL_CASH, "cash": INITIAL_CASH,
            "total_invested": 0, "total_fees": 0, "holdings": {}, "history": [], "snapshots": []}

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
    print(f"   持仓 {len(vp['holdings'])} 只, 现金 {vp['cash']:,.0f}")

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
    for code, h in list(vp["holdings"].items()):
        info = funds.get(code, {})
        day_ret = info.get("day_return", 0) or 0
        if day_ret < -12:
            today_actions.append({"action": "SELL", "code": code, "name": h["name"],
                                  "amount": h["cost_basis"], "reason": f"大跌 {day_ret:.1f}%"})
            vp["cash"] += h["cost_basis"] * 0.995
            vp["total_fees"] += h["cost_basis"] * 0.005
            del vp["holdings"][code]

    available = MAX_POSITIONS - len(vp["holdings"])
    for r in results:
        if available <= 0: break
        if r["blocked"] or r["code"] in vp["holdings"]: continue
        if r["score"] < 3.0: continue
        today_actions.append({"action": "BUY", "code": r["code"], "name": r["name"],
                              "amount": BUY_AMOUNT, "reason": f"评分 {r['score']:.1f}"})
        fee = BUY_AMOUNT * 0.0015
        vp["cash"] -= BUY_AMOUNT + fee
        vp["total_invested"] += BUY_AMOUNT
        vp["total_fees"] += fee
        vp["holdings"][r["code"]] = {"name": r["name"], "cost_basis": BUY_AMOUNT,
                                      "buy_date": TODAY, "buy_score": r["score"]}
        available -= 1

    # 保存
    for a in today_actions:
        vp["history"].append({**a, "date": TODAY})
    total_val = vp["cash"] + sum(h["cost_basis"] for h in vp["holdings"].values())
    vp["snapshots"].append({"date": TODAY, "total_value": round(total_val, 2),
                            "cash": round(vp["cash"], 2), "holdings": len(vp["holdings"]),
                            "actions": len(today_actions)})
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
