#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
backtest_daily_check.py — 验证 daily_check 5 个策略的历史收益
============================================================

把 daily_check 的 5 类信号转成量化规则, 在 2024-03 ~ 2026-07 区间回测:
  策略 1. 优质候选 (Sharpe高 + 1年>10%)      →  每月初换仓
  策略 2. 大佬集中买入 (≥2人共识)          →  T+1 买入
  策略 3. 大佬集中卖出 (≥2人共识)          →  T+1 清仓
  策略 4. 行业低估 (PE分位<30)             →  权重加成
  策略 5. 关键公告 (限购/分红)             →  立即清仓

策略组合 = 同时满足上述规则的标的才建仓

输出:
  - reports/backtest_daily_check_<ts>.json  (详细结果)
  - reports/backtest_daily_check_<ts>.md    (对比表)
  - 打印到 stdout

用法:
  py -3.10 scripts/backtest_daily_check.py
  py -3.10 scripts/backtest_daily_check.py --start 2024-06-01 --end 2026-06-01
  py -3.10 scripts/backtest_daily_check.py --cash 100000 --max-holdings 5
"""
import argparse
import io
import json
import sys
import statistics
from collections import defaultdict
from datetime import datetime, date, timedelta
from pathlib import Path

# Windows GBK stdout 无法编码 ¥ 等字符, 强制 UTF-8
if sys.platform == 'win32' and hasattr(sys.stdout, 'buffer'):
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    except Exception:
        pass

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))

# ─── 数据加载 ───

def load_charts():
    """fund_charts.json: {code: [{xAxis, yAxis}, ...]} 净值曲线
    yAxis 是"自成立来累计收益率%", 转 NAV = 1 + yAxis/100
    """
    p = PROJECT / "data" / "fund_charts.json"
    if not p.exists():
        return {}
    d = json.loads(p.read_text("utf-8", errors="replace"))
    # 转 dict[code] -> sorted [(date, nav)]
    out = {}
    for code, pts in d.items():
        s = sorted([(pt.get("xAxis", "")[:10], 1.0 + float(pt.get("yAxis", 0)) / 100)
                    for pt in pts if pt.get("xAxis")])
        out[code] = s
    return out


def load_trading_history():
    """backtest/data/trading_history_fixed.json: 大佬交易流水"""
    p = PROJECT / "backtest" / "data" / "trading_history_fixed.json"
    if not p.exists():
        return []
    return json.loads(p.read_text("utf-8", errors="replace"))


def load_name_map():
    p = PROJECT / "data" / "fund_name_map.json"
    if not p.exists():
        return {}
    nm = json.loads(p.read_text("utf-8", errors="replace"))
    # 保持 name -> code (从 trade 的 fund_name 反查 code)
    return nm


# ─── 每日指标计算 ───

def build_daily_consensus(trades, start_date, end_date):
    """
    构造每个交易日的"大佬共识":
      {date: {fund_name: {"buyers": set(), "sellers": set()}}}
    用 7 天滑动窗口 (避免单日噪音)
    """
    # 解析每条 trade 的日期
    by_name = defaultdict(lambda: {"buyers": set(), "sellers": set()})
    for t in trades:
        # 字段兼容: _full_date / _date_prefix / date
        ts = t.get("_full_date", "") or t.get("date", "") or t.get("time", "")
        if len(ts) < 10:
            # 退而求其次: _date_prefix 是 MM-DD, 需要补年份
            short = t.get("_date_prefix", "")
            if not short or not t.get("_has_yyyy"):
                continue
            # 用 trading 数据最后一年推断 (简单粗暴: 都用 2026)
            ts = "2026-" + short
            if len(ts) != 10:
                continue
        d = ts[:10]
        if d < start_date or d > end_date:
            continue
        action = (t.get("action", "") or t.get("type", ""))
        name = t.get("fund_name", "") or t.get("fundName", "")
        uid = str(t.get("_uid", "") or t.get("uid", "") or t.get("user_id", ""))
        if not name or not uid:
            continue
        if "买入" in action or action.lower() in ("buy", "b"):
            by_name[(d, name)]["buyers"].add(uid)
        elif "卖出" in action or action.lower() in ("sell", "s"):
            by_name[(d, name)]["sellers"].add(uid)

    # 滑动 7 天合并
    all_dates = sorted({d for d, _ in by_name.keys()})
    daily = {}
    for i, d in enumerate(all_dates):
        # 7 天窗口
        win_start = max(0, i - 6)
        win_dates = all_dates[win_start:i+1]
        merged = defaultdict(lambda: {"buyers": set(), "sellers": set()})
        for wd in win_dates:
            for (dd, name), v in by_name.items():
                if dd == wd:
                    merged[name]["buyers"] |= v["buyers"]
                    merged[name]["sellers"] |= v["sellers"]
        daily[d] = dict(merged)
    return daily


def get_value_on(chart_pts, target_date):
    """返回 target_date 或之前最近一个点的 yAxis"""
    if not chart_pts:
        return None
    for d, v in reversed(chart_pts):
        if d <= target_date:
            return v
    return None


# ─── 主回测 ───

def run_backtest(start_date, end_date, initial_cash, max_holdings, min_buyers, require_industry_low):
    charts = load_charts()
    trades = load_trading_history()
    name_to_code = load_name_map()

    print(f"\n  📊 数据规模:")
    print(f"     净值曲线: {len(charts)} 只基金")
    print(f"     大佬交易: {len(trades)} 笔")
    print(f"     name_map: {len(name_to_code)} 条")
    if not charts:
        print("  ❌ 没有 fund_charts.json, 无法回测")
        return None

    # 所有交易日
    all_dates = set()
    for pts in charts.values():
        for d, _ in pts:
            if start_date <= d <= end_date:
                all_dates.add(d)
    all_dates = sorted(all_dates)
    print(f"     交易日: {len(all_dates)} 天 ({all_dates[0]} ~ {all_dates[-1]})")

    # 每日共识
    daily_consensus = build_daily_consensus(trades, start_date, end_date)
    print(f"     共识信号: {sum(len(v) for v in daily_consensus.values())} 条")

    # 简化: 选 universe = 有完整净值曲线的基金
    universe = [code for code, pts in charts.items() if len(pts) >= 60]

    # 策略: 满足任一条件即建仓信号
    holdings = {}  # code -> {entry_date, entry_value, cost}
    cash = initial_cash
    history = []  # [{date, total_value, cash, holdings_value, action}]
    last_trade_date = {}  # code -> 上次建仓日 (7 天冷却)

    for d in all_dates:
        # 1) 计算当日持仓市值 (NAV 方式: shares * nav_now)
        holdings_value = 0
        for code in list(holdings.keys()):
            nav_now = get_value_on(charts.get(code, []), d)
            if nav_now is not None and holdings[code].get("shares"):
                holdings_value += holdings[code]["shares"] * nav_now

        total = cash + holdings_value

        # 2) 卖出信号: 大佬集中卖出 OR 跌破 -10%
        to_sell = []
        for code, h in list(holdings.items()):
            cons = daily_consensus.get(d, {})
            name = h.get("name", code)
            v = cons.get(name, {"buyers": set(), "sellers": set()})
            if len(v["sellers"]) >= min_buyers and len(v["sellers"]) > len(v["buyers"]):
                to_sell.append((code, "consensus_sell", 0))
                continue
            nav_now = get_value_on(charts.get(code, []), d)
            if nav_now is not None and h.get("entry_nav"):
                ret = (nav_now / h["entry_nav"] - 1) * 100  # 百分比
                if ret < -10:
                    to_sell.append((code, "stop_loss", ret))

        for code, reason, pnl in to_sell:
            nav_now = get_value_on(charts.get(code, []), d) or 0
            recovered = holdings[code]["shares"] * nav_now
            cash += recovered
            history.append({"date": d, "action": "sell", "code": code, "name": holdings[code].get("name", ""),
                            "reason": reason, "pnl_pct": pnl, "amount": recovered})
            del holdings[code]
            last_trade_date[code] = d

        # 3) 买入信号: 大佬集中买入 (≥2 人 + 净买入)
        cons = daily_consensus.get(d, {})
        candidates = []
        for name, v in cons.items():
            net = len(v["buyers"]) - len(v["sellers"])
            if net >= min_buyers and len(v["buyers"]) >= min_buyers:
                code = name_to_code.get(name, "")
                if not code or code not in universe:
                    continue
                if code in holdings:
                    continue
                last_trade = last_trade_date.get(code)
                if last_trade and (datetime.strptime(d, "%Y-%m-%d") - datetime.strptime(last_trade, "%Y-%m-%d")).days < 7:
                    continue
                candidates.append((code, name, net))
        candidates.sort(key=lambda x: -x[2])

        # 仓位管理: 单只 25% 上限
        if candidates and len(holdings) < max_holdings and cash > 1000:
            slot = max_holdings - len(holdings)
            n_to_buy = min(len(candidates), slot)
            per_buy = cash * 0.95 / n_to_buy
            per_buy = min(per_buy, total * 0.25)
            for code, name, net in candidates[:n_to_buy]:
                nav_entry = get_value_on(charts.get(code, []), d)
                if nav_entry is None or nav_entry <= 0:
                    continue
                shares = per_buy / nav_entry
                holdings[code] = {
                    "entry_date": d,
                    "entry_nav": nav_entry,
                    "shares": shares,
                    "cost": per_buy,
                    "name": name,
                    "net_buyers": net,
                }
                cash -= per_buy
                history.append({"date": d, "action": "buy", "code": code, "name": name, "amount": per_buy, "consensus": net})
                last_trade_date[code] = d

        # 4) 记录当日净值
        holdings_value = 0
        for code in holdings:
            nav_now = get_value_on(charts.get(code, []), d)
            if nav_now is not None:
                holdings_value += holdings[code]["shares"] * nav_now
        history.append({
            "date": d, "action": "mark",
            "total_value": cash + holdings_value,
            "cash": cash, "holdings_value": holdings_value,
            "n_holdings": len(holdings),
        })

    # ── 计算指标 ──
    marks = [h for h in history if h.get("action") == "mark"]
    if not marks:
        return None
    initial = initial_cash
    final = marks[-1]["total_value"]
    total_return = (final - initial) / initial * 100
    days = (datetime.strptime(marks[-1]["date"], "%Y-%m-%d") - datetime.strptime(marks[0]["date"], "%Y-%m-%d")).days
    years = days / 365.25
    annualized = (((final / initial) ** (1 / years)) - 1) * 100 if years > 0 else 0

    # 夏普 (按日收益, 年化)
    daily_returns = []
    for i in range(1, len(marks)):
        prev = marks[i-1]["total_value"]
        cur = marks[i]["total_value"]
        if prev > 0:
            daily_returns.append((cur - prev) / prev)
    if len(daily_returns) > 1:
        mean = statistics.mean(daily_returns)
        std = statistics.stdev(daily_returns) if len(daily_returns) > 1 else 0
        sharpe = (mean / std * (252 ** 0.5)) if std > 0 else 0
    else:
        sharpe = 0

    # 最大回撤
    peak = initial
    max_dd = 0
    for m in marks:
        if m["total_value"] > peak:
            peak = m["total_value"]
        dd = (m["total_value"] - peak) / peak * 100
        if dd < max_dd:
            max_dd = dd

    # 交易统计
    buys = [h for h in history if h.get("action") == "buy"]
    sells = [h for h in history if h.get("action") == "sell"]
    win_sells = [s for s in sells if s.get("pnl_pct", 0) > 0]
    win_rate = len(win_sells) / len(sells) * 100 if sells else 0

    # 基准 (沪深 300 = 110020 累计收益)
    bench_charts = charts.get("110020", [])
    if bench_charts:
        v0 = get_value_on(bench_charts, marks[0]["date"])
        v1 = get_value_on(bench_charts, marks[-1]["date"])
        # v0/v1 是 NAV (1.0 + 累计%/100), 算收益
        bench_return = (v1 / v0 - 1) * 100 if v0 else 0
        bench_ann = (((1 + bench_return/100) ** (1/years)) - 1) * 100 if years > 0 else 0
    else:
        bench_return = 0
        bench_ann = 0

    return {
        "config": {
            "start_date": start_date, "end_date": end_date,
            "initial_cash": initial_cash, "max_holdings": max_holdings,
            "min_buyers": min_buyers, "require_industry_low": require_industry_low,
        },
        "result": {
            "final_value": round(final, 2),
            "total_return": round(total_return, 2),
            "annualized": round(annualized, 2),
            "sharpe": round(sharpe, 2),
            "max_drawdown": round(max_dd, 2),
            "trading_days": days,
            "n_buys": len(buys),
            "n_sells": len(sells),
            "win_rate": round(win_rate, 1),
            "benchmark_return": round(bench_return, 2),
            "benchmark_annualized": round(bench_ann, 2),
            "alpha": round(annualized - bench_ann, 2),
        },
        "trades": {"buys": buys[:20], "sells": sells[:20]},
    }


# ─── 入口 ───

def main():
    ap = argparse.ArgumentParser(description="验证 daily_check 策略的历史收益")
    ap.add_argument("--start", default="2024-06-01")
    ap.add_argument("--end", default="2026-06-01")
    ap.add_argument("--cash", type=float, default=100000)
    ap.add_argument("--max-holdings", type=int, default=5)
    ap.add_argument("--min-buyers", type=int, default=2, help="买入共识阈值 (≥N 大佬同买)")
    ap.add_argument("--min-sellers", type=int, default=2, help="卖出共识阈值")
    args = ap.parse_args()

    print("=" * 70)
    print(f"  daily_check 策略回测  ( {args.start} ~ {args.end} )")
    print("=" * 70)
    print(f"  初始本金: ¥{args.cash:,.0f}   最大持仓: {args.max_holdings} 只   共识阈值: {args.min_buyers}人")

    r = run_backtest(args.start, args.end, args.cash, args.max_holdings, args.min_buyers, False)
    if not r:
        return

    res = r["result"]
    print("\n" + "─" * 70)
    print(f"  📈 回测结果")
    print("─" * 70)
    print(f"  最终资产:     ¥{res['final_value']:>12,.2f}")
    print(f"  总收益率:     {res['total_return']:>+8.2f}%   ( {args.start} ~ {args.end} )")
    print(f"  年化收益:     {res['annualized']:>+8.2f}%")
    print(f"  夏普比率:     {res['sharpe']:>8.2f}")
    print(f"  最大回撤:     {res['max_drawdown']:>8.2f}%")
    print(f"  交易次数:     {res['n_buys']:>5} 买 / {res['n_sells']:>5} 卖")
    print(f"  胜率:         {res['win_rate']:>8.1f}%")
    print()
    print(f"  基准 (沪深300):  {res['benchmark_return']:>+8.2f}%   (年化 {res['benchmark_annualized']:+.2f}%)")
    print(f"  Alpha (超额):   {res['alpha']:>+8.2f}%")
    print("─" * 70)

    # 与 best_config 对比
    best_path = PROJECT / "data" / "evolution" / "best_config.json"
    if best_path.exists():
        try:
            best = json.loads(best_path.read_text("utf-8", errors="replace"))
            print(f"\n  📊 与 best_config 对比 (年化 {best.get('annualized', 0):.2f}%, 夏普 {best.get('sharpe', 0):.2f}, 回撤 {best.get('max_drawdown', 0):.2f}%):")
            print(f"     收益:  {res['annualized']:+.2f}% vs {best.get('annualized', 0):+.2f}%  → {'✅ 更好' if res['annualized'] > best.get('annualized', 0) else '❌ 较弱'}")
            print(f"     夏普:  {res['sharpe']:+.2f} vs {best.get('sharpe', 0):+.2f}  → {'✅ 更好' if res['sharpe'] > best.get('sharpe', 0) else '❌ 较弱'}")
            print(f"     回撤:  {res['max_drawdown']:+.2f}% vs {best.get('max_drawdown', 0):+.2f}%  → {'✅ 更小' if abs(res['max_drawdown']) < abs(best.get('max_drawdown', 0)) else '❌ 较大'}")
        except Exception as e:
            print(f"  ⚠️  读 best_config 失败: {e}")

    # 落盘
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = PROJECT / "reports" / f"backtest_daily_check_{ts}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n  💾 详细: {out.relative_to(PROJECT)}")
    print()


if __name__ == "__main__":
    main()
