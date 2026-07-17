#!/usr/bin/env python3
"""每日实盘模拟 — 复用回测引擎全部风控逻辑

每天 14:30 由 GitHub Actions 自动运行。
组件：Portfolio(仓位/T+N/费率)、score_fund_backtest(五维+大佬)、
      detect_market_state、correlation_filter、行业估值
参数 = data/evolution/best_config.json
"""

import json, sys, os, glob, argparse
from datetime import datetime, timedelta
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))

# ── 参数解析 (支持 --simulate-date YYYY-MM-DD 模拟历史日跑) ──
_ap = argparse.ArgumentParser(add_help=False)
_ap.add_argument("--simulate-date", default=None, help="模拟指定日期跑 (格式 YYYY-MM-DD)")
_args, _ = _ap.parse_known_args()

if _args.simulate_date:
    _dt = datetime.strptime(_args.simulate_date, "%Y-%m-%d")
    print(f"[SIM] simulate-date={_args.simulate_date} (force TODAY to this date)")
else:
    _dt = datetime.now()

TODAY = _dt.strftime("%Y-%m-%d")
TODAY_CN = _dt.strftime("%Y年%m月%d日")

from tools.jd_finance_api import get_watchlist, get_trading_records, _ensure_cookies, _verify_cookies, FOLLOWED_USERS

# ── 回测引擎组件 ──
from backtest.engine.backtest import (
    Portfolio, score_fund_backtest, detect_market_state,
    compute_correlation_matrix,
)
from tools.technical_indicators import compute_entry_timing_score

# ── 冠军策略参数 (强制从 best_config.json 加载, 无 fallback) ──
EVO_PATH = PROJECT / "data" / "evolution" / "best_config.json"
if not EVO_PATH.exists():
    print("[FATAL] best_config.json 不存在, 无法运行实盘模拟")
    sys.exit(1)

evo = json.loads(EVO_PATH.read_text("utf-8"))
GENE = evo.get("config", evo.get("gene", {}))
# 确保关键参数存在 (gene字段是旧格式, config字段才是冠军V2完整配置)
if "take_profit_pct" not in GENE:
    GENE.update(evo.get("gene", {}))
print(f"[CONFIG] 冠军V2: 年化={evo.get('annualized',evo.get('performance',{}).get('total_return','?'))}%")
print(f"  take_profit={GENE.get('take_profit_pct')}% stop_loss={GENE.get('stop_loss_pct')}%")
print(f"  max_position={GENE.get('max_position_pct')}% kelly_cap={GENE.get('kelly_cap')}")
print(f"  pyramiding={GENE.get('pyramiding_enabled')} dyn_stop_loss={GENE.get('dynamic_stop_loss')}")
print(f"  fund_type_filter={GENE.get('fund_type_filter')} exclude_uids={len(GENE.get('exclude_uids',[]))}")

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
    """获取当日大佬交易信号

    实时模式: 从10个大佬的 JD API 抓最新交易
    simulate 模式: 从 trading_by_date_fixed.json 取历史数据 (避免网络请求)
    """
    if _args.simulate_date:
        # simulate 模式: 从历史数据中提取当天的信号
        fresh = {}
        tp = PROJECT / "backtest" / "data" / "trading_by_date_fixed.json"
        if tp.exists():
            try:
                hist = json.loads(tp.read_text("utf-8"))
                day_recs = hist.get(TODAY, [])
                for rec in day_recs:
                    fresh.setdefault(TODAY, []).append({
                        "fund_name": rec.get("fund_name", ""),
                        "action": rec.get("action", ""),
                        "amount": rec.get("amount", ""),
                        "fund_code": rec.get("fund_code", ""),
                        "_user": rec.get("_user", "历史"),
                    })
            except Exception as e:
                print(f"  历史数据读取失败: {e}")
        return fresh

    # 实时模式: 从API拉取
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

    # simulate 模式跳过 cookie 验证 (避免真实网络)
    cookie_valid = True
    if not _args.simulate_date:
        valid, info = _verify_cookies(cookies)
        cookie_valid = valid
        print(f"Cookie: {'有效' if valid else '无效'}")
        if not valid:
            print("[WARN] Cookie 已过期!")
            # 飞书告警
            try:
                from tools.feishu_push import push_text
                push_text("⚠ Cookie 过期", f"京东金融 Cookie 已失效\n请重新登录 https://jdjr.jd.com/\n时间: {TODAY_CN}\n{info}")
            except Exception as e:
                print(f"  飞书告警失败: {e}")
    else:
        print("Cookie: 跳过验证 (simulate 模式)")

    # 0. 自动扩展：扫描新基金加入清单（异步, 不阻塞）
    print("0. 扫描新基金...")
    new_codes = set()
    if not _args.simulate_date:
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
    # 0.6 重建评分预计算 (自选基金的 score)
    # simulate 模式跳过 (用昨日缓存即可, 跑历史日不会改变实时数据)
    if not _args.simulate_date:
        print("0.5 重建排行缓存...")
        from tools.build_ranking_cache import main as _build_ranking
        _build_ranking()
        print("0.6 重建评分缓存...")
        from tools.build_score_cache import main as _build_score
        _build_score()
    else:
        print("0.5/0.6 跳过 (simulate 模式用缓存)")

    # 1. 自选 + 大佬信号
    print("1. 数据...")
    # simulate 模式: use_cache=True (避免重复抓, 用上次缓存)
    # 实时模式: use_cache=True (抓一次存盘供前端 /api/fund 读)
    wl = get_watchlist(cookies=cookies, use_cache=True)
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
    portfolio.slippage_pct = GENE.get("slippage_pct", 0.0)
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

    # 冠军配置: fund_type_filter + exclude_uids
    fund_type_filter = GENE.get("fund_type_filter", "")
    exclude_uids = set(GENE.get("exclude_uids", []))

    for code, info in funds.items():
        name = info.get("fund_name", code)

        # 排除噪音大佬
        if exclude_uids:
            # uid 排除在交易信号阶段生效, 此处跳过
            pass

        # 基金类型过滤 (active=只买主动型, 排除指数/ETF)
        if fund_type_filter == "active":
            ftype = info.get("fund_type", "")
            if ftype and "指数" in str(ftype):
                continue

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
            # 公告信号修正 (2026-07-12 接入, 经理变更/估值调整/合同修订)
            from backtest.engine.notice_signal import score_notice_signal
            notice = score_notice_signal(code, TODAY, name)
            notice_adj = notice.get("adjust", 0.0)
            if notice_adj != 0:
                s = max(0.5, min(5.0, s + notice_adj))
                ns = notice.get("signals", [])
                if ns:
                    print(f"   NOTICE {name[:20]}: {ns[0]} (adj={notice_adj})")
        except Exception:
            s = max(1.0, min(5.0, 3.0 + (info.get("month_return", 0) or 0) * 0.05))

        if s < min_score: continue
        candidates.append({"code": code, "name": name, "score": s})
        print(f"   {name[:30]} ({code}): {s:.1f}")

    candidates.sort(key=lambda x: -x["score"])

    # 5. 相关性过滤（max_correlation=0 表示不限制）
    _max_corr = GENE.get("max_correlation", 0)
    if _max_corr > 0 and len(portfolio.holdings) > 0 and len(candidates) > 0:
        held_codes = list(portfolio.holdings.keys()) + [c["code"] for c in candidates]
        corr = compute_correlation_matrix(fund_charts, held_codes, TODAY, lookback=60)
        filtered = []
        for c in candidates:
            add = True
            for hc in portfolio.holdings:
                if corr.get(c["code"], {}).get(hc, 0) > _max_corr:
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

        # 用 chart 数据算真实盈亏 (用 <=TODAY 的最近点, 避免未来函数)
        pts = fund_charts.get(code, [])
        mv = h["cost"]  # 默认成本
        actual_pnl = 0
        if pts and len(pts) > 0:
            today_pts = [p for p in pts if p.get("xAxis", "")[:10] <= TODAY]
            if today_pts:
                latest_yaxis = float(today_pts[-1].get("yAxis", 0))
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

        # 动态止损：浮盈>20%时从高点回撤15%止盈，浮盈>40%时回撤10%止盈
        elif GENE.get("dynamic_stop_loss") and actual_pnl > 20:
            # 计算从最高点回撤
            peak_nav = latest_nav
            if pts:
                hist_pts = [p for p in pts if p.get("xAxis", "")[:10] <= TODAY]
                if hist_pts:
                    peak_nav = max((100 + float(p.get("yAxis", 0))) / 100 for p in hist_pts)
            dd_from_peak = (latest_nav / peak_nav - 1) * 100 if peak_nav > 0 else 0
            if (actual_pnl > 40 and dd_from_peak < -10) or dd_from_peak < -15:
                portfolio.sell(code, h["cost"], 1.0, TODAY, "dyn_stop_loss", False)
                sell_cooldown[code] = {"date": TODAY, "reason": "dyn_stop_loss", "nav": 1.0}
                print(f"   SELL_DSL {h['name'][:25]}: profit={actual_pnl:.0f}% dd={dd_from_peak:.1f}%")

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
    for c in candidates:
        code = c["code"] if isinstance(c, dict) else c
        if code in sell_cooldown:
            continue
        if portfolio.is_in_cooldown(code, TODAY, cooldown_cfg):
            print(f"   COOLED {code}: 冷却期未过")
            continue
        active_codes.add(code)

    for c in candidates:
        if c["code"] not in active_codes: continue
        # 金字塔补仓：已持仓 + 浮亏5-15% + 大佬信号持续 → 加仓
        if c["code"] in portfolio.holdings:
            if not GENE.get("pyramiding_enabled"):
                continue
            h = portfolio.holdings[c["code"]]
            pts = fund_charts.get(c["code"], [])
            current_nav = 1.0
            buy_nav = h.get("buy_nav", 1.0)
            if pts:
                valid = [p for p in pts if p.get("xAxis", "")[:10] <= TODAY]
                if valid:
                    current_nav = (100 + float(valid[-1].get("yAxis", 0))) / 100
            loss_pct = (current_nav / buy_nav - 1) * 100 if buy_nav > 0 else 0
            if loss_pct > -5 or loss_pct < -15:
                continue
            pyramid_mult = 0.5 if loss_pct > -10 else 0.3
            available = portfolio.cash * (1 - cash_reserve)
            amount = round(available * kelly * pyramid_mult / 100) * 100
            if amount >= 100 and portfolio.buy(c["code"], c["name"], amount, current_nav, TODAY):
                print(f"   PYRAMID {c['name'][:25]}: loss={loss_pct:.1f}% mult={pyramid_mult} amt={amount:.0f}")
            continue
        if any(p["code"] == c["code"] for p in portfolio.pending_buys): continue

        available = portfolio.cash * (1 - cash_reserve)
        per_position = available * max_pos / 100
        # 动态仓位：用 kelly_cap 限制单笔上限
        kelly = GENE.get("kelly_cap", 0.2)
        amount = min(per_position, available * kelly)
        amount = round(amount / 100) * 100  # 取整
        if amount < 100:
            continue

        # 用实际净值买入 (不是 1.0)
        buy_price = 1.0
        pts = fund_charts.get(c["code"], [])
        if pts:
            valid = [p for p in pts if p.get("xAxis", "")[:10] <= TODAY]
            if valid:
                buy_price = (100 + float(valid[-1].get("yAxis", 0))) / 100

        if portfolio.buy(c["code"], c["name"], amount, buy_price, TODAY):
            print(f"   BUY {c['name'][:30]}: {amount:,.0f} @{buy_price:.4f} (评分{c['score']:.1f})")

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
            # 用 <=TODAY 的最近点 (避免未来函数)
            today_pts = [p for p in pts if p.get("xAxis", "")[:10] <= TODAY]
            if today_pts:
                latest_yaxis = float(today_pts[-1].get("yAxis", 0))
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
    vp["pending"] = list(portfolio.pending_buys)  # 持久化待确认（T+N 关键）
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

    # 构造 AI 审计需要的数据 (必须在 if 外, 否则空仓时 NameError)
    # 从 portfolio.trades 拿今日实际 buy 调用 (而非 pending/确认后)
    today_actions = []
    for tr in portfolio.trades:
        if tr.get("date") == TODAY and tr.get("action") == "buy":
            code = tr.get("code", "")
            # 找名称
            name = ""
            for c in candidates:
                if c.get("code") == code:
                    name = c.get("name", code)
                    break
            if not name:
                for pc, ph in portfolio.holdings.items():
                    if pc == code:
                        name = ph.get("name", code)
                        break
            if not name and code in funds:
                name = funds[code].get("fund_name", code)
            today_actions.append({"action": "BUY", "code": code, "name": name,
                                  "amount": tr.get("amount", 0)})
    # 兼容旧逻辑: 兜底用 holdings + pending
    if not today_actions:
        for code, h in portfolio.holdings.items():
            if h.get('buy_date') == TODAY:
                today_actions.append({"action": "BUY", "code": code, "name": h['name'], "amount": h['cost']})
        for p in portfolio.pending_buys:
            today_actions.append({"action": "BUY", "code": p.get('code', ''), "name": p.get('name', ''), "amount": p.get('amount', 0)})
    sell_actions = [a for a in today_actions if a.get('action') == 'SELL']
    # 找 BLOCKED 的 (从评分过程结果)
    blocked_set = set()
    for line in []:  # 日志里没存 blocked list, 改从 candidates 提取
        if line: pass
    # 实际 blocked 不在 candidates (candidates 是过滤后的, blocked 在更早被排除)
    # 看评分时的输出日志难以解析, 直接从 candidates 里找 score < min_score 的或 has block_reason 字段
    results = []
    for c in candidates:
        if c.get('block_reason'):
            results.append({"code": c['code'], "name": c['name'], "blocked": True, "reason": c['block_reason']})

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
    # 加载 fund_notices (反未来函数: 只取 <=TODAY 的公告)
    notices_for_ai = {}
    if today_actions:
        try:
            from tools.jd_finance_api import get_fund_notices
            for action in today_actions:
                if action.get("action") != "BUY":
                    continue
                code = action.get("code", "")
                if not code or code in notices_for_ai:
                    continue
                cache_path = CACHE / f"fund_notices_{code}.json"
                if cache_path.exists():
                    import time
                    try:
                        data = json.loads(cache_path.read_text(encoding="utf-8"))
                        recent = [n for n in data.get("notices", [])
                                  if n.get("date", "")[:10] <= TODAY]
                        if recent:
                            notices_for_ai[code] = recent[:3]  # 最近 3 条
                    except Exception:
                        pass
        except Exception as e:
            print(f"   notices 加载跳过: {e}")

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
        "fund_notices": notices_for_ai,  # 反未来函数: 只含 <=TODAY 的公告
        "portfolio": {"total_value": round(total_val, 2), "cash": round(portfolio.cash, 2), "fees": round(portfolio.total_fees, 2)},
    }
    (SIM_DIR / f"{TODAY}.json").write_text(json.dumps(ai_report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"   AI机器报告已保存: {TODAY}.json")

    print(f"\n=== 完成: 总资产 {total_val:,.0f} ({((total_val-INITIAL_CASH)/INITIAL_CASH*100):+.2f}%) ===")

    # 10. 推送飞书日报 (仅当天推送, 历史回放不推)
    real_today = datetime.now().strftime("%Y-%m-%d")
    if TODAY == real_today:
        # 本周/本月交易汇总
        week_buys = week_sells = week_buy_amt = 0
        for t in portfolio.trades:
            td = t.get("date", "")
            if td >= (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d"):
                if t.get("action") == "buy":
                    week_buys += 1; week_buy_amt += t.get("amount", 0)
                elif t.get("action") == "sell":
                    week_sells += 1
        _push_feishu_daily(vp, portfolio, candidates, today_actions, total_val, market,
                          sell_cooldown, total_new, week_buys, week_sells, week_buy_amt)
    else:
        print(f"[FEISHU] 跳过 (历史回放 {TODAY} != 今天 {real_today})")
    return vp, portfolio


def _push_feishu_daily(vp, portfolio, candidates, today_actions, total_val, market,
                      sell_cooldown, total_new, week_buys, week_sells, week_buy_amt):
    """生成并推送飞书日报卡片 (A+C合并风格: 紧凑信息 + 进度条 + 操作日志)"""
    try:
        from tools.feishu_push import _get_token, _send_card
    except ImportError:
        print("[FEISHU] feishu_push 模块不可用, 跳过推送")
        return

    token = _get_token()
    if not token:
        print("[FEISHU] token 获取失败, 跳过推送")
        return

    # ── 计算各项指标 ──
    total_return = (total_val - INITIAL_CASH) / INITIAL_CASH * 100
    july1_val = INITIAL_CASH
    for snap in vp.get("snapshots", []):
        if snap.get("date", "") >= "2026-07-01":
            if july1_val == INITIAL_CASH:
                july1_val = snap.get("total_value", INITIAL_CASH)
    july1_return = (total_val - july1_val) / july1_val * 100 if july1_val > 0 else 0

    month_buys = month_sells = month_buy_amt = 0
    for t in portfolio.trades:
        if t.get("date", "")[:7] == TODAY[:7]:
            if t.get("action") == "buy":
                month_buys += 1; month_buy_amt += t.get("amount", 0)
            elif t.get("action") == "sell":
                month_sells += 1

    market_emoji = {"bull": "🐂 牛市", "neutral": "⚖️ 震荡", "bear": "🐻 熊市"}.get(market, market)

    # ── 生成进度条 ──
    def bar(pct, width=10):
        filled = max(0, min(width, int((pct + 20) / 40 * width) if pct > -100 else 0))
        return "█" * filled + "░" * max(0, width - filled)

    # ── 持仓列表 (带进度条+颜色) ──
    holding_rows = []
    for code, h in portfolio.holdings.items():
        vh = vp.get("holdings", {}).get(code, {})
        pnl = vh.get("pnl_pct", 0) or 0
        mv = vh.get("market_value", h.get("cost", 0))
        emoji = "🟢" if pnl > 5 else "🟡" if pnl > 0 else "🔴" if pnl < -5 else "🟠"
        b = bar(pnl)
        holding_rows.append(f"{emoji} {h['name'][:14]:<14s} {pnl:+5.1f}% {b} ¥{mv:,.0f}")
    holding_text = "\n".join(holding_rows) if holding_rows else "暂无持仓"

    # ── 今日操作列表 ──
    buy_ops = [a for a in today_actions if a.get("action") == "BUY"]
    sell_ops = [a for a in today_actions if a.get("action") == "SELL"]
    ops_lines = []
    if buy_ops or sell_ops:
        for a in buy_ops[:5]:
            ops_lines.append(f"🟢 买入 {a.get('name','')[:16]}  ¥{a.get('amount',0):,.0f}")
        for a in sell_ops[:5]:
            ops_lines.append(f"🔴 卖出 {a.get('name','')[:16]}")
    ops_text = "\n".join(ops_lines) if ops_lines else "今日无操作"

    # ── TOP3候选 ──
    top_lines = []
    for i, c in enumerate(candidates[:3]):
        star = "⭐" if c['score'] >= 3.0 else "◎" if c['score'] >= 2.0 else "○"
        top_lines.append(f"{i+1}. {star} {c['code']} {c['name'][:14]:<14s} {c['score']:.1f}分")
    top_text = "\n".join(top_lines) if top_lines else "无候选"

    # ── 风险提示 ──
    alerts = []
    if total_new == 0 and not _args.simulate_date:
        alerts.append("⚠️ 今日大佬无新交易信号")
    if july1_return < -3:
        alerts.append(f"🔻 7月回撤 {july1_return:.1f}%")
    if market == "bear":
        alerts.append("🐻 熊市 — 持仓防御为主")
    for code, info in list(sell_cooldown.items())[:2]:
        name = portfolio.holdings.get(code, {}).get("name", code)
        alerts.append(f"⏳ {name[:12]} 冷却期 ({info.get('reason','?')})")
    alert_text = "\n".join(alerts) if alerts else ""

    # ── 构建卡片 (A+C风格) ──
    elements = [
        # 标题区
        {"tag": "div", "text": {"tag": "lark_md",
            "content": f"**📊 {TODAY_CN}  {market_emoji}**\n总资产 **¥{total_val:,.0f}**  |  总收益 {total_return:+.2f}%"}},
        {"tag": "hr"},
        # 概览指标行
        {"tag": "div", "text": {"tag": "lark_md",
            "content": (f"7月至今 {july1_return:+.2f}%  |  "
                       f"现金 ¥{portfolio.cash:,.0f}  |  "
                       f"持仓 **{len(portfolio.holdings)}**只  |  "
                       f"信号 {total_new}笔\n"
                       f"本周 买{week_buys}笔(¥{week_buy_amt:,.0f}) 卖{week_sells}笔  |  "
                       f"本月 买{month_buys}笔(¥{month_buy_amt:,.0f}) 卖{month_sells}笔")}},
        {"tag": "hr"},
        # 今日操作
        {"tag": "div", "text": {"tag": "lark_md",
            "content": f"**📋 今日操作**\n{ops_text}"}},
        {"tag": "hr"},
        # 持仓列表 (带进度条)
        {"tag": "div", "text": {"tag": "lark_md",
            "content": f"**📂 持仓盈亏**\n{holding_text}"}},
        {"tag": "hr"},
        # TOP3
        {"tag": "div", "text": {"tag": "lark_md",
            "content": f"**⭐ 评分TOP3**\n{top_text}"}},
    ]

    # 风险提示
    if alert_text:
        elements.append({"tag": "hr"})
        elements.append({"tag": "div", "text": {"tag": "lark_md",
            "content": f"**🔔 提醒**\n{alert_text}"}})

    elements.append({"tag": "hr"})
    elements.append({"tag": "note", "elements": [
        {"tag": "plain_text", "content": f"AI Berkshire · 冠军策略(70.23%) · {TODAY_CN} · 仅供参考"}
    ]})

    card = {
        "header": {"title": {"tag": "plain_text", "content": f"🏆 AI Berkshire {TODAY}"}, "template": "blue"},
        "elements": elements,
    }

    _send_card(card)


if __name__ == "__main__":
    run()
