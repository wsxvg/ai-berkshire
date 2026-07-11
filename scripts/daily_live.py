#!/usr/bin/env python3
"""每日实盘模拟 — 复用回测引擎全部风控逻辑

每天 14:30 由 GitHub Actions 自动运行。
组件：Portfolio(仓位/T+N/费率)、score_fund_backtest(五维+大佬)、
      detect_market_state、correlation_filter、行业估值
参数 = data/evolution/best_config.json
"""

import json, sys, os, glob
from datetime import datetime, timedelta
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))

from tools.jd_finance_api import get_watchlist, get_trading_records, _ensure_cookies, _verify_cookies, FOLLOWED_USERS

# ── 回测引擎组件 ──
from backtest.engine.backtest import (
    Portfolio, score_fund_backtest, detect_market_state,
    compute_correlation_matrix,
)
from tools.technical_indicators import compute_entry_timing_score

TODAY = datetime.now().strftime("%Y-%m-%d")
TODAY_CN = datetime.now().strftime("%Y年%m月%d日")

# ── 进化最优参数 ──
EVO_PATH = PROJECT / "data" / "evolution" / "best_config.json"
if EVO_PATH.exists():
    evo = json.loads(EVO_PATH.read_text("utf-8"))
    GENE = evo["gene"]
    print(f"参数: 年化={evo['annualized']:.1f}% 夏普={evo['sharpe']:.2f}")
else:
    GENE = {"bear_market_no_buy": False, "take_profit_pct": 80, "stop_loss_pct": -15,
            "ml_weight": 1.5, "min_score_bull": 2.5, "min_score_neutral": 3.0, "min_score_bear": 3.5,
            "trailing_tp_activate": 15, "trailing_tp_drawdown": 8,
            "cooldown_days": 15, "cooldown_profit_days": 10, "cooldown_loss_days": 30,
            "max_correlation": 0.85, "dynamic_ranking": True,
            "momentum_sell": 2.0, "slippage_pct": 0.1, "cash_reserve_pct": 0.1,
            "max_position_pct": 20, "max_sector_pct": 50, "max_qdii_pct": 50}

# ── 数据加载 ──
CACHE = PROJECT / "data" / "fund_cache"
def load_cache(prefix):
    data = {}
    for f in glob.glob(str(CACHE / f"{prefix}_*.json")):
        code = Path(f).stem.replace(f"{prefix}_", "", 1)
        try: data[code] = json.loads(open(f, encoding="utf-8").read())
        except: pass
    return data

fund_rules = load_cache("trade_rules")
fund_managers = load_cache("fund_manager")
fund_profiles = load_cache("fund_profile")
fund_charts = json.loads((PROJECT / "data" / "fund_charts.json").read_text("utf-8"))

tp = PROJECT / "backtest" / "data" / "trading_by_date_fixed.json"
trading_by_date = json.loads(tp.read_text("utf-8")) if tp.exists() else {}

# 名称映射
name_map = json.loads((PROJECT / "data" / "fund_name_map.json").read_text("utf-8"))
code_to_name = {}
for nm, cd in name_map.items():
    if cd not in code_to_name: code_to_name[cd] = nm

# ── 虚拟持仓 ──
SIM_DIR = PROJECT / "reports" / "sim"
SIM_DIR.mkdir(parents=True, exist_ok=True)
VP_PATH = SIM_DIR / "virtual_portfolio.json"
INITIAL_CASH = 100000


def load_vp():
    if VP_PATH.exists():
        return json.loads(VP_PATH.read_text("utf-8"))
    return {"created": TODAY, "initial_cash": INITIAL_CASH,
            "cash": INITIAL_CASH, "total_fees": 0,
            "holdings": {}, "pending": [], "history": [], "snapshots": []}

def save_vp(vp):
    VP_PATH.write_text(json.dumps(vp, ensure_ascii=False, indent=2), encoding="utf-8")


def fetch_today_trades(cookies):
    """从10个大佬抓取最新交易，合并到 trading_by_date"""
    fresh = {}
    for uid, name in list(FOLLOWED_USERS.items())[:10]:
        full = f"jimu_user_info-{uid}"
        try:
            r = get_trading_records(full, cookies=cookies, max_pages=2)
            for rec in r.get("records", []):
                detail = rec.get("detail", "")
                date = detail[:10] if detail and len(detail) >= 10 else TODAY
                fresh.setdefault(date, []).append({
                    "fund_name": rec.get("fund_name", ""),
                    "action": rec.get("action", ""),
                    "amount": rec.get("amount", ""),
                    "_user": name,
                })
        except Exception as e:
            print(f"  {name}: ERR {e}")
    return fresh


def run():
    print(f"=== 实盘模拟 {TODAY_CN} ===")
    cookies = _ensure_cookies(offline=True)
    if not cookies:
        cp = PROJECT / "data" / "jd_auth" / "cookies.json"
        if cp.exists(): cookies = json.loads(cp.read_text("utf-8"))
    if not cookies:
        print("[ERROR] 无 Cookie"); return

    valid, info = _verify_cookies(cookies)
    print(f"Cookie: {'有效' if valid else '无效'}")

    # 0. 自动扩展：扫描新基金加入清单（异步, 不阻塞）
    print("0. 扫描新基金...")
    from tools.fund_data_manager import expand_from_trading
    new_codes = expand_from_trading() or set()
    if new_codes:
        # 写入待抓清单 (后台)
        todo_file = PROJECT / "data" / "fund_charts_todo.json"
        existing_todo = set()
        if todo_file.exists():
            try: existing_todo = set(json.loads(todo_file.read_text("utf-8")))
            except: pass
        todo = existing_todo | new_codes
        todo_file.write_text(json.dumps(list(todo), ensure_ascii=False), "utf-8")
        print(f"   发现 {len(new_codes)} 只新基金, 待拉清单 {len(todo)} 只")
    else:
        print("   无新基金")

    # 0.5 重建排行预计算缓存 (供 /api/ranking 直接读, 不 spawn python)
    print("0.5 重建排行缓存...")
    from tools.build_ranking_cache import main as _build_ranking
    _build_ranking()
    # 0.6 重建评分预计算 (自选基金的 score)
    print("0.6 重建评分缓存...")
    from tools.build_score_cache import main as _build_score
    _build_score()

    # 1. 自选 + 大佬信号
    print("1. 数据...")"}
    wl = get_watchlist(cookies=cookies)
    if not wl or not wl.get("funds"):
        print("[ERROR] 自选列表为空"); return
    funds = {f["fund_code"]: f for f in wl["funds"]}
    print(f"   自选 {len(funds)} 只")

    fresh = fetch_today_trades(cookies)
    total_new = sum(len(v) for v in fresh.values())
    print(f"   大佬信号 {total_new} 笔 (今日)")
    # 合并到历史数据
    merged_trades = dict(trading_by_date)
    for d, items in fresh.items():
        merged_trades.setdefault(d, []).extend(items)
    # 为所有交易记录补 fund_code（和 run_backtest 一致）
    for d in merged_trades:
        for r in merged_trades[d]:
            if not r.get("fund_code") and r.get("fund_name", "") in name_map:
                r["fund_code"] = name_map[r["fund_name"]]

    # 2. 市场状态
    market = detect_market_state(TODAY, fund_charts)
    min_score = GENE.get(f"min_score_{market}", 3.0)
    print(f"2. 市场: {market} (门槛={min_score})")

    # 3. 组合状态
    vp = load_vp()
    portfolio = Portfolio(INITIAL_CASH)
    portfolio.set_fund_rules(fund_rules)
    portfolio._profiles = fund_profiles
    portfolio.slippage_pct = GENE.get("slippage_pct", 0.1)
    # 恢复之前的持仓
    for code, h in vp.get("holdings", {}).items():
        cb = h.get("cost_basis", 5000)
        portfolio.holdings[code] = {
            "name": h["name"], "shares": cb, "cost": cb,
            "buy_date": h.get("buy_date", TODAY), "buy_nav": 1.0,
        }
    portfolio.cash = vp.get("cash", INITIAL_CASH)
    portfolio.total_fees = vp.get("total_fees", 0)
    # 恢复待确认
    for pb in vp.get("pending", []):
        portfolio.pending_buys.append(pb)
    # 恢复冷却期记录
    portfolio.sell_history = vp.get("sell_history", {})

    # T+N 结算
    portfolio.settle_pending(TODAY)
    print(f"   持仓 {len(portfolio.holdings)} 只, 待确认 {len(portfolio.pending_buys)} 笔, 现金 {portfolio.cash:,.0f}")

    # 4. 评分
    print("3. 评分...")
    candidates = []
    for code, info in funds.items():
        name = info.get("fund_name", code)
        # RSI 超买
        pts = fund_charts.get(code, [])
        if len(pts) >= 60:
            timing = compute_entry_timing_score(pts, TODAY)
            if timing.get("should_warn"):
                print(f"   BLOCKED {name[:25]}: RSI超买")
                continue

        try:
            fs = score_fund_backtest(code, name, fund_charts, None,
                fund_rules.get(code), fund_managers.get(code),
                TODAY, merged_trades, fund_profiles.get(code))
            s = fs.total if hasattr(fs, 'total') else 3.0
        except:
            s = max(1.0, min(5.0, 3.0 + (info.get("month_return", 0) or 0) * 0.05))

        if s < min_score: continue
        candidates.append({"code": code, "name": name, "score": s})
        print(f"   {name[:30]} ({code}): {s:.1f}")

    candidates.sort(key=lambda x: -x["score"])

    # 5. 相关性过滤
    if len(portfolio.holdings) > 0 and len(candidates) > 0:
        held_codes = list(portfolio.holdings.keys()) + [c["code"] for c in candidates]
        corr = compute_correlation_matrix(fund_charts, held_codes, TODAY, lookback=60)
        filtered = []
        for c in candidates:
            add = True
            for hc in portfolio.holdings:
                if corr.get(c["code"], {}).get(hc, 0) > GENE.get("max_correlation", 0.85):
                    add = False
                    print(f"   FILTERED {c['name'][:25]}: 与持仓 {code_to_name.get(hc, hc)[:15]} 相关{corr[c['code']][hc]:.2f}")
                    break
            if add: filtered.append(c)
        candidates = filtered

    # 6. 卖出决策（回测引擎同款逻辑）
    print("4. 卖出检查...")
    sell_cooldown = {}
    for code in list(portfolio.holdings.keys()):
        h = portfolio.holdings[code]
        days = portfolio._holding_days(code, TODAY)
        if days < 60:
            continue  # 60天最低持有期（减少摩擦成本）

        # day_ret 从自选数据拿（动量崩溃需要实时涨跌幅）
        info = funds.get(code, {})
        day_ret = info.get("day_return") or 0

        # 用 chart 数据算真实盈亏
        pts = fund_charts.get(code, [])
        mv = h["cost"]  # 默认成本
        actual_pnl = 0
        if pts and len(pts) > 0:
            latest_yaxis = float(pts[-1].get("yAxis", 0))
            latest_nav = (100 + latest_yaxis) / 100
            buy_pts = [p for p in pts if p.get("xAxis", "")[:10] <= h.get("buy_date", TODAY)]
            if buy_pts:
                buy_yaxis = float(buy_pts[-1].get("yAxis", 0))
                buy_nav = (100 + buy_yaxis) / 100
                mv = h["cost"] * (latest_nav / buy_nav)
                actual_pnl = (mv - h["cost"]) / h["cost"] * 100

        # 止盈
        if actual_pnl >= GENE.get("take_profit_pct", 80):
            portfolio.sell(code, h["cost"], 1.0, TODAY, "take_profit", False)
            sell_cooldown[code] = {"date": TODAY, "reason": "take_profit", "nav": 1.0}
            print(f"   SELL_TP {h['name'][:25]}: +{actual_pnl:.0f}%")

        # 止损
        elif actual_pnl <= GENE.get("stop_loss_pct", -15):
            portfolio.sell(code, h["cost"], 1.0, TODAY, "stop_loss", True)
            sell_cooldown[code] = {"date": TODAY, "reason": "stop_loss", "nav": 1.0}
            print(f"   SELL_SL {h['name'][:25]}: {actual_pnl:.0f}%")

        # 动量崩溃（牛市不触发，减少假信号）
        elif day_ret < -8 and market != "bull":
            pts = fund_charts.get(code, [])
            if len(pts) >= 20:
                timing = compute_entry_timing_score(pts, TODAY)
                if timing.get("entry_score", 0) < 1.0:
                    portfolio.sell(code, h["cost"], 1.0, TODAY, "momentum_crash", True)
                    sell_cooldown[code] = {"date": TODAY, "reason": "momentum_crash", "nav": 1.0}
                    print(f"   SELL_MC {h['name'][:25]}: 动量崩塌")

    # 7. 买入决策
    print("5. 买入...")
    max_pos = GENE.get("max_position_pct", 20)
    cash_reserve = GENE.get("cash_reserve_pct", 0.1)
    cooldown_cfg = {"profit_days": GENE.get("cooldown_profit_days", 10),
                    "loss_days": GENE.get("cooldown_loss_days", 30)}

    # 冷却期检查
    active_codes = set()
    for code in candidates:
        if code in sell_cooldown:
            continue
        if portfolio.is_in_cooldown(code, TODAY, cooldown_cfg):
            print(f"   COOLED {code}: 冷却期未过")
            continue
        active_codes.add(code)

    for c in candidates:
        if c["code"] not in active_codes: continue
        if c["code"] in portfolio.holdings: continue
        if any(p["code"] == c["code"] for p in portfolio.pending_buys): continue

        available = portfolio.cash * (1 - cash_reserve)
        per_position = available * max_pos / 100
        # 动态仓位：用 kelly_cap 限制单笔上限
        kelly = GENE.get("kelly_cap", 0.4)
        amount = min(per_position, available * kelly)
        amount = round(amount / 100) * 100  # 取整
        if amount < 100:
            continue

        if portfolio.buy(c["code"], c["name"], amount, 1.0, TODAY):
            print(f"   BUY {c['name'][:30]}: {amount:,.0f} (评分{c['score']:.1f})")

    # 8. 同步回 VP（含市值盯市）
    vp["cash"] = portfolio.cash
    vp["total_fees"] = portfolio.total_fees

    # 计算持仓当前市值（基金累计收益 → 净值）
    holdings_market_value = 0
    vp_holdings = {}
    for code, h in portfolio.holdings.items():
        cb = h["cost"]
        mv = cb  # 默认按成本
        pts = fund_charts.get(code, [])
        if pts:
            latest_yaxis = float(pts[-1].get("yAxis", 0))
            latest_nav = (100 + latest_yaxis) / 100
            # 估算买入时净值
            buy_pts = [p for p in pts if p.get("xAxis", "")[:10] <= h.get("buy_date", TODAY)]
            if buy_pts:
                buy_yaxis = float(buy_pts[-1].get("yAxis", 0))
                buy_nav = (100 + buy_yaxis) / 100
                if buy_nav > 0:
                    mv = cb * (latest_nav / buy_nav)
        holdings_market_value += mv
        vp_holdings[code] = {
            "name": h["name"], "cost_basis": cb,
            "market_value": round(mv, 2),
            "buy_date": h.get("buy_date", TODAY), "buy_score": 3.0,
            "pnl_pct": round((mv - cb) / cb * 100, 2) if cb > 0 else 0,
        }
    vp["holdings"] = vp_holdings

    pending_value = sum(p.get("amount", 0) for p in portfolio.pending_buys)
    total_val = portfolio.cash + holdings_market_value + pending_value
    vp["snapshots"].append({"date": TODAY, "total_value": round(total_val, 2),
                            "cash": round(portfolio.cash, 2),
                            "holdings": len(portfolio.holdings),
                            "pending": len(portfolio.pending_buys)})
    vp["sell_history"] = portfolio.sell_history  # 持久化冷却期
    save_vp(vp)

    # 9. 日报
    print("6. 日报...")
    lines = [
        f"# 实盘模拟日报 {TODAY_CN}",
        f"",
        f"> 自选 {len(funds)} 只 | 大佬 {total_new} 笔 | 市场 {market} | 门槛 {min_score}",
        f"",
        f"## 组合状态",
        f"| 指标 | 值 |",
        f"|------|------|",
        f"| 总资产 | {total_val:,.2f} |",
        f"| 现金 | {portfolio.cash:,.2f} |",
        f"| 持仓 | {len(portfolio.holdings)} 只 |",
        f"| 待确认 | {len(portfolio.pending_buys)} 笔 |",
        f"| 手续费 | {portfolio.total_fees:,.2f} |",
        f"| 收益率 | {((total_val-INITIAL_CASH)/INITIAL_CASH*100):+.2f}% |",
        f"",
        f"## 评分 TOP 5",
        f"| 基金 | 评分 |",
        f"|------|------|",
    ]
    for c in candidates[:5]:
        lines.append(f"| {c['name']} ({c['code']}) | {c['score']:.1f} |")

    if portfolio.holdings:
        lines += ["", "## 当前持仓", "", "| 基金 | 成本 | 市值 | 盈亏 | 买入日期 |", "|------|------|------|------|----------|"]
        for code, h in portfolio.holdings.items():
            vh = vp["holdings"].get(code, {})
            pnl_str = f"{vh.get('pnl_pct',0):+.1f}%" if vh.get('pnl_pct') is not None else "N/A"
            mv_str = f"{vh.get('market_value',h['cost']):,.0f}"
            lines.append(f"| {h['name']} ({code}) | {h['cost']:,.0f} | {mv_str} | {pnl_str} | {h.get('buy_date','?')} |")

    # AI 审计入口
    buy_codes = [a["code"] for a in today_actions if a["action"] == "BUY"]
    blocked_codes = [r["code"] for r in results if r.get("blocked")]
    lines += [
        "",
        "## AI 审计入口",
        "",
        "在本地 IDE (Claude Code / OpenCode) 打开此文件，AI 会自动调用以下 SKILL：",
        "",
    ]
    if buy_codes:
        lines.append(f"### 买入前深度审计（今日候选 {len(buy_codes)} 只）")
        lines.append("")
        for code in buy_codes:
            lines.append(f"- `fund-checklist {code}` — 买入前六关 (能力圈/质量/经理/成本/流动性/聪明钱)")
            lines.append(f"- `fund-penetration {code}` — 穿透持仓看底层资产 (PE/PB/行业景气)")
        lines.append("")
    if blocked_codes:
        lines.append(f"### 风控拦截复查（{len(blocked_codes)} 只被系统拦截）")
        lines.append("")
        for code in blocked_codes:
            reason = next((r.get("reason","?") for r in results if r["code"]==code), "?")
            lines.append(f"- `fund-analyze {code}` — 复查: {reason}")
        lines.append("")
    if portfolio.holdings:
        held = list(portfolio.holdings.keys())
        lines.append(f"### 持仓卖出信号（{len(held)} 只在仓）")
        lines.append("")
        for code in held:
            lines.append(f"- `fund-sell {code}` — 大佬卖出信号/止盈止损/调仓成本")
        lines.append("")
    lines += [
        "### 通用 SKILL（随时可用）",
        "",
        "- `fund-monitor` — 大佬持仓 + 交易流水监控 (信号核心)",
        "- `fund-scan` — 全市场基金扫描（按多维度筛选）",
        "- `fund-compare {代码1,代码2}` — 基金对比",
        "- `portfolio-review` — 组合复盘",
        "",
        "### 数据状态",
        "",
        f"- 大佬交易数据: 截至 {TODAY}",
        f"- 行情数据: 截至 {TODAY} 收盘",
        f"- AI 机器报告: `reports/sim/{TODAY}.json` (结构化数据供 LLM 解析)",
        "",
        "---",
        f"*{TODAY_CN} 14:30 CST*",
    ]
    (SIM_DIR / f"{TODAY}.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"   日报已保存")

    # 保存 AI 可读的机器报告
    ai_report = {
        "date": TODAY,
        "market": market,
        "min_score": min_score,
        "candidates_top5": [{"code": c["code"], "name": c["name"], "score": c["score"]} for c in candidates[:5]],
        "buy_recommendations": [a for a in today_actions if a["action"] == "BUY"],
        "sell_recommendations": [a for a in today_actions if a["action"] == "SELL"],
        "blocked_funds": [{"code": r["code"], "name": r["name"], "reason": r.get("reason")} for r in results if r.get("blocked")],
        "holdings": {code: {"name": h["name"], "cost": h["cost"], "market_value": hv.get("market_value"), "pnl_pct": hv.get("pnl_pct")}
                     for code, h in portfolio.holdings.items() for hv in [vp_holdings.get(code, {})]},
        "portfolio": {"total_value": round(total_val, 2), "cash": round(portfolio.cash, 2), "fees": round(portfolio.total_fees, 2)},
    }
    (SIM_DIR / f"{TODAY}.json").write_text(json.dumps(ai_report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"   AI机器报告已保存: {TODAY}.json")

    print(f"\n=== 完成: 总资产 {total_val:,.0f} ({((total_val-INITIAL_CASH)/INITIAL_CASH*100):+.2f}%) ===")


if __name__ == "__main__":
    run()
