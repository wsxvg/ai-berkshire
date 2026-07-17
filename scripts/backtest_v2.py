#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
backtest_v2.py — daily_check V2 增强版回测
==============================================

P1. 止盈 (3 种 + 可开关)
  - 固定止盈: 收益 ≥ tp_pct (默认 20%) 全卖
  - 移动止盈: 自持仓创新高后回撤 ≥ trail_pct (默认 8%) 卖
  - 时间止盈: 持仓 ≥ hold_days (默认 60) 且收益 < 5% 卖

P2. 动态仓位 (按市场状态)
  - 牛市 (沪深300 MA60 斜率 > 0.05): 95% 仓位
  - 中性: 60%
  - 熊市 (斜率 < -0.05): 30%

P3. 5 维评分 (加分不阻挡)
  - 加载 data/cache/scores.json
  - score >= 4: 仓位翻倍 (50% 代替 25%)
  - score 2.5~4: 正常
  - score < 2.5: 仓位减半

P4. 训练/验证集拆分
  - 默认 2024-03-11 ~ 2026-03-11 训练
  - 2026-03-11 ~ 2026-07-01 验证 (前向测试, 防过拟合)

用法:
  py -3.10 scripts/backtest_v2.py                     # 全量 V2
  py -3.10 scripts/backtest_v2.py --no-tp            # 关止盈
  py -3.10 scripts/backtest_v2.py --no-dynamic       # 固定 95% 仓位
  py -3.10 scripts/backtest_v2.py --no-scorer        # 关闭 5 维评分
  py -3.10 scripts/backtest_v2.py --train-end 2026-03-11  # 训练/验证拆分
"""
import argparse
import io
import json
import sys
import statistics
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

# Windows GBK stdout 无法编码 ¥ 等字符, 强制 UTF-8 (兼容 Linux)
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
    p = PROJECT / "data" / "fund_charts.json"
    if not p.exists():
        return {}
    d = json.loads(p.read_text("utf-8", errors="replace"))
    out = {}
    for code, pts in d.items():
        s = sorted([(pt.get("xAxis", "")[:10], 1.0 + float(pt.get("yAxis", 0)) / 100)
                    for pt in pts if pt.get("xAxis")])
        out[code] = s
    return out


def load_trading_history():
    p = PROJECT / "backtest" / "data" / "trading_history_fixed.json"
    if not p.exists():
        return []
    return json.loads(p.read_text("utf-8", errors="replace"))


def load_name_map():
    p = PROJECT / "data" / "fund_name_map.json"
    if not p.exists():
        return {}
    return json.loads(p.read_text("utf-8", errors="replace"))


def load_scores():
    """data/cache/scores.json: 预计算 5 维评分 {code: {total, quality, cost, manager, momentum, smart_money}}"""
    p = PROJECT / "data" / "cache" / "scores.json"
    if not p.exists():
        return {}
    return json.loads(p.read_text("utf-8", errors="replace"))


def load_fund_cache():
    """加载 data/fund_cache/fund_data_*.json (profile/manager/rules)"""
    cache_dir = PROJECT / "data" / "fund_cache"
    if not cache_dir.exists():
        return {}
    out = {}
    import glob as _glob
    for p in _glob.glob(str(cache_dir / "fund_data_*.json")):
        try:
            d = json.loads(open(p, encoding="utf-8", errors="replace").read())
            code = d.get("fund_code", "") or Path(p).stem.replace("fund_data_", "")
            if code:
                out[code] = d
        except Exception:
            pass
    return out


# ─── 5 维评分 (按 cutoff_date 现场算, 修复前瞻偏差) ───

def _mgr_tenure_years_at(mgr, cutoff_date):
    """从 manager.accession_date 提取任职起始日, 算到 cutoff_date 的任职年限"""
    if not mgr:
        return None
    managers = mgr.get("managers", [])
    if not managers:
        return None
    accession = managers[0].get("accession_date", "")
    # 格式 "2019.01.30-至今" 或 "2019-01-30"
    import re
    m = re.search(r"(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})", str(accession))
    if not m:
        return None
    try:
        start = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        end = datetime.strptime(cutoff_date, "%Y-%m-%d")
        return max(0, (end - start).days / 365.25)
    except Exception:
        return None


def compute_score_at(code, cutoff_date, charts, fund_cache, trades_by_date, name_to_code):
    """按截止日现场算 5 维评分 (无前瞻偏差, 2026-07-13 修复版)

    Returns:
        {"total": float 0~25, "breakdown": {...}}
    """
    bd = {}
    score = 0.0

    # === 1. Quality (0~5): 1y 收益 + 1y 最大回撤 + 夏普 ===
    chart = charts.get(code, [])
    valid = [p for p in chart if p[0] <= cutoff_date]
    if len(valid) >= 250:
        ret_1y = valid[-1][1] - valid[-250][1]  # 1y 累计收益差 (yAxis 是 NAV 倍数)
        # 1y 收益得分 (0~2.5): 0% 收益 -> 1.25, 20% -> 2.5, 50% -> 2.5 (封顶)
        q_ret = min(2.5, max(0, 1.25 + ret_1y * 5))  # 1y +20% 收益 -> 2.5

        # 1y 最大回撤
        peak = max(p[1] for p in valid[-250:])
        dd = (valid[-1][1] - peak) / peak * 100 if peak > 0 else 0
        # dd=-5% -> 2.5, dd=-20% -> 0.5
        q_dd = max(0, min(2.5, 2.5 + dd * 0.1))
        score += q_ret + q_dd
        bd["q_ret_1y"] = round(ret_1y * 100, 2)
        bd["q_dd_1y"] = round(dd, 2)
    else:
        score += 2.0  # 数据不足给中性分
        bd["q_ret_1y"] = None

    # === 2. Cost (0~5): 管理费 ===
    cache = fund_cache.get(code, {})
    rules = cache.get("rules", {})
    mf = rules.get("manage_fee", 1.2) if rules else 1.2
    if mf <= 0: mf = 1.2
    if mf < 0.5: c = 5.0
    elif mf < 0.8: c = 4.0
    elif mf < 1.2: c = 3.0
    elif mf < 1.5: c = 2.0
    else: c = 1.0
    score += c
    bd["manage_fee"] = mf

    # === 3. Manager (0~5): 任职年限 (按 cutoff_date 算) ===
    mgr = cache.get("manager", {})
    tenure = _mgr_tenure_years_at(mgr, cutoff_date)
    if tenure is None:
        m_score = 2.5
    else:
        # 5 年满分: m_score = min(5, tenure * 1.0)
        m_score = min(5.0, tenure * 1.0)
    score += m_score
    bd["mgr_tenure_years"] = round(tenure, 2) if tenure is not None else None

    # === 4. Momentum (0~5): 60 日斜率 (按 cutoff) ===
    if len(valid) >= 60:
        recent = sum(p[1] for p in valid[-60:]) / 60
        if len(valid) >= 120:
            past = sum(p[1] for p in valid[-120:-60]) / 60
        else:
            past = recent
        slope_pct = (recent - past) / (past + 0.01) * 100  # 60日 vs 前60日, 百分比
        # slope=0 -> 2.5, slope=10% -> 5.0, slope=-10% -> 0.0
        mom = max(0, min(5.0, 2.5 + slope_pct * 0.25))
    else:
        mom = 2.5
    score += mom
    bd["slope_60d_pct"] = round(slope_pct, 2) if len(valid) >= 60 else None

    # === 5. Smart Money (0~5): 14 天内几位大佬买 ===
    try:
        from datetime import timedelta as _td
        cutoff_dt = datetime.strptime(cutoff_date, "%Y-%m-%d")
        lookback_start = (cutoff_dt - _td(days=14)).strftime("%Y-%m-%d")
    except Exception:
        lookback_start = cutoff_date
    sm_users = set()
    for d_key, recs in (trades_by_date or {}).items():
        if d_key < lookback_start or d_key > cutoff_date:
            continue
        for r in recs:
            name = r.get("fund_name", "") or r.get("fundName", "")
            action = r.get("action", "") or r.get("type", "")
            uid = str(r.get("_user", "") or r.get("uid", ""))
            # 按 name 找 code (因为 trades_by_date 是按 name 索引的)
            if name_to_code.get(name) == code and "买入" in action and uid:
                sm_users.add(uid)
    sm_score = min(5.0, len(sm_users) * 1.5)
    score += sm_score
    bd["sm_buyers_14d"] = len(sm_users)

    return {"total": round(score, 2), "breakdown": bd}


# ─── RSI 计算 (按截止日) ───

def compute_rsi_at(chart_pts, cutoff_date, period=14):
    """计算 cutoff_date 当天的 RSI(14), chart_pts 已按 (date, nav) 排序"""
    valid = [v for d, v in chart_pts if d <= cutoff_date]
    if len(valid) < period + 1:
        return 50.0  # 中性
    gains, losses = [], []
    for i in range(-period, 0):
        chg = valid[i] - valid[i - 1]
        if chg > 0: gains.append(chg)
        else: losses.append(abs(chg))
    avg_g = sum(gains) / period if gains else 0.0
    avg_l = sum(losses) / period if losses else 0.0
    if avg_l == 0.0 and avg_g == 0.0:
        return 50.0
    if avg_l == 0.0:
        return 100.0
    rs = avg_g / avg_l
    return 100 - 100 / (1 + rs)


# ─── 每日指标计算 ───

def build_daily_consensus(trades, start_date, end_date):
    by_name = defaultdict(lambda: {"buyers": set(), "sellers": set()})
    for t in trades:
        ts = t.get("_full_date", "") or t.get("date", "") or t.get("time", "")
        if len(ts) < 10:
            short = t.get("_date_prefix", "")
            if not short or not t.get("_has_yyyy"):
                continue
            ts = "2026-" + short
            if len(ts) != 10:
                continue
        d = ts[:10]
        if d < start_date or d > end_date:
            continue
        action = t.get("action", "") or t.get("type", "")
        name = t.get("fund_name", "") or t.get("fundName", "")
        uid = str(t.get("_uid", "") or t.get("uid", "") or t.get("user_id", ""))
        if not name or not uid:
            continue
        if "买入" in action or action.lower() in ("buy", "b"):
            by_name[(d, name)]["buyers"].add(uid)
        elif "卖出" in action or action.lower() in ("sell", "s"):
            by_name[(d, name)]["sellers"].add(uid)

    all_dates = sorted({d for d, _ in by_name.keys()})
    daily = {}
    for i, d in enumerate(all_dates):
        win_dates = all_dates[max(0, i - 6):i + 1]
        merged = defaultdict(lambda: {"buyers": set(), "sellers": set()})
        for wd in win_dates:
            for (dd, name), v in by_name.items():
                if dd == wd:
                    merged[name]["buyers"] |= v["buyers"]
                    merged[name]["sellers"] |= v["sellers"]
        daily[d] = dict(merged)
    return daily


def get_value_on(chart_pts, target_date):
    if not chart_pts:
        return None
    for d, v in reversed(chart_pts):
        if d <= target_date:
            return v
    return None


# ─── P2 辅助: 市场状态判断 (用沪深 300 = 110020 的 MA60 斜率) ───

def detect_market_state(charts, d):
    """返回 'bull' / 'neutral' / 'bear'"""
    bench = charts.get("110020", [])
    if not bench:
        return "neutral"
    # 取 d 之前 60 天的 NAV
    navs = [v for dd, v in bench if dd <= d][-60:]
    if len(navs) < 20:
        return "neutral"
    # 简单斜率: (尾-首) / 长度
    slope = (navs[-1] - navs[0]) / len(navs) / navs[0] if navs[0] > 0 else 0
    if slope > 0.0005:
        return "bull"
    elif slope < -0.0005:
        return "bear"
    return "neutral"


# ─── 主回测 ───

def run_backtest(
    start_date, end_date, initial_cash, max_holdings, min_buyers,
    use_tp=True, use_trail=True, use_time_tp=True,
    use_dynamic=True, use_scorer=True,
    tp_pct=15.0, trail_pct=8.0, hold_days=60,
    bull_ratio=0.95, neutral_ratio=0.70, bear_ratio=0.50,
    # === SKILL 维度 (2026-07-13 新增) ===
    use_rsi_filter=False, rsi_threshold=75,                 # B1
    use_concentration_filter=False, concentration_max=0.6,  # B2
    use_manager_filter=False, min_tenure_years=1.0,         # B3
    use_score_threshold=False, score_threshold=3.0,         # B4
    use_score_position=False,                               # B5
):
    charts = load_charts()
    trades = load_trading_history()
    name_to_code = load_name_map()
    scores = load_scores()
    fund_cache = load_fund_cache()

    # 交易按日聚合 (用于 compute_score_at 的 smart_money)
    from collections import defaultdict
    trades_by_date = defaultdict(list)
    for t in trades:
        ts = t.get("_full_date", "") or t.get("date", "") or t.get("time", "")
        if len(ts) < 10:
            short = t.get("_date_prefix", "")
            if short and t.get("_has_yyyy"):
                ts = "2026-" + short
        if len(ts) >= 10:
            trades_by_date[ts[:10]].append(t)

    if not charts:
        return None

    # 交易日
    all_dates = set()
    for pts in charts.values():
        for d, _ in pts:
            if start_date <= d <= end_date:
                all_dates.add(d)
    all_dates = sorted(all_dates)
    daily_consensus = build_daily_consensus(trades, start_date, end_date)
    universe = [code for code, pts in charts.items() if len(pts) >= 60]

    holdings = {}
    cash = initial_cash
    history = []
    last_trade_date = {}
    high_since_entry = {}  # code -> 持仓后最高 NAV (用于移动止盈)

    for d in all_dates:
        # 1) 持仓市值
        holdings_value = 0
        for code in list(holdings.keys()):
            nav_now = get_value_on(charts.get(code, []), d)
            if nav_now is not None and holdings[code].get("shares"):
                holdings_value += holdings[code]["shares"] * nav_now
                # 更新持仓期最高
                if nav_now > high_since_entry.get(code, 0):
                    high_since_entry[code] = nav_now
        total = cash + holdings_value

        # 2) 卖出信号 (优先级: 大佬共识 > 移动止盈 > 固定止盈 > 时间止盈 > 止损)
        to_sell = []
        for code, h in list(holdings.items()):
            name = h.get("name", code)
            cons = daily_consensus.get(d, {})
            v = cons.get(name, {"buyers": set(), "sellers": set()})
            # 大佬集中卖出
            if len(v["sellers"]) >= min_buyers and len(v["sellers"]) > len(v["buyers"]):
                to_sell.append((code, "consensus_sell", 0))
                continue
            nav_now = get_value_on(charts.get(code, []), d)
            if nav_now is None or not h.get("entry_nav"):
                continue
            ret = (nav_now / h["entry_nav"] - 1) * 100
            # P1: 移动止盈
            if use_trail:
                high = high_since_entry.get(code, h["entry_nav"])
                trail_ret = (high - nav_now) / h["entry_nav"] * 100
                # 创新高 5% 后才激活
                if (high / h["entry_nav"] - 1) * 100 >= 5 and trail_ret >= trail_pct:
                    to_sell.append((code, "trail_stop", ret))
                    continue
            # P1: 固定止盈
            if use_tp and ret >= tp_pct:
                to_sell.append((code, "take_profit", ret))
                continue
            # P1: 时间止盈
            if use_time_tp and h.get("entry_date"):
                try:
                    days_held = (datetime.strptime(d, "%Y-%m-%d") -
                                 datetime.strptime(h["entry_date"], "%Y-%m-%d")).days
                    if days_held >= hold_days and ret < 5:
                        to_sell.append((code, "time_tp", ret))
                        continue
                except Exception:
                    pass
            # 止损
            if ret < -10:
                to_sell.append((code, "stop_loss", ret))
                continue

        for code, reason, pnl in to_sell:
            nav_now = get_value_on(charts.get(code, []), d) or 0
            recovered = holdings[code]["shares"] * nav_now
            cash += recovered
            history.append({"date": d, "action": "sell", "code": code,
                            "name": holdings[code].get("name", ""),
                            "reason": reason, "pnl_pct": pnl, "amount": recovered})
            del holdings[code]
            high_since_entry.pop(code, None)
            last_trade_date[code] = d

        # 3) 买入信号
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
                last = last_trade_date.get(code)
                if last and (datetime.strptime(d, "%Y-%m-%d") -
                             datetime.strptime(last, "%Y-%m-%d")).days < 7:
                    continue
                candidates.append((code, name, net))
        candidates.sort(key=lambda x: -x[2])

        # === SKILL: candidate 过滤 (B1/B3/B4) ===
        filtered = []
        for code, name, net in candidates:
            # B1: RSI 拦截 (避免追高)
            if use_rsi_filter:
                rsi = compute_rsi_at(charts.get(code, []), d)
                if rsi > rsi_threshold:
                    continue
            # B3: 经理筛选 (经理任职<1年不买)
            if use_manager_filter:
                mgr = fund_cache.get(code, {}).get("manager", {})
                tenure = _mgr_tenure_years_at(mgr, d)
                if tenure is not None and tenure < min_tenure_years:
                    continue
            # B4: 5 维评分门槛 (按 cutoff_date 算, 修复前瞻偏差)
            if use_score_threshold:
                sc = compute_score_at(code, d, charts, fund_cache, trades_by_date, name_to_code)
                if sc["total"] < score_threshold:
                    continue
            filtered.append((code, name, net))
        candidates = filtered

        # P2: 动态仓位
        if use_dynamic:
            market = detect_market_state(charts, d)
            ratio = {"bull": bull_ratio, "neutral": neutral_ratio, "bear": bear_ratio}[market]
        else:
            ratio = 0.95
            market = "fixed"

        if candidates and len(holdings) < max_holdings and cash > 1000:
            slot = max_holdings - len(holdings)
            n_to_buy = min(len(candidates), slot)
            for code, name, net in candidates[:n_to_buy]:
                nav_entry = get_value_on(charts.get(code, []), d)
                if nav_entry is None or nav_entry <= 0:
                    continue

                # === P3: 5 维评分影响初始仓位 ===
                per_buy_ratio = 0.25  # 默认
                if use_scorer:
                    sc = scores.get(code, {}).get("total", 0) if scores else 0
                    if sc >= 3.5:
                        per_buy_ratio = 0.30
                    elif sc >= 2.5:
                        per_buy_ratio = 0.25
                    else:
                        per_buy_ratio = 0.15
                if use_score_position:
                    # B5: 评分仓位调节 (按 cutoff_date 算)
                    sc_now = compute_score_at(code, d, charts, fund_cache, trades_by_date, name_to_code)
                    # score 5~25, 映射到 0.15~0.40
                    # total=12.5 (中性) -> 0.25; total=25 (满分) -> 0.40; total=5 (差) -> 0.10
                    per_buy_ratio = max(0.10, min(0.40, 0.10 + (sc_now["total"] - 5) * 0.02))

                per_buy = cash * ratio / n_to_buy
                per_buy = min(per_buy, total * per_buy_ratio)
                if per_buy < 1000:
                    continue

                shares = per_buy / nav_entry
                holdings[code] = {
                    "entry_date": d, "entry_nav": nav_entry,
                    "shares": shares, "cost": per_buy, "name": name,
                    "net_buyers": net, "market_at_entry": market,
                }
                cash -= per_buy
                high_since_entry[code] = nav_entry
                # 记录买入时的 score
                score_at_buy = None
                if use_scorer and scores:
                    score_at_buy = scores.get(code, {}).get("total", 0)
                if use_score_position or use_score_threshold:
                    score_at_buy = compute_score_at(code, d, charts, fund_cache, trades_by_date, name_to_code)["total"]
                history.append({"date": d, "action": "buy", "code": code, "name": name,
                                "amount": per_buy, "consensus": net, "market": market,
                                "score": score_at_buy or 0})
                last_trade_date[code] = d

                # === B2: 集中度过滤 (买入后, 检查持仓组合集中度) ===
                # 简化: 持仓中如果某行业占>60%, 减仓这只
                if use_concentration_filter:
                    this_holdings = fund_cache.get(code, {}).get("holdings", {})
                    if this_holdings and isinstance(this_holdings, dict):
                        sectors = this_holdings.get("sectors", [])
                        if sectors and isinstance(sectors, list):
                            # 找最大行业占比
                            top_pct = max((s.get("weight", 0) for s in sectors if isinstance(s, dict)), default=0)
                            if top_pct > concentration_max:
                                # 减仓 50%
                                holdings[code]["shares"] *= 0.5
                                cash += per_buy * 0.5

        # 4) 记录当日
        holdings_value = 0
        for code in holdings:
            v = get_value_on(charts.get(code, []), d)
            if v is not None:
                holdings_value += holdings[code]["shares"] * v
        history.append({
            "date": d, "action": "mark",
            "total_value": cash + holdings_value,
            "cash": cash, "holdings_value": holdings_value,
            "n_holdings": len(holdings),
            "market": market if 'market' in dir() else "neutral",
        })

    # ── 指标 ──
    return calc_metrics(history, initial_cash, charts, start_date, end_date, locals())


def calc_metrics(history, initial, charts, start_date, end_date, cfg):
    marks = [h for h in history if h.get("action") == "mark"]
    if not marks:
        return None
    final = marks[-1]["total_value"]
    total_return = (final - initial) / initial * 100
    days = (datetime.strptime(marks[-1]["date"], "%Y-%m-%d") -
            datetime.strptime(marks[0]["date"], "%Y-%m-%d")).days
    years = days / 365.25
    annualized = (((final / initial) ** (1 / years)) - 1) * 100 if years > 0 else 0

    daily_returns = []
    for i in range(1, len(marks)):
        prev = marks[i - 1]["total_value"]
        cur = marks[i]["total_value"]
        if prev > 0:
            daily_returns.append((cur - prev) / prev)
    if len(daily_returns) > 1:
        mean = statistics.mean(daily_returns)
        std = statistics.stdev(daily_returns) if len(daily_returns) > 1 else 0
        sharpe = (mean / std * (252 ** 0.5)) if std > 0 else 0
    else:
        sharpe = 0

    peak = initial
    max_dd = 0
    for m in marks:
        if m["total_value"] > peak:
            peak = m["total_value"]
        dd = (m["total_value"] - peak) / peak * 100
        if dd < max_dd:
            max_dd = dd

    buys = [h for h in history if h.get("action") == "buy"]
    sells = [h for h in history if h.get("action") == "sell"]
    win_sells = [s for s in sells if s.get("pnl_pct", 0) > 0]
    win_rate = len(win_sells) / len(sells) * 100 if sells else 0

    # 卖出原因统计
    reason_stats = defaultdict(lambda: {"count": 0, "total_pnl": 0})
    for s in sells:
        reason_stats[s.get("reason", "unknown")]["count"] += 1
        reason_stats[s.get("reason", "unknown")]["total_pnl"] += s.get("pnl_pct", 0)

    bench_charts = charts.get("110020", [])
    if bench_charts:
        v0 = get_value_on(bench_charts, marks[0]["date"])
        v1 = get_value_on(bench_charts, marks[-1]["date"])
        bench_return = (v1 / v0 - 1) * 100 if v0 else 0
        bench_ann = (((1 + bench_return / 100) ** (1 / years)) - 1) * 100 if years > 0 else 0
    else:
        bench_return = 0
        bench_ann = 0

    return {
        "config": {
            "start": start_date, "end": end_date,
            "use_tp": cfg.get("use_tp"), "use_trail": cfg.get("use_trail"),
            "use_time_tp": cfg.get("use_time_tp"),
            "use_dynamic": cfg.get("use_dynamic"),
            "use_scorer": cfg.get("use_scorer"),
            "tp_pct": cfg.get("tp_pct"), "trail_pct": cfg.get("trail_pct"),
            "hold_days": cfg.get("hold_days"),
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
        "reason_stats": {k: {"count": v["count"], "avg_pnl": round(v["total_pnl"] / v["count"], 2)}
                          for k, v in reason_stats.items()},
        "trades": {"buys": buys[:30], "sells": sells[:30]},
    }


# ─── 入口 ───

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2024-03-11")
    ap.add_argument("--end", default="2026-07-01")
    ap.add_argument("--cash", type=float, default=100000)
    ap.add_argument("--max-holdings", type=int, default=5)
    ap.add_argument("--min-buyers", type=int, default=1)
    ap.add_argument("--no-tp", action="store_true")
    ap.add_argument("--no-trail", action="store_true")
    ap.add_argument("--no-time-tp", action="store_true")
    ap.add_argument("--no-dynamic", action="store_true")
    ap.add_argument("--no-scorer", action="store_true")
    ap.add_argument("--train-end", default=None,
                    help="训练/验证集拆分日 (e.g. 2026-03-11)")
    ap.add_argument("--tp-pct", type=float, default=15.0)
    ap.add_argument("--trail-pct", type=float, default=10.0)
    ap.add_argument("--hold-days", type=int, default=30)
    args = ap.parse_args()

    print("=" * 72)
    print(f"  daily_check V2 增强版回测  ( {args.start} ~ {args.end} )")
    print("=" * 72)
    flags = []
    flags.append("固定止盈" if not args.no_tp else "X固定止盈")
    flags.append("移动止盈" if not args.no_trail else "X移动止盈")
    flags.append("时间止盈" if not args.no_time_tp else "X时间止盈")
    flags.append("动态仓位" if not args.no_dynamic else "X动态仓位")
    flags.append("5维评分" if not args.no_scorer else "X5维评分")
    print(f"  开关: {' | '.join(flags)}")
    print(f"  参数: max_holdings={args.max_holdings} min_buyers={args.min_buyers} "
          f"tp={args.tp_pct}% trail={args.trail_pct}% hold={args.hold_days}d")
    print()

    r = run_backtest(
        args.start, args.end, args.cash, args.max_holdings, args.min_buyers,
        use_tp=not args.no_tp, use_trail=not args.no_trail,
        use_time_tp=not args.no_time_tp,
        use_dynamic=not args.no_dynamic, use_scorer=not args.no_scorer,
        tp_pct=args.tp_pct, trail_pct=args.trail_pct, hold_days=args.hold_days,
    )
    if not r:
        print("❌ 无结果")
        return
    print_result(r, prefix="  ")
    save_result(r, "v2_full")

    # P4: 训练/验证集拆分
    if args.train_end:
        print("\n" + "=" * 72)
        print(f"  P4 训练/验证集拆分: 训练 {args.start} ~ {args.train_end}  |  验证 {args.train_end} ~ {args.end}")
        print("=" * 72)
        # 训练集
        print("\n  📚 训练集:")
        r_train = run_backtest(
            args.start, args.train_end, args.cash, args.max_holdings, args.min_buyers,
            use_tp=not args.no_tp, use_trail=not args.no_trail,
            use_time_tp=not args.no_time_tp,
            use_dynamic=not args.no_dynamic, use_scorer=not args.no_scorer,
            tp_pct=args.tp_pct, trail_pct=args.trail_pct, hold_days=args.hold_days,
        )
        if r_train:
            print_result(r_train, prefix="    ")
            save_result(r_train, "v2_train")
        # 验证集 (前向)
        print("\n  🔬 验证集 (前向, 防过拟合):")
        r_val = run_backtest(
            args.train_end, args.end, args.cash, args.max_holdings, args.min_buyers,
            use_tp=not args.no_tp, use_trail=not args.no_trail,
            use_time_tp=not args.no_time_tp,
            use_dynamic=not args.no_dynamic, use_scorer=not args.no_scorer,
            tp_pct=args.tp_pct, trail_pct=args.trail_pct, hold_days=args.hold_days,
        )
        if r_val:
            print_result(r_val, prefix="    ")
            save_result(r_val, "v2_val")
        # 退化检查
        if r_train and r_val:
            ann_train = r_train["result"]["annualized"]
            ann_val = r_val["result"]["annualized"]
            sharpe_train = r_train["result"]["sharpe"]
            sharpe_val = r_val["result"]["sharpe"]
            print(f"\n  ⚠️  过拟合检查:")
            print(f"     训练年化: {ann_train:+.2f}%  验证年化: {ann_val:+.2f}%  "
                  f"差异: {ann_val - ann_train:+.2f}%")
            print(f"     训练夏普: {sharpe_train:.2f}  验证夏普: {sharpe_val:.2f}  "
                  f"差异: {sharpe_val - sharpe_train:+.2f}")
            if ann_val < ann_train * 0.3:
                print(f"     🔴 严重过拟合! 验证集收益 < 训练集 30%")
            elif ann_val < ann_train * 0.6:
                print(f"     ⚠️  轻度过拟合")
            else:
                print(f"     ✅ 策略稳健")


def print_result(r, prefix=""):
    res = r["result"]
    print(f"{prefix}最终:    ¥{res['final_value']:>12,.0f}")
    print(f"{prefix}总收益:  {res['total_return']:>+8.2f}%")
    print(f"{prefix}年化:    {res['annualized']:>+8.2f}%")
    print(f"{prefix}夏普:    {res['sharpe']:>8.2f}")
    print(f"{prefix}回撤:    {res['max_drawdown']:>8.2f}%")
    print(f"{prefix}交易:    {res['n_buys']} 买 / {res['n_sells']} 卖   胜率 {res['win_rate']:.1f}%")
    print(f"{prefix}基准:    {res['benchmark_annualized']:+.2f}%   "
          f"Alpha {res['alpha']:+.2f}%")
    if r.get("reason_stats"):
        print(f"{prefix}卖出原因:")
        for reason, s in r["reason_stats"].items():
            print(f"{prefix}  {reason:<18} {s['count']:>3} 笔, 平均收益 {s['avg_pnl']:+.2f}%")


def save_result(r, name):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    p = PROJECT / "reports" / f"backtest_{name}_{ts}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n  💾 {p.relative_to(PROJECT)}")


if __name__ == "__main__":
    main()
