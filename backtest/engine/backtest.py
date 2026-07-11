#!/usr/bin/env python3
"""回测引擎：无未来函数，纯数据驱动。

核心原则：
1. 对每个日期 T，只用 T 之前的数据计算评分
2. chart_data 按日期截断（只取 xAxis ≤ T 的点）
3. 交易记录按日期截断（只取 _date_prefix ≤ T）
4. 费率、经理数据用当前值（变化极慢，可接受）
"""
import json, math, statistics, sys, os
from pathlib import Path
from datetime import datetime, date
from collections import defaultdict
from typing import Optional

BACKTEST_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BACKTEST_DIR / "data"
PROJECT_DIR = BACKTEST_DIR.parent

# 加载股票→行业映射表
STOCK_SECTOR_MAP_FILE = DATA_DIR / "stock_sector_map.json"
STOCK_SECTOR_MAP = {}
if STOCK_SECTOR_MAP_FILE.exists():
    try:
        STOCK_SECTOR_MAP = json.loads(STOCK_SECTOR_MAP_FILE.read_text("utf-8"))
    except:
        pass

# 基金持仓缓存（全局加载一次）
FUND_HOLDINGS_CACHE = {}
try:
    import glob as _glob
    for _f in _glob.glob(str(PROJECT_DIR / "data" / "fund_cache" / "fund_holdings_*.json")):
        _code = Path(_f).stem.replace("fund_holdings_", "")
        _data = json.loads(open(_f, "r", encoding="utf-8").read())
        _stocks = _data.get("top_stocks", [])
        if _stocks:
            FUND_HOLDINGS_CACHE[_code] = _stocks
except:
    pass
sys.path.insert(0, str(PROJECT_DIR))
import sys
from tools.fund_scorer import DimensionScore, calc_max_drawdown, _float, scale_penalty, _stock_to_unique_code, score_penetration_valuation
from tools.fund_rules import weighted_clear, buy_shield, take_profit_level, swap_cost

# ML信号增强（可选，需要lightgbm）
try:
    from tools.ml_signal import MLSignalEnhancer
    ML_AVAILABLE = True
except ImportError:
    ML_AVAILABLE = False

# 技术指标（RSI/MACD/布林带/均线交叉）— 融合QuantDinger算法
from tools.technical_indicators import compute_entry_timing_score, compute_rsi, ma_trend

RISK_FREE_RATE = 0.025
PURCHASE_DISCOUNT = 0.1


# ── 日期感知的评分 ──

def score_momentum_backtest(chart_points, cutoff_date):
    """用截止到 cutoff_date 的 chart_data 计算动量分。
    chart_points: [{xAxis: "2026-01-15", yAxis: 5.23}, ...]
    cutoff_date: "2026-03-15"
    只使用 xAxis ≤ cutoff_date 的点。
    """
    valid = [p for p in chart_points if p.get("xAxis", "") <= cutoff_date]
    if len(valid) < 20:
        return DimensionScore(score=2.5, weight=0.15, freshness_days=0)

    values = [(100 + _float(p.get("yAxis", 0))) / 100 * 100 for p in valid]
    current = values[-1]

    # 20日 MA
    ma20 = statistics.mean(values[-20:])
    score_short = min(5.0, (current / ma20 - 1) * 100 + 2.5)

    # 60日 MA 斜率
    if len(values) >= 60:
        ma60 = statistics.mean(values[-60:])
        ma60_30 = statistics.mean(values[-90:-30]) if len(values) >= 90 else statistics.mean(values[:30])
        slope = (ma60 - ma60_30) / ma60_30 * 100
        score_mid = min(5.0, slope * 2 + 2.5)
    else:
        score_mid = 2.5

    # 回撤恢复
    peak = max(values)
    distance = (current - peak) / peak
    if distance >= 0: score_recovery = 5.0
    elif distance > -0.05: score_recovery = 4.0
    elif distance > -0.10: score_recovery = 3.0
    elif distance > -0.20: score_recovery = 2.0
    else: score_recovery = 1.0

    score = score_short * 0.25 + score_mid * 0.25 + score_recovery * 0.15 + 3.0 * 0.35
    return DimensionScore(score=min(5.0, max(0, score)), weight=0.15, freshness_days=0)


def score_quality_backtest(chart_points, cutoff_date, scale_text=None, perf_data=None):
    """用 chart_data 算质量分（替代 rank_pct，用绝对收益代替）。
    perf_data 可作为补充（如果有当天的排名数据），
    但回测中只使用 chart_data 算的收益率。
    """
    valid = [p for p in chart_points if p.get("xAxis", "") <= cutoff_date]
    if len(valid) < 20:
        return DimensionScore(score=2.5, weight=0.25, freshness_days=0)

    values = [_float(p.get("yAxis", 0)) for p in valid]  # 累计收益率 %
    cur_return = values[-1]

    # 近1月收益 = 最近 20 个交易日的收益
    if len(valid) >= 20:
        ret_1m = cur_return - values[-20]
    else:
        ret_1m = cur_return - values[0]

    # 近3月收益 ≈ 60 个交易日
    if len(valid) >= 60:
        ret_3m = cur_return - values[-60]
    else:
        ret_3m = cur_return - values[0]

    # 近6月收益
    if len(valid) >= 120:
        ret_6m = cur_return - values[-120]
    else:
        ret_6m = cur_return - values[0]

    # 用绝对收益打分（注意：这不是同类排名，但有区分度）
    # ret_1m: >10%→5, >5%→4, >0%→3, >-5%→2, else→1
    def _ret_score(r):
        if r >= 10: return 5.0
        elif r >= 5: return 4.0
        elif r >= 0: return 3.0
        elif r >= -5: return 2.0
        else: return 1.0

    # 最大回撤
    nav_idx = [(100 + v) / 100 * 100 for v in values]
    mdd = calc_max_drawdown(nav_idx)
    if mdd <= 10: score_dd = 5.0
    elif mdd <= 15: score_dd = 4.0
    elif mdd <= 20: score_dd = 3.0
    elif mdd <= 30: score_dd = 2.0
    else: score_dd = 1.0

    # 短期过热惩罚：近3月涨幅极端过高则扣分
    heat_penalty = 0.0
    if ret_3m > 100:
        heat_penalty = -0.8  # 翻倍以上，明显过热
    elif ret_3m > 80:
        heat_penalty = -0.4  # 涨幅过高，轻微扣分

    score = (_ret_score(ret_1m) * 0.25 + _ret_score(ret_3m) * 0.20 + _ret_score(ret_6m) * 0.15
            + score_dd * 0.20 + 3.0 * 0.10 + 3.0 * 0.10)
    score += heat_penalty  # 过热扣分
    penalty = scale_penalty(scale_text) if scale_text else 1.0
    return DimensionScore(score=min(5.0, max(0, score * penalty)), weight=0.25, freshness_days=0)


def score_smart_money_backtest(fund_name, cutoff_date, trading_by_date, fund_code=None):
    """基于截止到 cutoff_date 的大佬交易记录计算聪明钱分。
    增强版: 区分建仓/加仓/清仓信号，叠加共识与趋势强度。
    trading_by_date: {"2026-01-15": [{fund_name, action, _user, fund_code?}, ...]}
    cutoff_date: "2026-03-15" → 只取 <= 的日期。
    fund_code: 可选，用于精确匹配（优先级高于 fund_name）。
    """
    sorted_dates = sorted(d for d in trading_by_date if d <= cutoff_date)

    def _match(record):
        """匹配: fund_code 优先 → fund_name → 包含"""
        if fund_code and record.get("fund_code") == fund_code:
            return True
        if record.get("fund_name", "") == fund_name:
            return True
        # 模糊: 名称包含（处理份额后缀差异）
        rn = record.get("fund_name", "")
        if rn and (fund_name in rn or rn in fund_name):
            return True
        return False

    # 追踪每个用户对这只基金的操作历史
    user_actions = {}   # {user: [action, ...]}
    first_buy_dates = {}  # {user: first_buy_date}

    for d in sorted_dates:
        for r in trading_by_date[d]:
            if not _match(r):
                continue
            act = r.get("action", "")
            user = r.get("_user", "")
            if user not in user_actions:
                user_actions[user] = []
            if "买入" in act or "转换入" in act or "加仓" in act or "定投" in act:
                user_actions[user].append("buy")
                if user not in first_buy_dates:
                    first_buy_dates[user] = d
            elif "卖出" in act or "转换出" in act or "减仓" in act:
                user_actions[user].append("sell")

    # 今天的操作
    today_records = trading_by_date.get(cutoff_date, [])
    # 如果今天无交易记录，回退到最近有数据的日期
    if not today_records and sorted_dates:
        for fallback_date in reversed(sorted_dates):
            fb = trading_by_date.get(fallback_date, [])
            if any(_match(r) for r in fb):
                today_records = fb
                break
    first_time_buyers = set()   # 建仓
    repeat_buyers = set()       # 加仓
    daily_buyers = set()
    daily_sellers = set()
    complete_exiters = set()    # 清仓

    for r in today_records:
        if not _match(r):
            continue
        act = r.get("action", "")
        user = r.get("_user", "")

        if "买入" in act or "转换入" in act or "加仓" in act or "定投" in act:
            daily_buyers.add(user)
            if user in first_buy_dates and first_buy_dates[user] < cutoff_date:
                repeat_buyers.add(user)
            else:
                first_time_buyers.add(user)
        elif "卖出" in act or "转换出" in act or "减仓" in act:
            daily_sellers.add(user)
            if user in user_actions:
                buys = user_actions[user].count("buy")
                sells = user_actions[user].count("sell")
                if sells >= buys:
                    complete_exiters.add(user)

    # 连续共识检测: 过去14天有多少不同用户买入
    lookback_days = 14
    consensus_users = set()
    from datetime import datetime, timedelta
    try:
        cutoff_dt = datetime.strptime(cutoff_date[:10], "%Y-%m-%d")
        lookback_start = (cutoff_dt - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
    except:
        lookback_start = cutoff_date

    for d in sorted_dates:
        if lookback_start and d < lookback_start:
            continue
        if d >= cutoff_date:
            continue
        for r in trading_by_date[d]:
            if not _match(r):
                continue
            act = r.get("action", "")
            if "买入" in act or "转换入" in act or "加仓" in act or "定投" in act:
                consensus_users.add(r.get("_user", ""))

    # 评分计算
    n_first = len(first_time_buyers)          # 建仓人数
    n_repeat = len(repeat_buyers)              # 加仓人数
    n_buyers = len(daily_buyers)               # 今日总买入人数
    n_sellers = len(daily_sellers)              # 今日总卖出人数
    n_consensus = len(consensus_users)         # 过去14天总买入人数
    n_exited = len(complete_exiters)           # 清仓人数

    # 建仓: 新人大佬首次买入 → 强信号
    raw_first = min(n_first, 5) * 3.0
    # repeat -> medium
    raw_repeat = min(n_repeat, 4) * 1.5
    # consensus over 14 days
    raw_consensus = min(max(0, n_consensus - n_buyers), 10) * 0.4
    # same-day breadth
    raw_breadth = min(n_buyers / 2, 2.0) * 2.0

    raw = raw_first * 0.35 + raw_repeat * 0.25 + raw_consensus * 0.15 + raw_breadth * 0.25

    # exit penalty (mild)
    if n_exited >= 1:
        raw -= min(n_exited, 3) * 2.0
    # sell overwhelm -> cap
    if n_buyers > 0 and n_sellers > n_buyers * 3:
        raw = min(raw, 3.0)
    # no buy signal -> low
    # 7-day super consensus: 3+ buyers in a week -> +1.0 bonus
    n_weekly = len(first_time_buyers) + len(repeat_buyers)
    if n_weekly >= 3:
        raw += 1.0
    if raw == 0 and n_sellers > 0:
        return DimensionScore(score=1.0, weight=0.20, freshness_days=0)

    return DimensionScore(score=min(5.0, max(0, raw)), weight=0.20, freshness_days=0)




def detect_market_state(cutoff_date, fund_charts, benchmark_code="110020", lookback_days=60):
    """Use benchmark fund performance to determine market state"""
    pts = fund_charts.get(benchmark_code, [])
    valid = [p for p in pts if p.get("xAxis", "") <= cutoff_date]
    if len(valid) < 20:
        return "neutral"  # insufficient data
    recent = valid[-min(lookback_days, len(valid)):]
    start_val = _float(recent[0].get("yAxis", 0))
    end_val = _float(recent[-1].get("yAxis", 0))
    perf = end_val - start_val
    if perf > 8: return "bull"
    if perf < -5: return "bear"
    return "neutral"


# ── 基金相关性分析 ──

def _compute_fund_returns(chart_points, cutoff_date, lookback=60):
    """提取截止到cutoff_date的最近lookback个日收益率。"""
    valid = [p for p in chart_points if p.get("xAxis", "") <= cutoff_date]
    if len(valid) < 20:
        return []
    recent = valid[-min(lookback + 1, len(valid)):]
    returns = []
    for i in range(1, len(recent)):
        prev = _float(recent[i-1].get("yAxis", 0))
        curr = _float(recent[i].get("yAxis", 0))
        # 净值 = (100 + yAxis) / 100，收益率 =净值变化
        prev_nav = (100 + prev) / 100
        curr_nav = (100 + curr) / 100
        if prev_nav > 0:
            returns.append((curr_nav / prev_nav - 1) * 100)
    return returns


def _pearson_correlation(x, y):
    """纯Python实现的Pearson相关系数。"""
    n = min(len(x), len(y))
    if n < 10:
        return 0.0
    x = x[-n:]
    y = y[-n:]
    sum_x = sum(x)
    sum_y = sum(y)
    sum_xy = sum(xi * yi for xi, yi in zip(x, y))
    sum_x2 = sum(xi * xi for xi in x)
    sum_y2 = sum(yi * yi for yi in y)
    denom = ((n * sum_x2 - sum_x * sum_x) * (n * sum_y2 - sum_y * sum_y)) ** 0.5
    if denom == 0:
        return 0.0
    return (n * sum_xy - sum_x * sum_y) / denom


def compute_correlation_matrix(fund_charts, codes, cutoff_date, lookback=60):
    """计算一组基金之间的相关系数矩阵。
    返回 {code: {code: correlation}}。
    """
    returns_cache = {}
    for code in codes:
        pts = fund_charts.get(code, [])
        if not pts:
            continue
        rets = _compute_fund_returns(pts, cutoff_date, lookback)
        if len(rets) >= 10:
            returns_cache[code] = rets

    corr_matrix = {}
    for c1 in returns_cache:
        corr_matrix[c1] = {}
        for c2 in returns_cache:
            if c1 == c2:
                corr_matrix[c1][c2] = 1.0
            elif c2 in corr_matrix.get(c1, {}):
                corr_matrix[c1][c2] = corr_matrix[c1][c2]
            else:
                corr_matrix[c1][c2] = _pearson_correlation(returns_cache[c1], returns_cache[c2])
    return corr_matrix


def check_max_correlation(candidate_code, held_codes, corr_matrix, threshold=0.85):
    """检查候选基金与已持仓基金的最大相关系数。
    返回最大相关系数（如果没有持仓则返回0）。
    """
    if not held_codes or candidate_code not in corr_matrix:
        return 0.0
    max_corr = 0.0
    for hc in held_codes:
        if hc in corr_matrix.get(candidate_code, {}):
            max_corr = max(max_corr, abs(corr_matrix[candidate_code][hc]))
    return max_corr



def get_sector_performance(cutoff_date, fund_charts, fund_holdings_cache, lookback=60):
    """Calculate performance of each sector based on constituent fund returns.
    Returns dict: {sector: avg_return_percent}
    """
    sector_returns = {}
    sector_counts = {}
    
    for code, pts in fund_charts.items():
        valid = [p for p in pts if p.get("xAxis", "") <= cutoff_date]
        if len(valid) < 20:
            continue
        recent = valid[-min(lookback, len(valid)):]
        ret = _float(recent[-1].get("yAxis", 0)) - _float(recent[0].get("yAxis", 0))
        
        # Detect sector from code or name 
        name = ""
        for c, s in fund_holdings_cache.items():
            if isinstance(s, list) and len(s) > 0:
                name = str(c)
        sector, _ = detect_sector(name, code, fund_holdings_cache)
        
        sector_returns[sector] = sector_returns.get(sector, 0) + ret
        sector_counts[sector] = sector_counts.get(sector, 0) + 1
    
    # Average per sector
    result = {}
    for s, total in sector_returns.items():
        count = sector_counts.get(s, 1)
        result[s] = round(total / count, 2)
    return result

def compute_player_rankings(all_records, fund_charts, name_to_code, cutoff_date, config):
    """动态计算大佬权重。只用截止到cutoff_date的数据，无未来函数。"""


# ── 基金所属行业/类型检测 ──
def detect_sector(fund_name, fund_code=None, fund_holdings_cache=None):
    """从基金名判断所属行业/类型。如果提供了持仓数据，用持仓穿透判断。
    返回(sector, is_qdii)。"""
    name = fund_name or ""
    is_qdii = "QDII" in name or "全球" in name or "海外" in name or "纳斯达克" in name or "标普" in name

    # 如果有持仓数据，用持仓穿透判断
    if fund_code and fund_holdings_cache and fund_code in fund_holdings_cache:
        stocks = fund_holdings_cache[fund_code]
        sector_ratios = {}
        for s in stocks:
            scode = s.get("code", "")
            ratio = float(str(s.get("ratio", "0")).replace("%", ""))
            sec = STOCK_SECTOR_MAP.get(scode, "其他")
            sector_ratios[sec] = sector_ratios.get(sec, 0) + ratio
        if sector_ratios:
            top_sector = max(sector_ratios, key=sector_ratios.get)
            top_pct = sector_ratios[top_sector]
            # 只持仓占比超过30%才用持仓判断
            if top_pct >= 30:
                return top_sector, is_qdii

    # 无持仓数据或持仓不够集中，用名字判断
    sector = "其他"
    if "半导体" in name or "芯片" in name: sector = "半导体"
    elif "人工智能" in name or "AI" in name: sector = "AI"
    elif "科技" in name or "信息" in name or "互联网" in name: sector = "科技"
    elif "医疗" in name or "医药" in name or "医" in name: sector = "医疗"
    elif "消费" in name: sector = "消费"
    elif "新能源" in name or "能源" in name or "碳中和" in name: sector = "新能源"
    elif "金融" in name or "银行" in name or "证券" in name or "保险" in name: sector = "金融"
    elif "地产" in name or "基建" in name: sector = "地产基建"
    elif "军工" in name or "国防" in name: sector = "军工"
    elif "农业" in name or "养殖" in name or "畜牧" in name: sector = "农业"
    elif "港股" in name or "恒生" in name or "H股" in name: sector = "港股"
    elif "红利" in name or "股息" in name: sector = "红利"
    elif "债券" in name or "债" in name: sector = "债券"
    elif "货币" in name: sector = "货币"
    elif "混合" in name or "成长" in name or "价值" in name or "精选" in name or "灵活" in name: sector = "混合"
    elif "指数" in name or "ETF" in name or "联接" in name: sector = "指数"
    return sector, is_qdii


def compute_player_rankings(all_records, fund_charts, name_to_code, cutoff_date, config):
    """动态计算大佬权重（多因子增强版）。只用截止到cutoff_date的数据，无未来函数。
    因子：平均收益(50%) + 胜率(30%) + 一致性(20%)，支持时间衰减加权。
    """
    window = config.get("ranking_window", 90)
    fwd_days = config.get("ranking_fwd_days", 30)
    min_buys = config.get("ranking_min_buys", 5)
    from collections import defaultdict
    from datetime import datetime
    import math
    def _float(v):
        try: return float(v)
        except: return 0.0
    cutoff_dt = datetime.strptime(cutoff_date[:10], '%Y-%m-%d')
    half_life = config.get("ranking_half_life", 45)  # 时间衰减半衰期（天）
    player_data = defaultdict(list)  # {uid: [(return, days_ago), ...]}
    for r in all_records:
        act = r.get("action", "")
        if "买入" not in act: continue
        date = r.get("_full_date", "")
        if len(date) < 10: continue
        record_dt = datetime.strptime(date[:10], '%Y-%m-%d')
        if record_dt > cutoff_dt: continue
        if (cutoff_dt - record_dt).days > window: continue
        uid = r.get("_uid", "")
        fn = r.get("fund_name", "")
        code = name_to_code.get(fn, "")
        if not uid or not code:
            continue

        pts = fund_charts.get(code, [])
        if not pts:
            continue
        for i, p in enumerate(pts):
            if p.get("xAxis", "") >= date:
                if i + fwd_days >= len(pts):
                    break
                # 防未来函数：fwd_days 的日期不能超过截止日
                fwd_date = pts[i + fwd_days].get("xAxis", "9999-99-99")
                if fwd_date > cutoff_date[:10]:
                    break  # 未来数据不可用，跳过该笔
                bv = _float(pts[i].get("yAxis", 0))
                sv = _float(pts[i + fwd_days].get("yAxis", 0))
                days_ago = (cutoff_dt - record_dt).days
                player_data[uid].append((sv - bv, days_ago))
                break

    weights = {}
    for uid, rets_days in player_data.items():
        if len(rets_days) < min_buys:
            continue
        # 时间衰减加权：近期交易权重更高
        weighted_returns = []
        total_weight = 0.0
        for ret, days_ago in rets_days:
            w = math.exp(-0.693 * days_ago / half_life)  # exponential decay
            weighted_returns.append((ret, w))
            total_weight += w
        if total_weight == 0:
            continue
        # 因子1: 时间加权平均收益
        avg_ret = sum(r * w for r, w in weighted_returns) / total_weight
        # 因子2: 胜率（收益>0的交易占比）
        wins = sum(1 for r, _ in rets_days if r > 0)
        win_rate = wins / len(rets_days)
        # 因子3: 一致性（收益稳定性，用1 - CV，截断到[0,1]）
        rets_only = [r for r, _ in rets_days]
        mean_ret = sum(rets_only) / len(rets_only) if rets_only else 0
        if mean_ret != 0 and len(rets_only) > 1:
            variance = sum((r - mean_ret) ** 2 for r in rets_only) / (len(rets_only) - 1)
            std = variance ** 0.5
            cv = abs(std / mean_ret) if mean_ret != 0 else 999
            consistency = max(0, min(1, 1 - cv / 3))  # CV<3则一致性好
        else:
            consistency = 0.5

        # 复合得分: avg_ret归一化(50%) + win_rate(30%) + consistency(20%)
        ret_score = max(0, min(1, (avg_ret + 5) / 15))  # -5%~+10% 映射到 0~1
        composite = ret_score * 0.50 + win_rate * 0.30 + consistency * 0.20

        # 映射到权重
        if composite >= 0.75: weights[uid] = 2.0
        elif composite >= 0.60: weights[uid] = 1.5
        elif composite >= 0.45: weights[uid] = 1.0
        elif composite >= 0.30: weights[uid] = 0.5
        else: weights[uid] = 0.0

    if config.get("verbose_ranking", False):
        scored = [(uid, weights[uid]) for uid in weights]
        scored.sort(key=lambda x: -x[1])
        print(f"  RANK@{cutoff_date[:10]} {len(scored)} scored: {scored[:5]}")
    return weights


def score_fund_backtest(fund_code, fund_name, charts, perf_data, rules, mgr,
                        cutoff_date, trading_by_date, profile=None,
                        allocation_data=None, fund_data_cache=None,
                        industry_data=None):
    """对单只基金在某个历史日期 T 的完整评分。
    ⚠️ 只用 T 之前的 chart_data 和交易记录。
    新增: 资产配置评分 + 规模评分 + 管理稳定性评分 + 行业估值评分
    """
    chart_pts = charts.get(fund_code, []) if isinstance(charts, dict) else []

    momentum = score_momentum_backtest(chart_pts, cutoff_date)
    quality = score_quality_backtest(chart_pts, cutoff_date,
                                     profile.get("scale") if profile else None,
                                     perf_data)
    smart = score_smart_money_backtest(fund_name, cutoff_date, trading_by_date, fund_code)

    # 成本分（使用实际费率）
    from tools.fund_scorer import score_cost
    if rules:
        cost = score_cost(rules)
        # 管理费修正: 管理费>1.2% 扣分, <0.5% 加分
        mf = float(rules.get("manage_fee", 1.0))
        if cost.score > 0:
            if mf > 1.2: cost.score -= 0.5
            elif mf < 0.5: cost.score += 0.3
    else:
        cost = DimensionScore(score=3.0, weight=0.20, freshness_days=365)

    # 经理分（使用实际经理数据）
    from tools.fund_scorer import score_manager
    _mgr_missing = False
    if mgr:
        manager_dim = score_manager(mgr)
        # 如果经理数据虽然存在但内容为空（如 managers=[]），也视为缺失
        if manager_dim.score == 2.5 and not (mgr.get("managers") or []):
            _mgr_missing = True
    else:
        _mgr_missing = True

    if _mgr_missing:
        # 经理数据缺失时降低该维度权重（0.20→0.05），避免用默认值干扰总分
        # 剩余权重按比例分配给其他维度
        manager_dim = DimensionScore(score=2.5, weight=0.05, freshness_days=365)

    # ===== 新增: 资产配置评分 =====
    alloc_modifier = 0.0
    alloc_data = None
    if allocation_data and fund_code in allocation_data:
        alloc_data = allocation_data[fund_code]
    elif fund_data_cache and fund_code in fund_data_cache:
        alloc_data = fund_data_cache[fund_code].get("holdings")

    if alloc_data:
        alloc = alloc_data.get("allocation", {})
        stock_pct = float(alloc.get("股票", 0))
        bond_pct = float(alloc.get("债券", 0))
        cash_pct = float(alloc.get("现金", 0))

        # 基金类型判断
        fund_type = ""
        if profile:
            fund_type = profile.get("fund_type", "")
        elif fund_data_cache and fund_code in fund_data_cache:
            p = fund_data_cache[fund_code].get("profile", {})
            fund_type = p.get("fund_type", "")

        # 偏股型基金应该有高股票仓位
        if "偏股" in fund_type or "股票" in fund_type or "混合" in fund_type or "指数" in fund_type:
            if stock_pct < 50:
                alloc_modifier -= 0.5  # 股票仓位太低，扣分
            elif stock_pct >= 80:
                alloc_modifier += 0.3  # 高仓位加分
        # 偏债型基金
        elif "偏债" in fund_type or "债券" in fund_type:
            if bond_pct > 70:
                alloc_modifier += 0.3
            if stock_pct > 30:
                alloc_modifier -= 0.3  # 偏债基金股票太多

        # 前10持仓集中度
        top_stocks = alloc_data.get("top_stocks", [])
        if top_stocks:
            top10_pct = sum(float(s.get("ratio", "0").replace("%","")) for s in top_stocks[:10])
            if top10_pct > 70:
                alloc_modifier -= 0.3  # 太集中

    # ===== 新增: 规模评分 =====
    scale_modifier = 0.0
    if profile:
        scale_str = profile.get("scale", "")
        if "亿" in scale_str:
            try:
                import re
                nums = re.findall(r'[\d.]+', scale_str.replace("亿元", "").replace("亿", ""))
                if nums:
                    scale_val = float(nums[0])
                    if scale_val < 0.5:
                        scale_modifier = -0.5  # <5000万，清盘风险
                    elif scale_val < 2:
                        scale_modifier = -0.2  # 太小
                    elif scale_val > 200:
                        scale_modifier = -0.2  # 太大，难有超额
                    elif 5 <= scale_val <= 50:
                        scale_modifier = +0.2  # 适中规模加分
            except: pass

    # ===== 新增: 持有天数检查（短线交易惩罚）=====
    holding_modifier = 0.0
    # 不做惩罚，因为回测中无法知道未来的持有天数

    # 基金类型检测（静态）
    fund_type = "active"
    if profile:
        tn = profile.get("fund_type", "")
        if "指数" in tn and "增强" not in tn:
            fund_type = "passive_index"
        elif "指数增强" in tn:
            fund_type = "index_enhanced"

    if fund_type == "passive_index":
        quality = DimensionScore(score=3.0, weight=0.25, freshness_days=0)
        manager_dim = DimensionScore(score=-1, weight=0, freshness_days=0)
        momentum = DimensionScore(score=3.0, weight=0.15, freshness_days=0)

    from tools.fund_scorer import FundScore, DimensionScore as DS
    fs = FundScore(
        fund_code=fund_code,
        fund_type=fund_type,
        quality=quality,
        cost=cost,
        manager=manager_dim,
        momentum=momentum,
        smart_money=smart,
    )
    # 跳过成立天数检测（回测中不准确）
    dims = [quality, cost, manager_dim, momentum, smart]
    raw = sum(d.score * d.weight for d in dims) / max(sum(d.weight for d in dims), 0.01)
    fs.total = raw

    # 应用资产配置+规模修正
    total_modifier = alloc_modifier + scale_modifier

    # ===== 新增: 行业估值评分（防高位接盘）=====
    if industry_data:
        from backtest.engine.sector_valuation import score_sector_valuation_backtest
        sector_adjust = score_sector_valuation_backtest(
            fund_code, fund_name, cutoff_date, industry_data)
        total_modifier += sector_adjust
        if sector_adjust != 0:
            pass  # 可在 verbose 模式下打印

    fs.total = max(0.5, min(5.0, fs.total + total_modifier))

    # 过度上涨扣分已包含在 score_quality_backtest 的 heat_penalty 中
    # 此处不再重复扣分

    fs.verdict = "buy" if raw >= 4.0 else "watch" if raw >= 3.3 else "pass"
    return fs


# ── 组合管理器（无未来函数）──

class Portfolio:
    def __init__(self, initial_cash=10000):
        self.cash = initial_cash
        self.holdings = {}  # {code: {name, shares, cost, buy_date, buy_nav, fee_rate_pct}}
        self.pending_buys = []  # [{date, code, name, amount, shares, nav, fee, confirm_date, t_plus_n}]
        self.trades = []
        self.daily_values = []
        self.total_fees = 0
        self.monthly_injections = 0
        self.fund_rules = {}  # per-fund rules loaded from cache
        self._min_holding_days = 30  # 30-day minimum hold for cost control
        self.yearly_trades = {}  # {year: count}
        self.max_yearly_trades = 6  # annual trade cap
        self.sell_history = {}  # {code: {date: "YYYY-MM-DD", reason: "...", nav: float}} — 冷却期追踪
        self.slippage_pct = 0.0  # 滑点百分比（买入加价，卖出发折）

    def set_fund_rules(self, fund_rules):
        self.fund_rules = fund_rules

    def is_in_cooldown(self, code, current_date, cooldown_config=None):
        """检查基金是否在卖出冷却期内。
        cooldown_config: {"profit_days": int, "loss_days": int} — 止盈卖出的冷却期短，止损/动量崩溃的冷却期长。
        """
        if not cooldown_config or code not in self.sell_history:
            return False
        record = self.sell_history[code]
        sell_date_str = record.get("date", "")
        reason = record.get("reason", "")
        if not sell_date_str:
            return False
        try:
            from datetime import datetime
            sell_dt = datetime.strptime(sell_date_str[:10], "%Y-%m-%d")
            cur_dt = datetime.strptime(current_date[:10], "%Y-%m-%d")
            days_since = (cur_dt - sell_dt).days
        except:
            return False
        # 止盈类卖出冷却期短；止损/动量崩溃类冷却期长
        profit_keywords = ["take_profit", "trailing_tp", "reduce_pos", "rebalance"]
        loss_keywords = ["stop_loss", "momentum_crash", "trail_stop", "peak_dd", "big_sell"]
        if any(kw in reason for kw in profit_keywords):
            cooldown_days = cooldown_config.get("profit_days", 10)
        elif any(kw in reason for kw in loss_keywords):
            cooldown_days = cooldown_config.get("loss_days", 30)
        else:
            cooldown_days = cooldown_config.get("default_days", 15)
        return days_since < cooldown_days

    def get_fee(self, code, default_purchase_fee=0.0015):
        """获取基金的实际申购费率"""
        rules = self.fund_rules.get(code, {})
        pf = rules.get("purchase_fee", default_purchase_fee * 100)
        if isinstance(pf, str):
            try: pf = float(pf.replace("%",""))
            except: pf = default_purchase_fee * 100
        return float(pf) / 100 if pf > 1 else float(pf)  # 1.5%→0.015, 0.15→0.0015

    def get_redeem_fee(self, code, days_held):
        """获取基金的实际赎回费率"""
        rules = self.fund_rules.get(code, {})
        tiers = rules.get("redeem_fees", [])
        if not tiers:
            # 默认阶梯
            if days_held < 7: return 0.015
            if days_held < 30: return 0.0075
            if days_held < 365: return 0.005
            return 0.0
        for tier in tiers:
            interval = str(tier.get("interval", ""))
            rate = float(tier.get("rate", 0))
            # 解析 interval 如 "1天≤持有期限<6天" → 判断 days_held 是否在区间内
            if "≤" in interval and "<" in interval:
                parts = interval.replace("天", "").split("≤")
                if len(parts) >= 2:
                    low_str = parts[0].strip()
                    rest = parts[1].split("<")
                    high_str = rest[0].strip() if len(rest) >= 1 else "9999"
                    try:
                        low = int(low_str) if low_str.isdigit() else 0
                        high = int(high_str) if high_str.isdigit() else 9999
                        if low <= days_held < high:
                            return rate / 100
                    except: pass
            elif "≥" in interval:
                low_str = interval.replace("天", "").replace("≥", "").strip()
                try:
                    low = int(low_str) if low_str.isdigit() else 0
                    if days_held >= low:
                        return rate / 100
                except: pass
            elif "＜" in interval:
                high_str = interval.replace("天", "").replace("＜", "").strip()
                try:
                    high = int(high_str) if high_str.isdigit() else 0
                    if days_held < high:
                        return rate / 100
                except: pass
        return 0.0

    def get_t_plus_n(self, code):
        """获取基金T+N确认天数"""
        rules = self.fund_rules.get(code, {})
        confirm = rules.get("confirm_date", "")
        buy_date = rules.get("buy_date", "")
        # 简单判断: 如果 confirm_date 比 buy_date 晚2天 → T+2
        if confirm and buy_date:
            try:
                c_day = int(confirm.split("-")[-1])
                b_day = int(buy_date.split(" ")[0].split("-")[-1])
                diff = (c_day - b_day) % 30
                if diff <= 1: return 1  # T+1
                if diff <= 2: return 2  # T+2
                return diff
            except: pass
        # 根据基金类型判断
        rules = self.fund_rules.get(code, {})
        profile = getattr(self, '_profiles', {}).get(code, {})
        fund_type = profile.get("fund_type", "") if profile else ""
        if "QDII" in fund_type: return 2
        return 1  # 默认 T+1

    def get_day_limit(self, code):
        """获取基金日申购限额"""
        rules = self.fund_rules.get(code, {})
        limit = rules.get("day_limit", 99999999)
        if limit == "Infinity" or limit is None or limit == float('inf'):
            return 99999999
        try: return float(limit)
        except: return 99999999

    def inject_cash(self, amount, day_str=""):
        """每月工资注入。"""
        self.cash += amount
        self.monthly_injections += amount
        self.trades.append({"date": day_str, "code": "CASH", "action": "salary", "amount": amount})

    def value(self, fund_prices=None):
        total = self.cash
        # 已确认持仓
        for code, h in self.holdings.items():
            price = 1.0
            if fund_prices and code in fund_prices:
                price = fund_prices[code]
            total += h["shares"] * price
        # 待确认买入（T+N 期间，按成本价计入）
        for pb in self.pending_buys:
            total += pb["shares"] * pb["nav"]
        return total

    def buy(self, code, name, amount, price=1.0, day_str="", fund_rules=None):
        """买入，使用实际费率+T+N确认+滑点模拟。"""
        fee_rate = self.get_fee(code)
        day_limit = self.get_day_limit(code)
        amount = min(amount, day_limit)
        if amount > self.cash:
            amount = self.cash
        if amount < 100:
            return False
        # 滑点：买入实际价格略高（模拟申购时间差、净值波动等）
        eff_price = price * (1 + self.slippage_pct / 100.0) if self.slippage_pct > 0 else price
        fee = round(amount * fee_rate, 2)
        net_amount = amount - fee
        shares = net_amount / eff_price if eff_price > 0 else 0
        t_plus_n = self.get_t_plus_n(code)
        confirm_date = self._add_trading_days(day_str, t_plus_n)

        self.cash -= amount
        self.total_fees += fee
        # Track yearly trade count
        _yr = day_str[:4] if len(day_str) >= 4 else "0000"
        self.yearly_trades[_yr] = self.yearly_trades.get(_yr, 0) + 1
        self.trades.append({
            "date": day_str, "code": code, "action": "buy",
            "amount": amount, "fee": fee, "nav": price,
            "confirm_date": confirm_date, "t_plus_n": t_plus_n
        })

        # 加入待确认队列（T+N 后才真正持仓）
        self.pending_buys.append({
            "date": day_str, "code": code, "name": name,
            "shares": shares, "nav": price, "fee": fee,
            "confirm_date": confirm_date, "amount": amount
        })
        return True

    def settle_pending(self, current_date):
        """处理 T+N 确认到期的待确认买入"""
        settled = []
        remaining = []
        for pb in self.pending_buys:
            if pb["confirm_date"] <= current_date:
                code = pb["code"]
                if code not in self.holdings:
                    self.holdings[code] = {
                        "name": pb["name"], "shares": 0, "cost": 0,
                        "buy_date": pb["date"], "buy_nav": pb["nav"],
                        "last_buy_date": pb["date"],
                    }
                h = self.holdings[code]
                # 更新加权平均买入净值（用于更准确的累计收益计算）
                old_shares = h["shares"]
                new_shares = pb["shares"]
                total_shares = old_shares + new_shares
                if total_shares > 0:
                    h["buy_nav"] = (old_shares * h["buy_nav"] + new_shares * pb["nav"]) / total_shares
                h["shares"] = total_shares
                h["cost"] += pb["amount"]
                h["last_buy_date"] = pb["date"]
                settled.append(pb)
            else:
                remaining.append(pb)
        self.pending_buys = remaining
        return len(settled)

    @staticmethod
    def _add_trading_days(date_str, n_days):
        """简单近似: 加 N 个日历日"""
        from datetime import datetime, timedelta
        try:
            dt = datetime.strptime(date_str[:10], "%Y-%m-%d")
            return (dt + timedelta(days=n_days)).strftime("%Y-%m-%d")
        except:
            return date_str

    def _holding_days(self, code, current_date):
        """估算持有天数。"""
        if code not in self.holdings:
            return 999
        h = self.holdings[code]
        if not h.get("buy_date"):
            return 999
        try:
            d1 = h["buy_date"]
            d2 = current_date
            from datetime import datetime
            dt1 = datetime.strptime(d1[:10], "%Y-%m-%d")
            dt2 = datetime.strptime(d2[:10], "%Y-%m-%d")
            return (dt2 - dt1).days
        except:
            return 999

    def _redemption_fee_rate(self, days_held, code=""):
        """使用实际赎回费率"""
        if code and code in self.fund_rules:
            # 使用基金实际费率
            tiers = self.fund_rules[code].get("redeem_fees", [])
            if tiers:
                for tier in tiers:
                    interval = str(tier.get("interval", ""))
                    rate = float(tier.get("rate", 0))
                    if "≤" in interval and "<" in interval:
                        parts = interval.replace("天", "").split("≤")
                        if len(parts) >= 2:
                            rest = parts[1].split("<")
                            try:
                                low = int(parts[0].strip()) if parts[0].strip().isdigit() else 0
                                high = int(rest[0].strip()) if len(rest) >= 1 and rest[0].strip().isdigit() else 9999
                                if low <= days_held < high:
                                    return rate / 100
                            except: pass
                    elif "≥" in interval:
                        low_str = interval.replace("天", "").replace("≥", "").strip()
                        try:
                            low = int(low_str) if low_str.isdigit() else 0
                            if days_held >= low:
                                return rate / 100
                        except: pass
                return 0.0
        # 默认阶梯
        if days_held < 7: return 0.015
        if days_held < 30: return 0.0075
        if days_held < 365: return 0.005
        return 0.0

    def sell(self, code, amount, price=1.0, day_str="", sell_reason="", force_sell=False):
        """卖出，使用实际赎回费，检查 T+N 锁定。"""
        if code not in self.holdings:
            return
        # 30天最低持有期检查（除止损/清仓跟卖外）
        if not force_sell:
            _hold_d = self._holding_days(code, day_str)
            min_hold = self._min_holding_days if hasattr(self, '_min_holding_days') else 0
            if min_hold > 0 and _hold_d < min_hold:
                # 例外：止损/移动止盈/动量崩溃等不受最低持有期限制
                is_exception = any(kw in (sell_reason or "") for kw in [
                    "stop_loss", "big_sell", "trail_stop", "peak_dd",
                    "trailing_tp", "momentum_crash"])
                if not is_exception:
                    return  # 持有期不足，不卖

        # 检查 T+N 锁定：pending_buys 中是否有未确认的同基金
        for pb in self.pending_buys:
            if pb["code"] == code and pb["confirm_date"] > day_str:
                return  # 尚在 T+N 锁定期，不能卖出

        h = self.holdings[code]
        days_held = self._holding_days(code, day_str)
        redeem_fee_rate = self._redemption_fee_rate(days_held, code)
        # 滑点：卖出实际价格略低
        _slip = 1 - self.slippage_pct / 100.0 if self.slippage_pct > 0 else 1.0

        if amount <= 0:
            # 清仓
            proceeds = h["shares"] * price * _slip
            fee = round(proceeds * redeem_fee_rate, 2)
            self.cash += (proceeds - fee)
            self.total_fees += fee
            _yr = day_str[:4] if len(day_str) >= 4 else "0000"
            self.yearly_trades[_yr] = self.yearly_trades.get(_yr, 0) + 1
            self.trades.append({"date": day_str, "code": code, "action": "sell_all",
                               "amount": round(proceeds, 2), "fee": fee,
                               "price": price, "days_held": days_held, "reason": sell_reason})
            if code in self.holdings: del self.holdings[code]
            # 记录卖出历史（用于冷却期追踪）
            self.sell_history[code] = {"date": day_str, "reason": sell_reason, "nav": price}
        # 部分卖出
        shares_to_sell = amount / price
        if shares_to_sell >= h["shares"]:
            self.sell(code, 0, price, day_str, sell_reason)
            return
        # 滑点导致实际收到金额略少
        proceeds = amount * _slip
        fee = round(proceeds * redeem_fee_rate, 2)
        # 按比例扣减成本（而非用卖出金额直接扣减，后者在盈利/亏损时会扭曲剩余成本）
        cost_ratio = shares_to_sell / h["shares"] if h["shares"] > 0 else 0
        h["cost"] -= h["cost"] * cost_ratio
        h["shares"] -= shares_to_sell
        self.cash += (proceeds - fee)
        self.total_fees += fee
        self.trades.append({"date": day_str, "code": code, "action": "sell",
                           "amount": amount, "fee": fee, "days_held": days_held, "reason": sell_reason})

    def snapshot(self, day_str, fund_prices=None):
        self.daily_values.append({
            "date": day_str,
            "cash": round(self.cash, 2),
            "holdings_value": round(self.value(fund_prices) - self.cash, 2),
            "total": round(self.value(fund_prices), 2),
        })


# ── 资金分配器（回测版）──

def kelly_allocate(candidates, total_cash, kelly_cap=0.2, cash_reserve=0.2, max_pos=0.15):
    """半凯利分配。折扣×0.5 + 硬上限。"""
    available = total_cash * (1 - cash_reserve)
    for c in candidates:
        p = c["score"] / 5.0
        b = max(p * 2, 0.5)
        kelly = max(0, min((p * b - (1 - p)) / b, kelly_cap))
        # 半凯利: 直接砍半
        kelly = kelly * 0.5
        suggested = available * kelly * c["score"] / 5.0
        if c["day_limit"] and c["day_limit"] < 999999:
            suggested = min(suggested, c["day_limit"])
        # 硬上限: 单只基金不超过总资产25%, 单次不超过可用现金30%
        suggested = min(suggested, total_cash * max_pos)  # max_pos 默认0.15=15%
        suggested = min(suggested, available * 0.30)       # 单次不超过可用现金30%
        suggested = round(suggested / 100) * 100
        c["_suggested"] = suggested

    candidates.sort(key=lambda x: x["score"], reverse=True)
    allocated = 0
    results = []
    for c in candidates:
        if allocated >= available or c["_suggested"] < 100:
            continue
        if allocated + c["_suggested"] > available:
            c["_suggested"] = round((available - allocated) / 100) * 100
        if c["_suggested"] < 100:
            continue
        allocated += c["_suggested"]
        results.append(c)
    return results


def run_backtest(config):
    """运行回测主循环。"""
    import json

    # 加载数据（支持多年；用 _fixed 文件）
    print("加载历史数据...")
    data_file = DATA_DIR / "trading_by_date_fixed.json"
    if not data_file.exists():
        data_file = DATA_DIR / "trading_by_date.json"
    with open(data_file, "r", encoding="utf-8") as f:
        trading_by_date = json.load(f)

    hist_file = DATA_DIR / "trading_history_fixed.json"
    if not hist_file.exists():
        hist_file = DATA_DIR / "trading_history.json"
    with open(hist_file, "r", encoding="utf-8") as f:
        all_records = json.load(f)

    with open(DATA_DIR / "fund_charts.json", "r", encoding="utf-8") as f:
        fund_charts = json.load(f)

    # 加载行业估值数据（新增）
    industry_data = {}
    if config.get("sector_valuation", False):
        try:
            from backtest.engine.sector_valuation import load_industry_data, test_coverage
            industry_data = load_industry_data()
            if industry_data:
                # 测试覆盖率
                fund_codes = list(fund_charts.keys())
                fund_name_map = json.loads((PROJECT_DIR / "data" / "fund_name_map.json").read_text("utf-8"))
                # reverse: name→code 变为 code→name
                code_to_name = {}
                for nm, cd in fund_name_map.items():
                    if cd not in code_to_name:
                        code_to_name[cd] = nm
                names = [code_to_name.get(c, c) for c in fund_codes]
                test_coverage(names, {n: n for n in names})
                print(f"  加载了 {len(industry_data)} 个行业估值数据（{list(industry_data.keys())}）")
        except Exception as e:
            print(f"  [WARN] 行业估值数据加载失败: {e}")
            industry_data = {}

    # 加载静态数据
    CACHE_DIR = PROJECT_DIR / "data" / "fund_cache"
    import glob

    def load_cache(prefix):
        data = {}
        for f in glob.glob(str(CACHE_DIR / f"{prefix}_*.json")):
            stem = Path(f).stem
            # Remove prefix from stem to get code
            if stem.startswith(prefix):
                code = stem[len(prefix)+1:] if stem[len(prefix)] == '_' else stem[len(prefix):]
            else:
                code = stem.replace(prefix, "", 1).lstrip("_")
            try:
                data[code] = json.loads(open(f, "r", encoding="utf-8").read())
            except: pass
        return data

    fund_profiles = load_cache("fund_profile")
    fund_rules = load_cache("trade_rules")
    fund_managers = load_cache("fund_manager")
    fund_holdings_data = load_cache("fund_holdings_*latest")  # 新增: 持仓穿透+资产配置

    # 补充: 用 fund_data 作为后备（有更完整的 holdings 数据）
    fund_data_cache = {}
    for f in glob.glob(str(CACHE_DIR / "fund_data_*.json")):
        code = Path(f).stem.replace("fund_data_", "")
        try:
            d = json.loads(open(f, "r", encoding="utf-8").read())
            fund_data_cache[code] = d
        except: pass

    # 构建 fund_code → fund_name 映射
    code_to_name = {}
    # 从 holdings_snapshot
    snap_file = PROJECT_DIR / "data" / "holdings_snapshot.json"
    if snap_file.exists():
        snap = json.loads(snap_file.read_text("utf-8"))
        for user, funds in snap.get("holdings", {}).items():
            for f in funds if isinstance(funds, list) else []:
                if isinstance(f, dict) and f.get("code") and f.get("name"):
                    code_to_name[f["code"]] = f["name"]

    # 从 fund_name_map.json（eastmoney API 补全的映射）
    name_map_file = PROJECT_DIR / "data" / "fund_name_map.json"
    if name_map_file.exists():
        ext_map = json.loads(name_map_file.read_text("utf-8"))
        for name, code in ext_map.items():
            if code not in code_to_name:
                code_to_name[code] = name

    # 反向映射 name → code（用于动态排分）
    name_to_code = {v: k for k, v in code_to_name.items()}

    # 构建标准化名称映射（去除份额后缀 A/C/E/H/I/R 等）用于模糊匹配
    import re as _re
    _SUFFIX_PATTERN = _re.compile(r'[ACHIRachir][类类]?$')
    _BRACKET_SUFFIX = _re.compile(r'\([ACHIRachir]\)$')
    normalized_name_map = {}  # 标准化名 → [(code, 原名), ...]
    for code, name in code_to_name.items():
        norm = name
        # 去除括号内的份额标识 如 "(A)" "(C)"
        norm = _BRACKET_SUFFIX.sub('', norm).strip()
        # 去除末尾的 A/C/E 等份额标识
        norm = _SUFFIX_PATTERN.sub('', norm).strip()
        if norm != name:
            normalized_name_map.setdefault(norm, []).append((code, name))
    # 去重：每个标准化名只保留一个代码（取第一个）
    normalized_name_map = {k: v[0][0] for k, v in normalized_name_map.items() if v}

    def _resolve_fund_code(fund_name):
        """三步匹配：精确→标准化→包含匹配"""
        # Step 1: 精确匹配
        code = name_to_code.get(fund_name)
        if code:
            return code
        # Step 2: 标准化匹配（去除份额后缀）
        norm = _BRACKET_SUFFIX.sub('', fund_name).strip()
        norm = _SUFFIX_PATTERN.sub('', norm).strip()
        code = normalized_name_map.get(norm)
        if code:
            return code
        # Step 3: 包含匹配（基金名是映射中某个名称的子串或反过来）
        for c, n in code_to_name.items():
            if len(fund_name) >= 4 and (fund_name in n or n in fund_name):
                return c
        return None

    # 回测日期范围（多年代迭：key 已经是 YYYY-MM-DD）
    dates = sorted(trading_by_date.keys())
    start_date = config["start_date"]
    end_date = config["end_date"]
    backtest_dates = [d for d in dates if start_date <= d <= end_date]

    print(f"\nPeriod: {config['start_date']} ~ {config['end_date']}")
    print(f"Days: {len(backtest_dates)}")
    print(f"start_cash: {config['initial_cash']:,.0f}")
    print(f"weights: Q{config['weights']['quality']} C{config['weights']['cost']} M{config['weights']['manager']} Mo{config['weights']['momentum']} SM{config['weights']['smart_money']}")

    portfolio = Portfolio(config["initial_cash"])
    portfolio.set_fund_rules(fund_rules)
    portfolio._profiles = fund_profiles  # 供 get_t_plus_n 使用
    portfolio.slippage_pct = config.get("slippage_pct", 0.0)  # 滑点模拟
    fund_holdings_data[""] = {}  # 确保load_cache正确工作
    scores_history = []
    fund_prices = {}  # 初始化在前，避免首次迭代 sell 逻辑引用未定义变量
    _corr_matrix = {}  # 相关性矩阵（每30天重算）
    _max_corr = config.get("max_correlation", 0)  # 最大允许相关系数（0=禁用）
    _buy_back_watchlist = {}  # {code: {"name":..., "sell_date":..., "sell_nav":...}} — 企稳买回追踪

    # ── ML信号增强初始化 ──
    _ml_enabled = config.get("ml_signal", False) and ML_AVAILABLE
    _ml_weight = config.get("ml_weight", 1.0)  # ML预测对评分的影响权重
    _ml_enhancer = None
    _ml_training_data = []  # 收集训练数据 [(code, date, scores_dict, buy_count, market_state)]
    _ml_retrain_interval = config.get("ml_retrain_days", 60)
    _ml_min_train_samples = config.get("ml_min_samples", 50)
    _ml_cold_start = True  # ML 冷启动标志
    _ml_cold_start_score_bonus = config.get("ml_cold_start_bonus", 0.3)  # 冷启动期额外加分补偿
    _ml_warmup_cycle = 0  # 已完成的训练轮次
    if _ml_enabled:
        _ml_enhancer = MLSignalEnhancer(
            fund_charts, fund_profiles, fund_rules,
            fwd_days=config.get("ml_fwd_days", 30),
            label_threshold=config.get("ml_label_threshold", 3.0))
        print("ML signal enhancement: enabled")

    for idx, day in enumerate(backtest_dates):
        cutoff_full = day  # 已经是 YYYY-MM-DD

        # 处理 T+N 确认到期的买入
        portfolio.settle_pending(cutoff_full)

        # 市场状态检测 + 动态仓位上限
        _market_state = "neutral"
        try:
            _market_state = detect_market_state(cutoff_full, fund_charts)
        except: pass
        # Check if user enabled dynamic limits
        _use_dyn = "dyn_max_pos_bull" in config
        if _use_dyn:
            if _market_state == "bull":
                _dyn_max_pos = config.get("dyn_max_pos_bull", 35)
                _dyn_cash_reserve = config.get("dyn_cash_reserve_bull", 0.10)
            elif _market_state == "bear":
                _dyn_max_pos = config.get("dyn_max_pos_bear", 15)
                _dyn_cash_reserve = config.get("dyn_cash_reserve_bear", 0.40)
            else:
                _dyn_max_pos = config.get("dyn_max_pos_neutral", 25)
                _dyn_cash_reserve = config.get("dyn_cash_reserve_neutral", 0.20)
        else:
            # Use fixed config values
            _dyn_max_pos = config.get("max_position_pct", 25)
            _dyn_cash_reserve = config.get("cash_reserve_pct", 0.10)

        # ── 动态评分门槛：根据市场状态调整 min_score ──
        _effective_min_score = config.get("min_score", 3.3)
        _dyn_min_score_key = f"min_score_{_market_state}"  # min_score_bull / min_score_bear / min_score_neutral
        if _dyn_min_score_key in config:
            _effective_min_score = config[_dyn_min_score_key]

        # ── ML冷启动降门槛：ML不可靠时放宽买入标准 ──
        if _ml_enabled and _ml_cold_start:
            _cs_drop = config.get("ml_cold_start_drop", 0.5)  # 冷启动期间降低门槛
            _effective_min_score = max(2.0, _effective_min_score - _cs_drop)

        # ── 熊市趋势过滤：熊市状态下跳过所有买入 ──
        _bear_no_buy = config.get("bear_market_no_buy", False) and _market_state == "bear"

        # ── 冷却期配置 ──
        _cooldown_cfg = None
        _cooldown_days = config.get("cooldown_days", 0)
        if _cooldown_days > 0:
            _cooldown_cfg = {
                "profit_days": config.get("cooldown_profit_days", _cooldown_days),
                "loss_days": config.get("cooldown_loss_days", _cooldown_days * 2),
                "default_days": _cooldown_days,
            }

        # ── 每30天重算基金相关性矩阵 ──
        if _max_corr > 0 and (idx % 30 == 0 or not _corr_matrix):
            _relevant_codes = set(portfolio.holdings.keys())
            _relevant_codes.update(c.get("code", "") for c in candidates) if 'candidates' in dir() else None
            _relevant_codes.discard("")
            if _relevant_codes:
                _corr_matrix = compute_correlation_matrix(
                    fund_charts, list(_relevant_codes), cutoff_full, lookback=60)

        # ── ML模型定期重训练（冷启动保护）──
        if _ml_enabled and _ml_enhancer and idx > 0 and idx % _ml_retrain_interval == 0:
            n_samples = len(_ml_training_data)
            if n_samples >= _ml_min_train_samples:
                _ml_enhancer.pretrain(cutoff_full, _ml_training_data)
                _ml_cold_start = False
                _ml_warmup_cycle += 1
            else:
                if _ml_cold_start and n_samples > 0:
                    pass  # 静默跳过，样本不足时不训练

        if idx % 20 == 0:
            print(f"  progress: {day} ({idx+1}/{len(backtest_dates)})")

        # 该日的所有交易记录
        day_records = trading_by_date.get(day, [])

        # — 动态大佬排分（每N天重算）—
        if config.get("dynamic_ranking", False):
            recalc_days = config.get("ranking_recalc_days", 30)
            last_rank = getattr(run_backtest, "_last_rank_date", None)
            if not last_rank or (idx - last_rank) >= recalc_days or idx <= 1:
                dyn_weights = compute_player_rankings(
                    all_records, fund_charts, name_to_code, cutoff_full, config)
                run_backtest._last_rank_date = idx
                run_backtest._rank_weights = dyn_weights
                run_backtest._rank_excluded = {uid for uid, w in dyn_weights.items() if w == 0}
            player_weights = run_backtest._rank_weights
            exclude_uids = run_backtest._rank_excluded
        else:
            exclude_uids = set(str(u) for u in config.get("exclude_uids", []))
            player_weights = config.get("player_weights", {})
        fund_signals = defaultdict(lambda: {"buy_count": 0, "sell_count": 0, "weighted_buy": 0.0, "records": []})
        for r in day_records:
            uid = str(r.get("_uid", ""))
            if exclude_uids and uid in exclude_uids:
                continue
            fn = r.get("fund_name", "")
            act = r.get("action", "")
            weight = float(player_weights.get(uid, 1.0)) if player_weights else 1.0
            if "买入" in act:
                fund_signals[fn]["buy_count"] += 1
                fund_signals[fn]["weighted_buy"] += weight
            elif "卖出" in act:
                fund_signals[fn]["sell_count"] += 1
            fund_signals[fn]["records"].append(r)

        # 如果启用了加权，用加权后的买数替代原始买数
        use_weighted = config.get("use_weighted_consensus", False)
        for fn in fund_signals:
            if use_weighted:
                fund_signals[fn]["buy_count"] = max(1, int(fund_signals[fn]["weighted_buy"]))

        # 对该日有买入信号的基金评分
        candidates = []
        for fn, signal in fund_signals.items():
            if signal["buy_count"] < 2:  # 需要至少2人买入
                continue
            # 净信号过滤：买入必须多于卖出
            if config.get("net_signal", False) and signal["buy_count"] <= signal.get("sell_count", 0):
                continue
            # 找基金代码（三步模糊匹配：精确→标准化→包含）
            code = _resolve_fund_code(fn)
            if not code:
                continue

            cutoff = day  # 已经是 YYYY-MM-DD
            fs = score_fund_backtest(
                code, fn, fund_charts, None,
                fund_rules.get(code), fund_managers.get(code),
                cutoff, trading_by_date,
                fund_profiles.get(code),
                allocation_data=fund_holdings_data,
                fund_data_cache=fund_data_cache,
                industry_data=industry_data if industry_data else None,
            )
            ft = fund_profiles.get(code, {}).get("fund_type", "")
            is_active = "指数" not in ft and "QDII" not in ft
            is_passive = "指数" in ft and "增强" not in ft
            ftype_filter = config.get("fund_type_filter", "all")
            if ftype_filter == "active" and not is_active:
                continue  # 跳过非主动基金
            if ftype_filter == "passive" and not is_passive:
                continue  # 跳过非指数基金

            raw_score = fs.total
            # 费用惩罚（策略A）
            if config.get("cost_penalty", 0) > 0 and code in fund_rules:
                manage_fee = float(fund_rules[code].get("manage_fee", 0))
                if manage_fee > config["cost_penalty"]:
                    raw_score -= 0.3  # 高费率扣分

            # ── 技术择时过滤：RSI超买惩罚 + 均值回归奖励 + 趋势确认 ──
            # 融合QuantDinger的RSI/MACD/布林带算法，防止高位接盘
            if config.get("timing_filter", False):
                _timing = compute_entry_timing_score(
                    fund_charts.get(code, []), day)
                # 超买惩罚（RSI>70或布林带上轨突破）
                raw_score += _timing["overbought_penalty"]
                # 均值回归奖励（回调中买入且趋势向上）
                raw_score += _timing["mean_reversion_bonus"]
                # 趋势确认：下降趋势中降低评分
                if _timing["trend"] < 0:
                    raw_score -= config.get("downtrend_penalty", 0.5)
                # 严重超买直接跳过（RSI>80）
                if config.get("block_overbought", False) and _timing["should_warn"]:
                    scores_history.append({
                        "date": day, "code": code, "name": fn,
                        "score": round(raw_score, 2), "verdict": "block_overbought",
                        "rsi": _timing["rsi"],
                    })
                    continue

            # ── ML信号增强：用模型预测概率调整评分 ──
            if _ml_enabled and _ml_enhancer and _ml_enhancer.model:
                _ml_scores = {
                    "quality": fs.quality.score if fs.quality else 2.5,
                    "cost": fs.cost.score if fs.cost else 3.0,
                    "manager": fs.manager.score if fs.manager else 2.5,
                    "momentum": fs.momentum.score if fs.momentum else 2.5,
                    "smart_money": fs.smart_money.score if fs.smart_money else 2.5,
                    "total": fs.total,
                }
                _ml_prob = _ml_enhancer.predict(code, day, _ml_scores,
                                                signal["buy_count"], _market_state)
                if _ml_cold_start:
                    # ML冷启动期: 预测不可靠，给保守加分补偿
                    raw_score += _ml_cold_start_score_bonus
                else:
                    # 正常期: 概率>0.5加分，<0.5扣分
                    raw_score += (_ml_prob - 0.5) * _ml_weight

            # ── 收集ML训练数据（所有评分过的基金都记录）──
            if _ml_enabled:
                _ml_training_data.append((code, day, {
                    "quality": fs.quality.score if fs.quality else 2.5,
                    "cost": fs.cost.score if fs.cost else 3.0,
                    "manager": fs.manager.score if fs.manager else 2.5,
                    "momentum": fs.momentum.score if fs.momentum else 2.5,
                    "smart_money": fs.smart_money.score if fs.smart_money else 2.5,
                    "total": fs.total,
                }, signal["buy_count"], _market_state))

            # 共识门槛
            min_consensus = config.get("min_consensus", 2)
            if signal["buy_count"] < min_consensus:
                scores_history.append({
                    "date": day,
                    "code": code, "name": fn,
                    "score": round(raw_score, 2), "verdict": "skip_low_consensus",
                })
                continue

            # 限购感知：有限额的基金说明是热门，加分
            limit_boost = config.get("limit_boost", 0)
            if limit_boost > 0 and code in fund_rules:
                day_limit_val = fund_rules[code].get("day_limit", 0) or 0
                if day_limit_val and day_limit_val < 999999:
                    raw_score += limit_boost

            if raw_score >= _effective_min_score:
                limit = 0
                if code in fund_rules:
                    limit = fund_rules[code].get("day_limit", 0) or 0
                sector, is_qdii = detect_sector(fn, code, FUND_HOLDINGS_CACHE)
                candidates.append({
                    "code": code,
                    "name": fn,
                    "score": raw_score,
                    "buy_count": signal["buy_count"],
                    "day_limit": float(limit) if limit and limit != float('inf') else 999999,
                    "sector": sector,
                    "is_qdii": is_qdii,
                })
            scores_history.append({
                "date": day,
                "code": code, "name": fn,
                "score": round(raw_score, 2),
                "verdict": "pass" if raw_score < _effective_min_score else "candidate",
            })

        # 熊市趋势过滤：清空候选列表，当天不买入
        if _bear_no_buy and candidates:
            candidates = []

        # ── 相关性过滤：排除与已持仓基金高度相关的新基金 ──
        if _max_corr > 0 and candidates and portfolio.holdings:
            held_codes = list(portfolio.holdings.keys())
            filtered = []
            for c in candidates:
                max_c = check_max_correlation(c["code"], held_codes, _corr_matrix, _max_corr)
                if max_c > _max_corr:
                    # 高相关但评分显著更高（>0.5分）的仍可买入，但降低仓位
                    if c["score"] > max((s.get("score", 0) for s in filtered), default=0) + 0.5:
                        c["_corr_penalty"] = True  # 标记，在kelly分配时降低仓位
                        filtered.append(c)
                else:
                    filtered.append(c)
            if filtered:
                candidates = filtered

        # Top-N 过滤：按分数排序，只保留前N只
        top_n = config.get("top_n", 0)
        if top_n > 0 and len(candidates) > top_n:
            candidates.sort(key=lambda c: c["score"], reverse=True)
            candidates = candidates[:top_n]

        # Top-N% 过滤：按分数排序，只保留前N%
        top_n_pct = config.get("top_n_pct", 0)
        if top_n_pct > 0 and candidates:
            keep = max(1, int(len(candidates) * top_n_pct / 100))
            candidates.sort(key=lambda c: c["score"], reverse=True)
            candidates = candidates[:keep]

        # 共识优先：按买的人数排序，优先买共识高的
        if config.get("consensus_priority", False):
            candidates.sort(key=lambda c: c["buy_count"], reverse=True)

        # ── 行业分散过滤 ──
        max_sector_pct = config.get("max_sector_pct", 100)
        max_qdii_pct = config.get("max_qdii_pct", 100)
        if max_sector_pct < 100 or max_qdii_pct < 100:
            # 计算当前持仓行业分布（使用实际市场价值）
            total_val = portfolio.value(fund_prices) or 1
            sector_vals = {}
            qdii_val = 0
            for code, h in portfolio.holdings.items():
                hfn = h.get("name", "")
                hsec, hqdii = detect_sector(hfn)
                val = h["shares"] * fund_prices.get(code, h.get("buy_nav", 1.0))
                sector_vals[hsec] = sector_vals.get(hsec, 0) + val
                if hqdii: qdii_val += val

            filtered = []
            for c in candidates:
                sec = c.get("sector", "其他")
                est = 1000  # 假设每笔买入约1000元
                cur_pct = sector_vals.get(sec, 0) / total_val * 100
                cur_q = qdii_val / total_val * 100
                if cur_pct + (100 / total_val * 100 if total_val > 0 else 10) > max_sector_pct:
                    continue
                if cur_q + (100 / total_val * 100 if total_val > 0 else 10) > max_qdii_pct:
                    continue
                filtered.append(c)
            if filtered: candidates = filtered

        # 每月首个交易日注入工资（如果启用）
        monthly_amount = config.get("monthly_injection", 0)
        if monthly_amount > 0:
            # 检测是否是新月份的第一个交易日
            current_month = day[5:7]  # YYYY-MM-DD -> MM
            if idx == 0 or backtest_dates[idx-1][:7] != day[:7]:
                portfolio.inject_cash(monthly_amount, cutoff_full)
                print(f"  SALARY +{monthly_amount} on {cutoff_full}")

        # 重新评分已持仓的基金（判断是否需要卖出）
        for code in list(portfolio.holdings.keys()):
            h = portfolio.holdings[code]
            pts = fund_charts.get(code, [])
            if not pts:
                continue

            # 用当天的 chart_data 算累计收益
            valid = [p for p in pts if p.get("xAxis", "") <= cutoff_full]
            if not valid:
                continue
            y = _float(valid[-1].get("yAxis", 0))
            current_nav = (100 + y) / 100
            buy_nav = h.get("buy_nav", 1.0)
            cum_return = (current_nav / buy_nav - 1) * 100 if buy_nav > 0 else 0

            # 追踪最高净值（用于最大回撤止盈和移动止损）
            if "peak_nav" not in h or current_nav > h["peak_nav"]:
                h["peak_nav"] = current_nav
            peak_nav = h["peak_nav"]
            drawdown_from_peak = (current_nav / peak_nav - 1) * 100 if peak_nav > 0 else 0

            # 动量分
            mom = score_momentum_backtest(pts, cutoff_full)

            sell_price = fund_prices.get(code, current_nav)
            sell_reason = ""
            should_sell = False

            tp_pct = config.get("take_profit_pct", 30)
            tp_sell = config.get("take_profit_sell_pct", 0.5)
            sl_pct = config.get("stop_loss_pct", -15)
            mom_sell = config.get("momentum_sell", 2.0)
            max_pos = _dyn_max_pos

            # 🔴 止损: 亏损超过阈值（指数型或配置了no_stop_loss则跳过）
            no_sl = config.get("no_stop_loss", False)
            if not no_sl and cum_return < sl_pct:
                should_sell = True
                sell_reason = f"stop_loss {cum_return:.1f}%"

            # 🟢 止盈: 收益超过阈值
            profit_mode = config.get("profit_mode", "half")
            if cum_return > tp_pct and code in portfolio.holdings:
                sell_value = h["shares"] * sell_price
                if profit_mode == "all":
                    sell_amt = sell_value
                elif profit_mode == "quarter":
                    sell_amt = sell_value * 0.25
                elif profit_mode == "step":
                    # 阶梯止盈: 每多赚15%就卖一部分
                    steps = int((cum_return - tp_pct) / 15)
                    step_sell = {0: 0.5, 1: 0.5, 2: 0.3, 3: 0.2}
                    sell_frac = step_sell.get(min(steps, 3), 0.1)
                    sell_amt = sell_value * sell_frac
                else:  # "half" 或其他，卖一半
                    sell_amt = sell_value * tp_sell
                if sell_amt >= 100:
                    portfolio.sell(code, sell_amt, sell_price, cutoff_full,
                                  sell_reason=f"take_profit {cum_return:.1f}%")
                    print(f"  SELL_TP {code} {h['name'][:16]} profit={cum_return:.1f}% amt={sell_amt:.0f}")
                    continue

            # 🟢 移动止盈: 盈利达到激活阈值后，从最高点回撤超过阈值则卖出锁利
            # 与 peak_drawdown_exit 的区别：只在盈利状态下触发，避免亏损时误卖
            trailing_tp_activate = config.get("trailing_tp_activate", 0)
            trailing_tp_dd = config.get("trailing_tp_drawdown", 10)
            if trailing_tp_activate > 0 and cum_return >= trailing_tp_activate and drawdown_from_peak < -trailing_tp_dd:
                should_sell = True
                sell_reason = f"trailing_tp profit={cum_return:.1f}% dd={drawdown_from_peak:.1f}%"

            # 大佬卖出信号：跟大佬卖
            sell_consensus = config.get("sell_consensus", 0)
            if sell_consensus > 0:
                fn = portfolio.holdings[code].get("name", "")
                if fn and fn in fund_signals:
                    sc = fund_signals[fn]["sell_count"]
                    if sc >= sell_consensus:
                        should_sell = True
                        sell_reason = f"big_sell {sc}人"

            # 🔴 动量崩溃: 动量分低于阈值
            if mom.score < mom_sell:
                should_sell = True
                sell_reason = f"momentum_crash mom={mom.score:.2f}"

            # 🔴 最大回撤止盈: 从最高点回撤X%即卖出
            peak_dd_exit = config.get("peak_drawdown_exit", 0)
            if peak_dd_exit > 0 and drawdown_from_peak < -peak_dd_exit:
                should_sell = True
                sell_reason = f"peak_dd {drawdown_from_peak:.1f}%"

            # 🟡 回撤减半: 从最高点回撤超过阈值但未到清仓线，先卖一半锁利
            peak_dd_reduce = config.get("peak_drawdown_reduce", 0)
            if peak_dd_reduce > 0 and drawdown_from_peak < -peak_dd_reduce and code in portfolio.holdings:
                sell_value = h["shares"] * sell_price * 0.5
                if sell_value >= 100:
                    portfolio.sell(code, sell_value, sell_price, cutoff_full,
                                  sell_reason=f"peak_dd_reduce {drawdown_from_peak:.1f}%")
                    print(f"  SELL_HALF {code} {h['name'][:16]} dd={drawdown_from_peak:.1f}% amt={sell_value:.0f}")
                    # 记录到买回追踪列表
                    _buy_back_watchlist[code] = {
                        "name": h.get("name", ""),
                        "sell_date": cutoff_full,
                        "sell_nav": current_nav,
                        "reason": "peak_dd_reduce",
                    }

            # 🔴 移动止损: 止损线随最高点上移
            trail_stop = config.get("trailing_stop_pct", 0)
            if trail_stop > 0 and drawdown_from_peak < -trail_stop:
                should_sell = True
                sell_reason = f"trail_stop {drawdown_from_peak:.1f}%"

            # 🔵 仓位过重: 单只超过阈值，减到标准仓位
            total_value = portfolio.value(fund_prices)
            if total_value > 0 and code in portfolio.holdings:
                fund_value = h["shares"] * sell_price
                pct = fund_value / total_value * 100
                if pct > max_pos:
                    target_val = total_value * (max_pos * 0.6 / 100)
                    sell_val = fund_value - target_val
                    if sell_val > 0:
                        portfolio.sell(code, sell_val, sell_price, cutoff_full,
                                      sell_reason=f"reduce_pos {pct:.0f}%->{max_pos*0.6:.0f}%")
                        print(f"  SELL_REDUCE {code} {h['name'][:16]} {pct:.0f}%->{max_pos*0.6:.0f}% amt={sell_val:.0f}")
                        continue

            if should_sell:
                portfolio.sell(code, 0, sell_price, cutoff_full, sell_reason, force_sell=True)
                print(f"  SELL {code} {h['name'][:16]} {sell_reason} proceeds={h['shares']*sell_price:.0f}")
                # 记录到买回追踪列表（止损/回撤清仓的基金等企稳后可买回）
                _buy_back_watchlist[code] = {
                    "name": h.get("name", ""),
                    "sell_date": cutoff_full,
                    "sell_nav": current_nav,
                    "reason": sell_reason,
                }

        # ── 季度再平衡：每60天检查行业超配，卖超配行业中表现最差的 ──
        rebalance = config.get("rebalance", False)
        if rebalance and idx > 0 and idx % 60 == 0:
            max_sec = config.get("max_sector_pct", 100)
            if max_sec < 100:
                total_val = portfolio.value(fund_prices) or 1
                sec_vals = {}
                for code, h in list(portfolio.holdings.items()):
                    hfn = h.get("name","")
                    hsec, _ = detect_sector(hfn)
                    price = fund_prices.get(code, 1.0)
                    sec_vals[hsec] = sec_vals.get(hsec, 0) + h["shares"] * price
                for sec, val in sec_vals.items():
                    pct = val / total_val * 100
                    if pct > max_sec:
                        # 找到该行业中表现最差的基金
                        worst_code = None
                        worst_ret = 999
                        for code, h in list(portfolio.holdings.items()):
                            hfn = h.get("name","")
                            hsec, _ = detect_sector(hfn)
                            if hsec != sec: continue
                            pts = fund_charts.get(code, [])
                            if not pts: continue
                            valid = [p for p in pts if p.get("xAxis","") <= cutoff_full]
                            if not valid: continue
                            y = _float(valid[-1].get("yAxis",0))
                            nav = (100 + y) / 100
                            ret = (nav / h.get("buy_nav",1) - 1) * 100
                            if ret < worst_ret:
                                worst_ret = ret
                                worst_code = code
                        if worst_code:
                            sp = fund_prices.get(worst_code, 1.0)
                            sell_val = portfolio.holdings[worst_code]["shares"] * sp * 0.5
                            if sell_val >= 100:
                                portfolio.sell(worst_code, sell_val, sp, cutoff_full,
                                              sell_reason=f"rebalance {sec} {pct:.0f}%>{max_sec}%")
                                print(f"  REBALANCE {worst_code} {portfolio.holdings[worst_code]['name'][:16]} {sec} {pct:.0f}%>{max_sec}%")

        # 资金分配（使用可配置参数）
        # 板块热度检测: 如果某个板块的候选基金特别多且评分高, 允许提高集中度
        if len(candidates) >= 2:
            _sector_scores = {}
            _sector_counts = {}
            for _c in candidates:
                _sec = _c.get("sector", "其他")
                _sector_scores[_sec] = _sector_scores.get(_sec, 0) + _c["score"]
                _sector_counts[_sec] = _sector_counts.get(_sec, 0) + 1
            if _sector_scores:
                _hot_sector = max(_sector_scores, key=_sector_scores.get)
                _hot_score = _sector_scores[_hot_sector]
                _hot_count = _sector_counts[_hot_sector]
                # 最热板块的基金允许更高上限
                _sector_bonus = 1.3 if _hot_count >= 2 and _hot_score > 8 else 1.0
            else:
                _sector_bonus = 1.0
        else:
            _sector_bonus = 1.0

        # Apply sector bonus to candidate max_pos
        _capped_max_pos = min(_dyn_max_pos * _sector_bonus, 50)  # cap at 50% absolute
        for _c in candidates:
            if _sector_bonus > 1.0 and _c.get("sector", "") == _hot_sector:
                _c["_max_pos_override"] = _capped_max_pos

        # ── 企稳买回：之前因回撤/止损卖出的基金，RSI回落+趋势向上时重新买入 ──
        if config.get("enable_buy_back", False) and _buy_back_watchlist:
            buy_back_rsi = config.get("buy_back_rsi_max", 50)
            buy_back_min_days = config.get("buy_back_min_days", 5)  # 至少等5天再买回
            for bb_code in list(_buy_back_watchlist.keys()):
                bb = _buy_back_watchlist[bb_code]
                # 已重新持仓则从追踪列表移除
                if bb_code in portfolio.holdings:
                    del _buy_back_watchlist[bb_code]
                    continue
                # 冷却期检查
                try:
                    from datetime import datetime as _dt
                    sell_dt = _dt.strptime(bb["sell_date"][:10], "%Y-%m-%d")
                    cur_dt = _dt.strptime(cutoff_full[:10], "%Y-%m-%d")
                    if (cur_dt - sell_dt).days < buy_back_min_days:
                        continue
                except:
                    pass
                # 检查RSI和趋势
                bb_pts = fund_charts.get(bb_code, [])
                if not bb_pts:
                    continue
                bb_timing = compute_entry_timing_score(bb_pts, cutoff_full)
                if bb_timing["rsi"] < buy_back_rsi and bb_timing["trend"] > 0:
                    # 企稳，加入候选列表
                    bb_name = bb.get("name", "")
                    sector, is_qdii = detect_sector(bb_name, bb_code, FUND_HOLDINGS_CACHE)
                    candidates.append({
                        "code": bb_code,
                        "name": bb_name,
                        "score": config.get("min_score", 3.3) - 0.3,  # 买回门槛降低0.3
                        "buy_count": 1,
                        "day_limit": 999999,
                        "sector": sector,
                        "is_qdii": is_qdii,
                        "_buy_back": True,
                    })
                    print(f"  BUY_BACK_SIGNAL {bb_code} {bb_name[:16]} RSI={bb_timing['rsi']:.0f} trend=UP")

        to_buy = kelly_allocate(candidates, portfolio.cash + sum(
            h["shares"] * fund_prices.get(code, h.get("buy_nav", 1.0))
            for code, h in portfolio.holdings.items()),
            kelly_cap=config.get("kelly_cap", 0.2),
            cash_reserve=_dyn_cash_reserve,
            max_pos=_dyn_max_pos / 100)
        for c in to_buy:
            # 最大持仓数限制
            max_holdings = config.get("max_holdings", 0)
            if max_holdings > 0 and len(portfolio.holdings) >= max_holdings:
                print(f"  SKIP_BUY {c['code']} {c['name'][:16]} max_holdings={max_holdings}")
                continue
            # 冷却期检查：刚卖出的基金短期内不重新买入（减少反复交易和手续费）
            # 止盈卖出的冷却期短（默认profit_days），止损/动量崩溃的冷却期长（默认loss_days×2）
            # 这同时实现了"再入场机制"：止盈后基金再次走强可较快重新买入
            if _cooldown_cfg and portfolio.is_in_cooldown(c["code"], day, _cooldown_cfg):
                continue
            # 已持仓的基金不重复买入（加仓通过单独逻辑处理）
            if c["code"] in portfolio.holdings:
                continue
            # 计算实际买入净值
            buy_price = 1.0
            pts = fund_charts.get(c["code"], [])
            if pts:
                cutoff_full = day
                valid = [p for p in pts if p.get("xAxis", "") <= cutoff_full]
                if valid:
                    y = _float(valid[-1].get("yAxis", 0))
                    buy_price = (100 + y) / 100
            portfolio.buy(c["code"], c["name"], c["_suggested"], price=buy_price,
                         day_str=day)

        # 记录每日净值
        # Compute NAV from chart data for held funds
        fund_prices = {}
        cutoff_full = day
        for code in portfolio.holdings:
            pts = fund_charts.get(code, [])
            if not pts:
                continue
            # 取截止到当天的最后一条净值
            valid = [p for p in pts if p.get("xAxis", "") <= cutoff_full]
            if valid:
                y = _float(valid[-1].get("yAxis", 0))
                fund_prices[code] = (100 + y) / 100  # 净值 ≈ 1 + 累计收益率

        portfolio.snapshot(cutoff_full, fund_prices)

        # ── 结果 ──
    final_value = portfolio.daily_values[-1]["total"] if portfolio.daily_values else portfolio.value()
    total_invested = config["initial_cash"] + portfolio.monthly_injections
    total_return = (final_value - total_invested) / total_invested * 100 if total_invested > 0 else 0

    # 计算最大回撤
    values = [d["total"] for d in portfolio.daily_values]
    peak = values[0] if values else 1
    max_dd = 0
    for v in values[1:]:
        if v > peak: peak = v
        if peak > 0:
            dd = (peak - v) / peak * 100
            if dd > max_dd: max_dd = dd

    # ── 风险调整后收益指标 ──
    # 日收益率序列
    daily_returns = []
    for i in range(1, len(values)):
        if values[i-1] > 0:
            daily_returns.append((values[i] - values[i-1]) / values[i-1])

    # 年化收益率（假设252个交易日/年）
    num_trading_days = len(values)
    annualized_return = 0.0
    if num_trading_days > 1 and total_invested > 0:
        total_ret_ratio = final_value / total_invested
        annualized_return = (total_ret_ratio ** (252.0 / num_trading_days) - 1) * 100

    # 年化波动率
    annualized_volatility = 0.0
    if len(daily_returns) > 1:
        avg_daily = sum(daily_returns) / len(daily_returns)
        variance = sum((r - avg_daily) ** 2 for r in daily_returns) / (len(daily_returns) - 1)
        annualized_volatility = (variance ** 0.5) * (252 ** 0.5) * 100

    # 夏普比率 = (年化收益 - 无风险利率) / 年化波动率
    sharpe_ratio = 0.0
    if annualized_volatility > 0:
        sharpe_ratio = (annualized_return - RISK_FREE_RATE * 100) / annualized_volatility

    # 卡玛比率 = 年化收益 / 最大回撤
    calmar_ratio = 0.0
    if max_dd > 0:
        calmar_ratio = annualized_return / max_dd



    # 沪深300 benchmark（用 110020 易方达沪深300ETF联接 的 chart_data）
    benchmark_return = 0
    benchmark_dd = 0
    benchmark_code = "110020"
    bm_pts = fund_charts.get(benchmark_code, [])
    if bm_pts:
        bm_start_date = config["start_date"]
        bm_end_date = config["end_date"]
        bm_start = None
        bm_end = None
        for p in bm_pts:
            if p.get("xAxis", "") == bm_start_date:
                bm_start = _float(p.get("yAxis", 0))
            if p.get("xAxis", "") == bm_end_date:
                bm_end = _float(p.get("yAxis", 0))
        # 如果没找到精确匹配，取最近的点
        if bm_start is None and bm_pts:
            for p in bm_pts:
                if p.get("xAxis", "") >= bm_start_date:
                    bm_start = _float(p.get("yAxis", 0))
                    break
            if bm_start is None:
                bm_start = _float(bm_pts[-1].get("yAxis", 0))
        if bm_end is None and bm_pts:
            for p in reversed(bm_pts):
                if p.get("xAxis", "") <= bm_end_date:
                    bm_end = _float(p.get("yAxis", 0))
                    break
            if bm_end is None:
                bm_end = _float(bm_pts[-1].get("yAxis", 0))
        if bm_start is not None and bm_end is not None:
            benchmark_return = ((100 + bm_end) / (100 + bm_start) - 1) * 100

    # Buy-and-hold baseline: 第一天全仓评分最高的基金
    bh_return = 0
    bh_dd = 0
    bh_code = ""
    if scores_history:
        top_score = max([s for s in scores_history if s["date"].startswith("2026-01")], key=lambda x: x["score"]) if any(s["date"].startswith("2026-01") for s in scores_history) else max(scores_history, key=lambda x: x["score"])
        bh_code = top_score["code"]
        bh_pts = fund_charts.get(bh_code, [])
        if bh_pts:
            bh_start_val = None
            bh_end_val = None
            bms = config["start_date"]
            bme = config["end_date"]
            for p in bh_pts:
                if p.get("xAxis", "") == bms: bh_start_val = _float(p.get("yAxis", 0))
                if p.get("xAxis", "") == bme: bh_end_val = _float(p.get("yAxis", 0))
            if bh_start_val is not None and bh_end_val is not None:
                bh_return = ((100 + bh_end_val) / (100 + bh_start_val) - 1) * 100

    # 交易次数
    trade_count = len(portfolio.trades)
    final_holdings = len(portfolio.holdings)

    print(f"\n{'='*50}")
    print(f"回测结果")
    print(f"{'='*50}")
    print(f"Initial: {config['initial_cash']:,.0f}")
    print(f"Final: {final_value:,.2f}")
    print(f"Return: {total_return:+.2f}%")
    print(f"MaxDD: {max_dd:.2f}%")
    print(f"Trades: {trade_count}")
    print(f"Holdings: {final_holdings}")
    print(f"Benchmark CSI300: {benchmark_return:+.2f}%")
    print(f"BuyHold({bh_code}): {bh_return:+.2f}%")
    print(f"Scores: {len(scores_history)}")
    print(f"Annualized: {annualized_return:+.2f}%")
    print(f"Volatility: {annualized_volatility:.2f}%")
    print(f"Sharpe: {sharpe_ratio:.2f}")
    print(f"Calmar: {calmar_ratio:.2f}")
    print(f"Fees: {portfolio.total_fees:.2f}")

    return {
        "config": config,
                "final_value": final_value,
        "total_return": total_return,
        "max_drawdown": max_dd,
        "annualized_return": round(annualized_return, 2),
        "annualized_volatility": round(annualized_volatility, 2),
        "sharpe_ratio": round(sharpe_ratio, 2),
        "calmar_ratio": round(calmar_ratio, 2),
        "benchmark_return": benchmark_return,
        "benchmark_dd": benchmark_dd,
        "buyhold_return": bh_return,
        "buyhold_code": bh_code,
        "trade_count": trade_count,
        "final_holdings": final_holdings,
        "total_fees": round(portfolio.total_fees, 2),
        "monthly_injections": portfolio.monthly_injections,
        "daily_values": portfolio.daily_values,
        "trades": portfolio.trades,
        "scores": scores_history,
    }