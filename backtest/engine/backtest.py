#!/usr/bin/env python3
"""回测引擎：无未来函数，纯数据驱动。

核心原则：
1. 对每个日期 T，只用 T 之前的数据计算评分
2. chart_data 按日期截断（只取 xAxis ≤ T 的点）
3. 交易记录按日期截断（只取 _date_prefix ≤ T）
4. 费率、经理数据用当前值（变化极慢，可接受）
"""
import json, math, statistics, sys, os, bisect
from pathlib import Path
from datetime import datetime, date
from collections import defaultdict
from typing import Optional

# ── 速度优化：bisect 二分查找代替线性截断 ──
# 预处理时为每只基金缓存 dates 数组, id(pts)→dates
_DATES_CACHE = {}
_TRADING_DATES_SORTED = []  # 预排序的 trading_by_date keys

def _bisect_valid(pts, cutoff_date):
    """用 bisect 快速截断已排序的 chart_points。pts 必须按 xAxis 升序排列。"""
    if not pts:
        return []
    pid = id(pts)
    dates = _DATES_CACHE.get(pid)
    if dates is None:
        dates = [p.get("xAxis", "") for p in pts]
        _DATES_CACHE[pid] = dates
    pos = bisect.bisect_right(dates, cutoff_date)
    return pts[:pos] if pos > 0 else []

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
# 长周期技术指标（周线MACD背离/年线/周线布林带）
from tools.technical_indicators import compute_macd_divergence, compute_weekly_bollinger, compute_ma_250
from tools.technical_indicators import compute_kdj, compute_kdj_series, detect_momentum_acceleration

# 市场风险预警系统（方案B）
try:
    from tools.market_risk import compute_market_risk
    MARKET_RISK_AVAILABLE = True
except ImportError:
    MARKET_RISK_AVAILABLE = False

# 市场方向预测 — Transformer（方案C）
try:
    from tools.market_predictor import MarketPredictor, build_feature_sequence, _to_nav as mp_to_nav
    MARKET_PREDICTOR_AVAILABLE = True
except ImportError:
    MARKET_PREDICTOR_AVAILABLE = False

# 市场方向预测 — LightGBM（方案V，CPU秒级训练）
try:
    from tools.lgb_predictor import LGBMarketPredictor
    LGB_PREDICTOR_AVAILABLE = True
except Exception:
    LGB_PREDICTOR_AVAILABLE = False

RISK_FREE_RATE = 0.025
PURCHASE_DISCOUNT = 0.1


# ── 日期感知的评分 ──

def score_momentum_backtest(chart_points, cutoff_date):
    """用截止到 cutoff_date 的 chart_data 计算动量分。
    chart_points: [{xAxis: "2026-01-15", yAxis: 5.23}, ...]
    cutoff_date: "2026-03-15"
    只使用 xAxis ≤ cutoff_date 的点。
    """
    valid = _bisect_valid(chart_points, cutoff_date)
    if len(valid) < 20:
        return DimensionScore(score=-1, weight=0, freshness_days=0)

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
    valid = _bisect_valid(chart_points, cutoff_date)
    if len(valid) < 20:
        return DimensionScore(score=-1, weight=0, freshness_days=0)

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
    # 用 bisect 在预排序的 dates 中截断（速度优化）
    if _TRADING_DATES_SORTED:
        pos = bisect.bisect_right(_TRADING_DATES_SORTED, cutoff_date)
        sorted_dates = _TRADING_DATES_SORTED[:pos]
    else:
        sorted_dates = sorted(d for d in trading_by_date if d <= cutoff_date)

    def _match(record):
        """匹配: fund_code 精确匹配 → fund_name 精确匹配"""
        if fund_code and record.get("fund_code") == fund_code:
            return True
        if record.get("fund_name", "") == fund_name:
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
    valid = _bisect_valid(pts, cutoff_date)
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
    valid = _bisect_valid(chart_points, cutoff_date)
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
        valid = _bisect_valid(pts, cutoff_date)
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


# ── 4433法则评分（investool参考集成）──
def score_4433(fund_code, cutoff_date, fund_charts):
    """4433法则: 基于排名筛选基金。
    规则:
      - 近1年排名前1/4
      - 近2/3/5年排名前1/4
      - 近6月排名前1/3
      - 近3月排名前1/3
    返回: 修正值 (正=加分, 负=扣分), 通过数
    """
    pts = fund_charts.get(fund_code, [])
    valid = _bisect_valid(pts, cutoff_date)
    if len(valid) < 63:  # 至少3个月数据
        return 0.0, 0

    # yAxis=累计收益率% → 净值化: nav = (100 + yAxis) / 100
    yaxis_raw = [float(p.get("yAxis", 0)) for p in valid]
    navs = [(100 + v) / 100 for v in yaxis_raw]
    cur_nav = navs[-1]
    n = len(navs)

    periods = {
        "3mo": (63, 0.33),
        "6mo": (126, 0.33),
    }

    rets = {}
    for name, (days, _) in periods.items():
        if n > days:
            start_nav = navs[-days]
            rets[name] = (cur_nav - start_nav) / start_nav * 100
        else:
            rets[name] = None

    # 排名
    all_rets = {}
    for code, pts_all in fund_charts.items():
        v_raw = [float(p.get("yAxis", 0)) for p in pts_all if p.get("xAxis", "") <= cutoff_date]
        if len(v_raw) < 252:
            continue
        v_nav = [(100 + v) / 100 for v in v_raw]
        cv_nav = v_nav[-1]
        for name, (days, _) in periods.items():
            if len(v_nav) > days:
                sv_nav = v_nav[-days]
                r = (cv_nav - sv_nav) / sv_nav * 100
                all_rets.setdefault(name, []).append((code, r))

    passes = 0
    for name, (days, threshold) in periods.items():
        fund_ret = rets.get(name)
        if fund_ret is None:
            continue
        others = sorted(all_rets.get(name, []), key=lambda x: x[1], reverse=True)
        total = len(others)
        if total < 10:
            continue
        rank = sum(1 for _, r in others if r > fund_ret) + 1
        pct = rank / total
        if pct <= threshold:
            passes += 1

    # 得分: 3个通过=加分, 1个以下=扣分
    if passes >= 3:
        return 0.5 * passes, passes
    elif passes <= 1:
        return -0.5, passes
    return 0.0, passes


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
        if not (mgr.get("managers") or []):
            _mgr_missing = True
    else:
        _mgr_missing = True

    if _mgr_missing:
        # 经理数据缺失时降低该维度权重（0.20→0.05），避免用默认值干扰总分
        # 剩余权重按比例分配给其他维度
        manager_dim = DimensionScore(score=-1, weight=0, freshness_days=0)

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

    # ===== 新增: 4433法则评分 =====
    if charts:
        s4433, p4433 = score_4433(fund_code, cutoff_date, charts)
        total_modifier += s4433

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
        self._min_holding_days = 60  # 60天最低持有（减少交易频率）
        self.yearly_trades = {}  # {year: count}
        self.max_yearly_trades = 50  # annual trade cap (可被config覆盖)
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
        """获取基金的实际申购费率。
        京东API返回的 purchase_fee 是百分比值（如 0.15 表示 0.15%，1.5 表示 1.5%），
        且已是渠道打折后的实际费率。统一除以100转为小数。
        """
        rules = self.fund_rules.get(code, {})
        pf = rules.get("purchase_fee", default_purchase_fee * 100)
        if isinstance(pf, str):
            try: pf = float(pf.replace("%","").strip())
            except: pf = default_purchase_fee * 100
        return float(pf) / 100  # 0.15→0.0015, 1.5→0.015

    def get_redeem_fee(self, code, days_held):
        """获取基金的实际赎回费率。
        京东API返回的 rate 是百分比值（如 1.5 表示 1.5%），统一除以100转小数。
        interval 格式多样，用正则提取数字统一解析：
          "<7天" / "持有期限<7天"  → [0, 7)
          "7-365天" / "7天≤持有期限<365天" → [7, 365)
          ">365天" / "持有期限≥365天" → [365, ∞)
        """
        import re as _re
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
            rate = float(tier.get("rate", 0)) / 100  # 百分比→小数
            # 提取所有数字
            nums = [int(x) for x in _re.findall(r'\d+', interval)]
            if not nums:
                continue
            # 判断区间类型
            has_lower = any(c in interval for c in ["≥", ">", "≥"])
            has_dash = "-" in interval and len(nums) == 2
            if has_dash:
                # "7-365天" 格式
                low, high = nums[0], nums[1]
                if low <= days_held < high:
                    return rate
            elif len(nums) == 2:
                # "7天≤持有期限<365天" 格式
                low, high = nums[0], nums[1]
                if low <= days_held < high:
                    return rate
            elif has_lower or (len(nums) == 1 and (">" in interval or "≥" in interval)):
                # ">365天" / "≥365天" 格式
                if days_held >= nums[0]:
                    return rate
            elif len(nums) == 1:
                # "<7天" 格式
                if days_held < nums[0]:
                    return rate
        return 0.0

    def get_t_plus_n(self, code):
        """获取基金T+N确认天数"""
        rules = self.fund_rules.get(code, {})
        confirm = rules.get("confirm_date", "")
        buy_date = rules.get("buy_date", "")
        # 用完整日期解析，避免跨月错误
        if confirm and buy_date:
            try:
                from datetime import datetime
                # confirm_date 格式如 "07-08", buy_date 格式如 "07-06 15:00前"
                # 补全年份用当前年，只算日历差
                _year = datetime.now().year
                b_str = buy_date.split(" ")[0]  # "07-06"
                b_dt = datetime.strptime(f"{_year}-{b_str}", "%Y-%m-%d")
                c_dt = datetime.strptime(f"{_year}-{confirm}", "%Y-%m-%d")
                diff = (c_dt - b_dt).days
                if diff <= 1: return 1  # T+1
                if diff <= 2: return 2  # T+2
                return diff
            except: pass
        # 根据基金类型判断
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
        # 年交易次数上限检查
        _yr = day_str[:4] if len(day_str) >= 4 else "0000"
        if self.yearly_trades.get(_yr, 0) >= self.max_yearly_trades:
            return False  # 本年交易次数已达上限
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

def kelly_allocate(candidates, total_cash, kelly_cap=0.2, cash_reserve=0.2, max_pos=0.15, market_discount=1.0, kelly_fraction=0.5, max_single_buy_pct=0.30, equal_allocate=False):
    """凯利分配。kelly_fraction控制凯利系数(0.5=半凯利, 1.0=全凯利)。
    market_discount: 长周期调整因子（默认1.0，顶背离×0.7、布帶上轨×0.8等）
    equal_allocate: True=等额分配(不按评分差异化), False=凯利差异化分配
    
    改进：限额感知的资金重分配。当一个基金因day_limit只能买少量时，
    把剩余资金重新分配给后续无限额或限额充足的基金，避免现金闲置。
    """
    available = total_cash * (1 - cash_reserve) * market_discount
    if equal_allocate:
        # 等额分配：每只基金分配 available / N，受max_pos和max_single_buy_pct上限
        _n = max(len(candidates), 1)
        _per = available / _n
        for c in candidates:
            suggested = _per
            if c["day_limit"] and c["day_limit"] < 999999:
                suggested = min(suggested, c["day_limit"])
            _eff_max_pos = c.get("_max_pos_override", max_pos * 100) / 100
            suggested = min(suggested, total_cash * _eff_max_pos)
            suggested = min(suggested, available * max_single_buy_pct)
            suggested = round(suggested / 100) * 100
            c["_suggested"] = suggested
            c["_raw_suggested"] = suggested
            c["_capped_by_limit"] = False
    else:
        for c in candidates:
            p = c["score"] / 5.0
            b = max(p * 2, 0.5)
            kelly = max(0, min((p * b - (1 - p)) / b, kelly_cap))
            # 凯利分数: kelly_fraction=0.5半凯利, 1.0全凯利
            kelly = kelly * kelly_fraction
            suggested = available * kelly * c["score"] / 5.0
            _raw_suggested = suggested  # 限额截断前的原始建议金额
            if c["day_limit"] and c["day_limit"] < 999999:
                suggested = min(suggested, c["day_limit"])
            # 硬上限: 单只基金不超过总资产max_pos%, 单次不超过可用现金max_single_buy_pct
            _eff_max_pos = c.get("_max_pos_override", max_pos * 100) / 100  # 支持 sector bonus 覆盖
            suggested = min(suggested, total_cash * _eff_max_pos)  # max_pos 默认0.15=15%
            suggested = min(suggested, available * max_single_buy_pct)  # 单次不超过可用现金max_single_buy_pct
            suggested = round(suggested / 100) * 100
            c["_suggested"] = suggested
            c["_raw_suggested"] = round(_raw_suggested / 100) * 100  # 保存原始建议（限额截断前）
            c["_capped_by_limit"] = _raw_suggested > suggested + 100  # 是否被限额截断

    candidates.sort(key=lambda x: x["score"], reverse=True)
    allocated = 0
    results = []
    # 第一轮：按分数顺序分配，记录被限额截断的剩余资金
    capped_surplus = 0  # 被限额截断的总剩余资金
    for c in candidates:
        if allocated >= available or c["_suggested"] < 100:
            continue
        if allocated + c["_suggested"] > available:
            c["_suggested"] = round((available - allocated) / 100) * 100
        if c["_suggested"] < 100:
            continue
        allocated += c["_suggested"]
        # 如果被限额截断，记录剩余资金用于第二轮重分配
        if c["_capped_by_limit"] and c["_raw_suggested"] > c["_suggested"]:
            capped_surplus += c["_raw_suggested"] - c["_suggested"]
        results.append(c)

    # 第二轮：限额感知的资金重分配（把被截断的资金分给无限额的高分基金）
    if capped_surplus > 100:
        for c in results:
            if capped_surplus < 100:
                break
            # 只给无限额或限额充足的基金加仓
            if c["day_limit"] and c["day_limit"] < 999999:
                remaining_limit = c["day_limit"] - c["_suggested"]
                if remaining_limit < 100:
                    continue
                extra = min(capped_surplus, remaining_limit)
            else:
                _eff_max_pos = c.get("_max_pos_override", max_pos * 100) / 100
                hard_cap = total_cash * _eff_max_pos
                remaining_cap = hard_cap - c["_suggested"]
                if remaining_cap < 100:
                    continue
                extra = min(capped_surplus, remaining_cap)
            extra = round(extra / 100) * 100
            if extra >= 100:
                c["_suggested"] += extra
                capped_surplus -= extra
                allocated += extra
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

    # 为交易记录补充 fund_code（基于 name_map）
    _name_map_path = PROJECT_DIR / "data" / "fund_name_map.json"
    _name_to_code = {}
    if _name_map_path.exists():
        _name_to_code = json.loads(_name_map_path.read_text("utf-8"))
    for date in trading_by_date:
        for r in trading_by_date[date]:
            if r.get("fund_code"):
                continue
            name = r.get("fund_name", "")
            if name in _name_to_code:
                r["fund_code"] = _name_to_code[name]

    hist_file = DATA_DIR / "trading_history_fixed.json"
    if not hist_file.exists():
        hist_file = DATA_DIR / "trading_history.json"
    with open(hist_file, "r", encoding="utf-8") as f:
        all_records = json.load(f)

    from tools.chart_loader import load_all_charts
    fund_charts = load_all_charts()
    print(f"[DATA] 加载 {len(fund_charts)} 只基金净值数据")

    # ── 速度优化预处理：排序 fund_charts + 预排序 trading_by_date keys ──
    _DATES_CACHE.clear()
    for _code in fund_charts:
        if fund_charts[_code]:
            fund_charts[_code].sort(key=lambda p: p.get("xAxis", ""))
    global _TRADING_DATES_SORTED
    _TRADING_DATES_SORTED = sorted(trading_by_date.keys())
    print(f"  [优化] chart排序完成({len(fund_charts)}只) + trading dates预排序({len(_TRADING_DATES_SORTED)}天)")

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
    portfolio.max_yearly_trades = config.get("max_yearly_trades", 50)  # 年交易上限
    portfolio._min_holding_days = config.get("min_holding_days", 60)  # 最低持有天数
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

    # ── 市场风险预警初始化（方案B）──
    _market_risk_enabled = config.get("market_risk_filter", False) and MARKET_RISK_AVAILABLE
    _market_risk_threshold = config.get("market_risk_threshold", 60)  # 风险分>此值停止买入
    _market_risk_caution = config.get("market_risk_caution", 30)  # 风险分>此值减半买入

    # ── Transformer市场预测初始化（方案C）──
    _predictor_enabled = config.get("market_predictor", False) and MARKET_PREDICTOR_AVAILABLE
    _predictor = None
    _predictor_prob_threshold = config.get("predictor_prob_threshold", 0.6)  # P(跌)>此值停止买入
    _predictor_retrain_interval = config.get("predictor_retrain_days", 20)
    _predictor_crash_threshold = config.get("predictor_crash_threshold", 0.0)  # 0=任何跌, -0.05=跌超5%
    _predictor_sell_threshold = config.get("predictor_sell_threshold", 0.0)  # P(大跌)>此值清仓逃跑, 0=禁用
    if _predictor_enabled:
        _predictor = MarketPredictor(
            seq_len=60, fwd_days=10, retrain_interval=_predictor_retrain_interval,
            crash_threshold=_predictor_crash_threshold)
        print(f"Market predictor (Transformer): enabled, crash_thresh={_predictor_crash_threshold}, sell_thresh={_predictor_sell_threshold}")

    # ── LightGBM市场预测初始化（方案V）──
    _lgb_enabled = config.get("lgb_predictor", False) and LGB_PREDICTOR_AVAILABLE
    _lgb_predictor = None
    _lgb_crash_threshold = config.get("lgb_crash_threshold", -0.05)
    _lgb_sell_threshold = config.get("lgb_sell_threshold", 0.0)
    _lgb_prob_down = 0.5
    if _lgb_enabled:
        _lgb_predictor = LGBMarketPredictor(
            seq_len=60, fwd_days=10, retrain_interval=config.get("lgb_retrain_days", 20),
            crash_threshold=_lgb_crash_threshold)
        print(f"LGB predictor: enabled, crash_thresh={_lgb_crash_threshold}, sell_thresh={_lgb_sell_threshold}")

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

        # ── 长周期辅助参数：周线MACD背离/年线/周线布林带 → 仓位调节 ──
        _market_discount = 1.0  # 默认不调整，仅在config开启时生效
        _benchmark_code = "110020"  # 易方达沪深300ETF联接，与detect_market_state一致
        _bm_pts = fund_charts.get(_benchmark_code, [])
        _bm_nav_values = []
        if _bm_pts:
            _bm_valid = _bisect_valid(_bm_pts, cutoff_full)
            _bm_nav_values = [(100 + _float(p.get("yAxis", 0))) / 100 for p in _bm_valid]

        # 周线MACD顶背离 → 仓位×0.7
        if config.get("weekly_macd_divergence", False) and len(_bm_nav_values) >= 300:
            try:
                _div = compute_macd_divergence(_bm_nav_values)
                if _div == "top":
                    _market_discount *= config.get("divergence_top_discount", 0.7)
                # 底背离不提高仓位（让短线决定），牛市底背离很少
            except Exception:
                pass

        # 周线布林带仓位调节
        if config.get("weekly_bollinger_adjust", False) and len(_bm_nav_values) >= 100:
            try:
                _, _, _, _bb_pct = compute_weekly_bollinger(_bm_nav_values)
                if _bb_pct > 0.8:
                    _market_discount *= config.get("bb_upper_discount", 0.8)  # 接近上轨 → 减仓
                elif _bb_pct < 0.2:
                    _market_discount *= config.get("bb_lower_boost", 1.2)    # 接近下轨 → 加仓
            except Exception:
                pass

        # 年线牛熊过滤：跌破年线 → 仓位上限减半
        if config.get("yearly_ma_filter", False) and len(_bm_nav_values) >= 250:
            try:
                _bm_nav, _bm_ma250, _above_ma = compute_ma_250(_bm_nav_values)
                if not _above_ma:
                    _dyn_max_pos = _dyn_max_pos * config.get("yearly_bear_pos_ratio", 0.5)
            except Exception:
                pass

        # 防止_market_discount过小（最低0.3，避免完全不买）
        _market_discount = max(0.3, min(2.0, _market_discount))

        # ── 方案B：市场风险预警 ──
        _market_risk_action = "normal"
        _market_risk_score = 0
        if _market_risk_enabled and _bm_nav_values:
            # 收集持仓基金净值序列用于市场广度计算
            _held_nav_series = {}
            for _hc in list(portfolio.holdings.keys()):
                _hpts = fund_charts.get(_hc, [])
                _hvalid = _bisect_valid(_hpts, cutoff_full)
                if len(_hvalid) >= 20:
                    _held_nav_series[_hc] = [(100 + _float(p.get("yAxis", 0))) / 100 for p in _hvalid]
            try:
                _risk_result = compute_market_risk(_bm_nav_values, _held_nav_series)
                _market_risk_score = _risk_result["risk_score"]
                _market_risk_action = _risk_result["action"]
                if idx % 20 == 0:
                    print(f"  market_risk: score={_market_risk_score:.0f} action={_market_risk_action}")
            except Exception:
                pass

        # ── 方案C：Transformer市场方向预测 ──
        _predictor_prob_down = 0.5  # 默认中性
        if _predictor_enabled and _predictor and _bm_nav_values:
            # 收集训练数据（walk-forward）
            if idx > 0 and idx % 5 == 0:
                try:
                    _cutoff_idx = min(len(_bm_nav_values), len(_bm_nav_values))
                    _predictor.add_training_data(_bm_nav_values, _cutoff_idx)
                    _new_count = len(_predictor.training_data)
                    if _predictor.should_retrain(_new_count):
                        print(f"  training market predictor with {_new_count} samples...")
                        _predictor.train()
                except Exception as e:
                    pass
            # 预测
            try:
                _predictor_prob_down = _predictor.predict(_bm_nav_values)
                if idx % 20 == 0:
                    print(f"  predictor: P(down)={_predictor_prob_down:.2f}")
            except Exception:
                pass

        # ── 方案V：LightGBM市场预测（CPU秒级，替代Transformer）──
        _lgb_prob_down = 0.5
        if _lgb_enabled and _lgb_predictor and _bm_nav_values:
            if idx > 0 and idx % 5 == 0:
                try:
                    _lgb_predictor.add_training_data(_bm_nav_values, len(_bm_nav_values))
                    _lgb_new = len(_lgb_predictor.training_data_X)
                    if _lgb_predictor.should_retrain(_lgb_new):
                        _lgb_predictor.train()
                        if idx % 20 == 0:
                            print(f"  lgb_trained: {_lgb_new} samples")
                except Exception:
                    pass
            try:
                _lgb_prob_down = _lgb_predictor.predict(_bm_nav_values)
                if idx % 20 == 0:
                    print(f"  lgb_predict: P(crash)={_lgb_prob_down:.2f}")
            except Exception:
                pass

        # 方案V：LGB预测过滤 — P(crash)>阈值时停止买入
        if _lgb_enabled and candidates and _lgb_prob_down > config.get("lgb_buy_stop_threshold", 0.7):
            candidates = []
            if idx % 20 == 0:
                print(f"  lgb_filter: STOP BUY (P_crash={_lgb_prob_down:.2f})")

        # 方案V2：LGB大跌预测清仓 — P(crash)>sell_threshold时清仓逃跑
        if _lgb_enabled and _lgb_sell_threshold > 0 and _lgb_prob_down > _lgb_sell_threshold:
            if portfolio.holdings and (not hasattr(portfolio, '_last_lgb_crash_sell') or idx - getattr(portfolio, '_last_lgb_crash_sell', 0) >= 10):
                print(f"  LGB_CRASH: P(crash)={_lgb_prob_down:.2f} > {_lgb_sell_threshold}, SELLING ALL")
                for _lp_code in list(portfolio.holdings.keys()):
                    _lp_pts = fund_charts.get(_lp_code, [])
                    _lp_valid = _bisect_valid(_lp_pts, cutoff_full)
                    _lp_nav = (100 + _float(_lp_valid[-1].get("yAxis", 0))) / 100 if _lp_valid else 1.0
                    portfolio.sell(_lp_code, 0, _lp_nav, cutoff_full, "lgb_crash_predictor", force_sell=True)
                portfolio._last_lgb_crash_sell = idx
                portfolio._dd_pause_until = _add_days(cutoff_full, 5)

        # ── 动态评分门槛：根据市场状态调整 min_score ──
        _effective_min_score = config.get("min_score", 3.3)
        _dyn_min_score_key = f"min_score_{_market_state}"  # min_score_bull / min_score_bear / min_score_neutral
        if _dyn_min_score_key in config:
            _effective_min_score = config[_dyn_min_score_key]

        # ── 行情特定参数：按牛/熊/震荡分别配置 ──
        _ms = _market_state  # shorthand
        # 如果配置了 regime_specific=true, 优先用行情特定参数, 否则用通用值
        _regime = config.get("regime_specific", False)
        def _rc(key, default):
            """Regime-aware config: 先查 regime 特定值, 再查通用值, 最后用 default"""
            if _regime:
                regime_val = config.get(f"{key}_{_ms}")
                if regime_val is not None:
                    return regime_val
            return config.get(key, default)

        _dyn_tp_pct = _rc("take_profit_pct", 50)
        _dyn_sl_pct = _rc("stop_loss_pct", -30)
        _dyn_kelly = _rc("kelly_cap", 0.2)
        _dyn_pyramid = _rc("pyramiding_enabled", False)
        _dyn_dynsl = _rc("dynamic_stop_loss", False)
        _dyn_trail_act = _rc("trailing_tp_activate", 0)
        _dyn_trail_dd = _rc("trailing_tp_drawdown", 10)
        # max_pos / cash_reserve 也走 _rc() 机制，使 regime_specific=True 时仓位上限随行情变化
        _dyn_max_pos = _rc("max_position_pct", _dyn_max_pos)
        _dyn_cash_reserve = _rc("cash_reserve_pct", _dyn_cash_reserve)

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

        # ── OpenClaw组合级回撤熔断：检查是否在暂停期内（上一轮可能触发）──
        _in_pause = hasattr(portfolio, '_dd_pause_until') and cutoff_full < getattr(portfolio, '_dd_pause_until', '')

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

        # ═══ 动量信号模式：脱离大佬，用基金自身收益率排名生成信号 ═══
        _signal_source = config.get("signal_source", "expert")
        if _signal_source == "momentum":
            _mom_lookback = config.get("momentum_lookback", 63)  # 回看天数（63≈3月）
            _mom_top_n = config.get("momentum_top_n", 10)  # 取前N只
            _mom_rebal = config.get("momentum_rebalance_days", 21)  # 调仓频率（21≈1月）
            _mom_min_data = config.get("momentum_min_data", 40)  # 最少数据天数

            # 只在调仓日重新计算排名
            if idx % _mom_rebal == 0 or idx == 0:
                _mom_ranking = []
                for _code, _pts in fund_charts.items():
                    _valid = _bisect_valid(_pts, cutoff_full)
                    if len(_valid) < _mom_min_data + _mom_lookback:
                        continue
                    _navs = [(100 + _float(p.get("yAxis", 0))) / 100 for p in _valid]
                    _cur = _navs[-1]
                    _past = _navs[-_mom_lookback] if len(_navs) > _mom_lookback else _navs[0]
                    if _past > 0:
                        _ret = (_cur / _past - 1) * 100
                        _mom_ranking.append((_code, _ret))
                _mom_ranking.sort(key=lambda x: x[1], reverse=True)
                _mom_ranking = _mom_ranking[:_mom_top_n]
                if idx % 100 == 0:
                    print(f"  [momentum] rebalance: top{_mom_top_n} by {_mom_lookback}d return")
                    for _c, _r in _mom_ranking[:5]:
                        print(f"    {_c}: {_r:.2f}%")

            # 生成合成信号：top N基金各得到buy_count=1
            fund_signals = defaultdict(lambda: {"buy_count": 0, "sell_count": 0, "weighted_buy": 0.0, "records": []})
            _name_map_inv = {v: k for k, v in name_to_code.items()} if name_to_code else {}
            for _rank, (_code, _ret) in enumerate(_mom_ranking):
                _fn = _name_map_inv.get(_code, _code)
                fund_signals[_fn]["buy_count"] = 1
                fund_signals[_fn]["weighted_buy"] = 1.0
            use_weighted = False
            _weighted_threshold = 0
        else:
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
            _weighted_threshold = config.get("weighted_consensus_threshold", 0)  # 加权共识门槛(浮点)
            for fn in fund_signals:
                if use_weighted:
                    _wb = fund_signals[fn]["weighted_buy"]
                    if _weighted_threshold > 0:
                        # 使用浮点门槛而非int截断
                        fund_signals[fn]["buy_count"] = _wb  # 保留浮点用于门槛比较
                    else:
                        fund_signals[fn]["buy_count"] = max(1, int(_wb))

        # 对该日有买入信号的基金评分
        candidates = []

        # ── 自适应共识：稀疏期降门槛，密集期提门槛 ──
        _min_consensus = config.get("min_consensus", 2)
        if config.get("adaptive_consensus", False):
            # 近30日日均信号密度
            _recent_days = backtest_dates[max(0, idx-30):idx+1]
            _recent_signals = sum(len(trading_by_date.get(d, [])) for d in _recent_days)
            _avg_daily = _recent_signals / max(1, len(_recent_days))
            if _avg_daily < 15:
                _min_consensus = 1   # 稀疏期：1人买就够
            elif _avg_daily < 50:
                _min_consensus = 2   # 正常期
            else:
                _min_consensus = config.get("min_consensus", 2)  # 密集期：不提高门槛(防过量过滤)

        # ── 净信号参数 ──
        _net_signal = config.get("net_signal", False)
        _net_signal_ratio = config.get("net_signal_ratio", 0)  # 买入必须 >= 卖出 * ratio
        _net_signal_diff = config.get("net_signal_diff", 0)  # 买入-卖出必须 >= diff

        for fn, signal in fund_signals.items():
            _bc = signal["buy_count"]
            # 加权模式下用浮点比较
            if use_weighted and _weighted_threshold > 0:
                if _bc < _weighted_threshold:
                    continue
            else:
                if _bc < _min_consensus:
                    continue
            # 净信号过滤：买入必须多于卖出
            _sc = signal.get("sell_count", 0)
            if _net_signal and _bc <= _sc:
                continue
            # 净信号比例过滤：买入必须 >= 卖出 * ratio
            if _net_signal_ratio > 0 and _bc < _sc * _net_signal_ratio:
                continue
            # 净信号差值过滤：买入-卖出必须 >= diff
            if _net_signal_diff > 0 and (_bc - _sc) < _net_signal_diff:
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
                    "quality": fs.quality.score if fs.quality else -1,
                    "cost": fs.cost.score if fs.cost else 3.0,
                    "manager": fs.manager.score if fs.manager else -1,
                    "momentum": fs.momentum.score if fs.momentum else -1,
                    "smart_money": fs.smart_money.score if fs.smart_money else -1,
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
                    "quality": fs.quality.score if fs.quality else -1,
                    "cost": fs.cost.score if fs.cost else 3.0,
                    "manager": fs.manager.score if fs.manager else -1,
                    "momentum": fs.momentum.score if fs.momentum else -1,
                    "smart_money": fs.smart_money.score if fs.smart_money else -1,
                    "total": fs.total,
                }, signal["buy_count"], _market_state))

            # 共识门槛已在上方用 _min_consensus（支持自适应）过滤，此处不再重复检查

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

        # 组合回撤暂停期内不买入新基金（OpenClaw组合级风控）
        if _in_pause and candidates:
            candidates = []

        # 方案B：市场风险过滤 — 高风险时停止买入，中风险时减半
        if _market_risk_enabled and candidates:
            if _market_risk_action == "stop_buy" or _market_risk_action == "reduce":
                candidates = []
                if idx % 20 == 0:
                    print(f"  market_risk_filter: STOP BUY (score={_market_risk_score})")
            elif _market_risk_action == "caution":
                # 减半候选数量（只保留评分最高的前50%）
                candidates.sort(key=lambda c: c["score"], reverse=True)
                candidates = candidates[:max(1, len(candidates) // 2)]
                if idx % 20 == 0:
                    print(f"  market_risk_filter: CAUTION (score={_market_risk_score}), reduced to {len(candidates)} candidates")

        # 方案C：Transformer预测过滤 — P(下跌)>阈值时停止买入
        if _predictor_enabled and candidates and _predictor_prob_down > _predictor_prob_threshold:
            candidates = []
            if idx % 20 == 0:
                print(f"  predictor_filter: STOP BUY (P_down={_predictor_prob_down:.2f})")

        # 方案C2：大跌预测清仓 — P(大跌)>阈值时卖出所有持仓逃跑
        if _predictor_enabled and _predictor_sell_threshold > 0 and _predictor_prob_down > _predictor_sell_threshold:
            if portfolio.holdings and (not hasattr(portfolio, '_last_crash_sell') or idx - getattr(portfolio, '_last_crash_sell', 0) >= 10):
                print(f"  🚨 CRASH_PREDICTOR: P(crash)={_predictor_prob_down:.2f} > {_predictor_sell_threshold}, SELLING ALL")
                for _cp_code in list(portfolio.holdings.keys()):
                    _cp_h = portfolio.holdings[_cp_code]
                    _cp_pts = fund_charts.get(_cp_code, [])
                    _cp_valid = _bisect_valid(_cp_pts, cutoff_full)
                    _cp_nav = (100 + _float(_cp_valid[-1].get("yAxis", 0))) / 100 if _cp_valid else 1.0
                    portfolio.sell(_cp_code, 0, _cp_nav, cutoff_full, "crash_predictor", force_sell=True)
                portfolio._last_crash_sell = idx
                portfolio._dd_pause_until = _add_days(cutoff_full, 5)  # 暂停5天买入

        # 方案D3：MACD金叉买入过滤 — 基准MACD<0时停止买入
        _macd_buy_filter = config.get("macd_golden_cross_buy", False)
        if _macd_buy_filter and candidates and _bm_nav_values:
            try:
                from tools.technical_indicators import compute_macd
                _bm_macd, _bm_sig, _bm_hist = compute_macd(_bm_nav_values)
                if _bm_macd < _bm_sig:  # MACD在信号线下方，空头趋势
                    candidates = []
                    if idx % 20 == 0:
                        print(f"  macd_buy_filter: STOP BUY (MACD={_bm_macd:.4f} < signal={_bm_sig:.4f})")
            except Exception:
                pass

        # 方案I1：MA20趋势买入过滤 — 只买入站上MA20的基金（事件驱动V2灵感）
        _ma20_buy = config.get("ma20_trend_buy", False)
        if _ma20_buy and candidates:
            filtered = []
            for c in candidates:
                _cpts = fund_charts.get(c["code"], [])
                _cvalid = _bisect_valid(_cpts, cutoff_full)
                if len(_cvalid) >= 20:
                    _cnavs = [(100 + _float(p.get("yAxis", 0))) / 100 for p in _cvalid]
                    _cma20 = statistics.mean(_cnavs[-20:])
                    if _cnavs[-1] >= _cma20:
                        filtered.append(c)
            candidates = filtered

        # 方案I2：RSI超卖买入 — 只在RSI<阈值时买入（逆向/均值回归）
        _rsi_buy_max = config.get("rsi_buy_max", 0)
        if _rsi_buy_max > 0 and candidates:
            filtered = []
            for c in candidates:
                _cpts = fund_charts.get(c["code"], [])
                _cvalid = _bisect_valid(_cpts, cutoff_full)
                if len(_cvalid) >= 15:
                    _cnavs = [(100 + _float(p.get("yAxis", 0))) / 100 for p in _cvalid]
                    _crsi = compute_rsi(_cnavs, 14)
                    if _crsi <= _rsi_buy_max:
                        filtered.append(c)
            candidates = filtered

        # 方案I3：动量突破买入 — 只买入创N日新高的基金
        _breakout_days = config.get("momentum_breakout_days", 0)
        if _breakout_days > 0 and candidates:
            filtered = []
            for c in candidates:
                _cpts = fund_charts.get(c["code"], [])
                _cvalid = _bisect_valid(_cpts, cutoff_full)
                if len(_cvalid) >= _breakout_days:
                    _cnavs = [(100 + _float(p.get("yAxis", 0))) / 100 for p in _cvalid]
                    _recent_max = max(_cnavs[-(_breakout_days):-1]) if len(_cnavs) > _breakout_days else 0
                    if _cnavs[-1] > _recent_max:
                        filtered.append(c)
            candidates = filtered

        # 方案KDJ：KDJ买入过滤 — KDJ超买区不买/超卖区才买/金叉才买
        _kdj_buy_mode = config.get("kdj_buy_mode", "")  # "block_overbought" / "oversold_only" / "golden_cross"
        _kdj_n = config.get("kdj_n", 9)
        _kdj_overbought_k = config.get("kdj_overbought_k", 80)
        _kdj_oversold_k = config.get("kdj_oversold_k", 20)
        if _kdj_buy_mode and candidates:
            filtered = []
            for c in candidates:
                _cpts = fund_charts.get(c["code"], [])
                _cvalid = _bisect_valid(_cpts, cutoff_full)
                if len(_cvalid) < _kdj_n + 1:
                    filtered.append(c)  # 数据不足不过滤
                    continue
                _cnavs = [(100 + _float(p.get("yAxis", 0))) / 100 for p in _cvalid]
                _ck, _cd, _cj = compute_kdj(_cnavs, _kdj_n)
                if _kdj_buy_mode == "block_overbought":
                    # K>D且K>overbought → 超买，不买
                    if _ck > _kdj_overbought_k:
                        continue
                    filtered.append(c)
                elif _kdj_buy_mode == "oversold_only":
                    # 只在K<oversold时买入
                    if _ck < _kdj_oversold_k:
                        filtered.append(c)
                elif _kdj_buy_mode == "golden_cross":
                    # 需要KDJ序列判断金叉
                    _kdj_series = compute_kdj_series(_cnavs, _kdj_n)
                    if len(_kdj_series) >= 2:
                        _k1, _d1, _ = _kdj_series[-2]
                        _k2, _d2, _ = _kdj_series[-1]
                        # 金叉：前一天K<D，今天K>D
                        if _k1 <= _d1 and _k2 > _d2:
                            filtered.append(c)
                    # 非金叉但K>D也允许（趋势向上）
                    elif _ck > _cd:
                        filtered.append(c)
                else:
                    filtered.append(c)
            if filtered:
                candidates = filtered

        # 方案MACCEL：动量加速检测 — 3月涨30%+1月加速 → 不买（高位预警）
        _maccel_enabled = config.get("maccel_block", False)
        _maccel_3m = config.get("maccel_3m_threshold", 30.0)
        _maccel_ratio = config.get("maccel_ratio", 1.5)
        if _maccel_enabled and candidates:
            filtered = []
            for c in candidates:
                _cpts = fund_charts.get(c["code"], [])
                _cvalid = _bisect_valid(_cpts, cutoff_full)
                if len(_cvalid) < 64:
                    filtered.append(c)  # 数据不足不过滤
                    continue
                _cnavs = [(100 + _float(p.get("yAxis", 0))) / 100 for p in _cvalid]
                _ma = detect_momentum_acceleration(_cnavs, threshold_3m=_maccel_3m, accel_ratio=_maccel_ratio)
                if _ma["should_warn"]:
                    continue  # 动量加速，跳过
                filtered.append(c)
            if filtered:
                candidates = filtered

        # 方案U4：相对强度买入 — 只买跑赢基准的基金
        _rel_strength = config.get("relative_strength_buy", False)
        if _rel_strength and candidates and _bm_nav_values and len(_bm_nav_values) >= 20:
            _bm_ret_20 = _bm_nav_values[-1] / _bm_nav_values[-20] - 1
            filtered = []
            for c in candidates:
                _cpts = fund_charts.get(c["code"], [])
                _cvalid = _bisect_valid(_cpts, cutoff_full)
                if len(_cvalid) >= 20:
                    _cnavs = [(100 + _float(p.get("yAxis", 0))) / 100 for p in _cvalid]
                    _c_ret = _cnavs[-1] / _cnavs[-20] - 1
                    if _c_ret > _bm_ret_20:
                        filtered.append(c)
            candidates = filtered

        # 方案U5：逆向买入 — 基准前一日跌幅>X%时才买入（抄底策略）
        _contrarian_drop = config.get("contrarian_buy_drop", 0)
        if _contrarian_drop > 0 and _bm_nav_values and len(_bm_nav_values) >= 2:
            _bm_daily_ret = _bm_nav_values[-1] / _bm_nav_values[-2] - 1
            if _bm_daily_ret < -_contrarian_drop:
                # 市场大跌，保持候选不变（抄底信号）
                if idx % 20 == 0:
                    print(f"  contrarian_buy: market drop={_bm_daily_ret*100:.2f}%, KEEPING candidates")
            else:
                # 市场没大跌，不买
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

        # ── OpenClaw策略：组合级回撤熔断 — 总资产从峰值回撤>X% → 清仓+暂停N天 ──
        _portfolio_dd_breaker = config.get("portfolio_dd_breaker", 0)
        if _portfolio_dd_breaker > 0:
            _total_val_now = portfolio.value(fund_prices)
            if not hasattr(portfolio, '_peak_total'):
                portfolio._peak_total = _total_val_now
            if _total_val_now > portfolio._peak_total:
                portfolio._peak_total = _total_val_now
            if portfolio._peak_total > 0:
                _portfolio_dd = (_total_val_now / portfolio._peak_total - 1) * 100
                if _portfolio_dd < -_portfolio_dd_breaker:
                    _pause_days = config.get("portfolio_dd_pause_days", 5)
                    if not hasattr(portfolio, '_dd_pause_until') or cutoff_full >= getattr(portfolio, '_dd_pause_until', ''):
                        print(f"  🚨 PORTFOLIO_CIRCUIT_BREAKER dd={_portfolio_dd:.1f}% clearing all + pause {_pause_days}d")
                        for _cb_code in list(portfolio.holdings.keys()):
                            _cb_h = portfolio.holdings[_cb_code]
                            _cb_pts = fund_charts.get(_cb_code, [])
                            _cb_valid = _bisect_valid(_cb_pts, cutoff_full)
                            _cb_nav = (100 + _float(_cb_valid[-1].get("yAxis", 0))) / 100 if _cb_valid else 1.0
                            portfolio.sell(_cb_code, 0, _cb_nav, cutoff_full, "portfolio_circuit_breaker", force_sell=True)
                        try:
                            from datetime import datetime as _dt, timedelta as _td
                            _pause_dt = _dt.strptime(cutoff_full[:10], "%Y-%m-%d") + _td(days=_pause_days)
                            portfolio._dd_pause_until = _pause_dt.strftime("%Y-%m-%d")
                        except:
                            portfolio._dd_pause_until = cutoff_full

        # 更新暂停状态（可能在上面触发）
        _in_pause = hasattr(portfolio, '_dd_pause_until') and cutoff_full < getattr(portfolio, '_dd_pause_until', '')

        # 重新评分已持仓的基金（判断是否需要卖出）
        for code in list(portfolio.holdings.keys()):
            h = portfolio.holdings[code]
            pts = fund_charts.get(code, [])
            if not pts:
                continue

            # 用当天的 chart_data 算累计收益
            valid = _bisect_valid(pts, cutoff_full)
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

            sell_price = current_nav  # 用当天净值（与买入一致，实盘T日赎回按当日净值）
            sell_reason = ""
            should_sell = False

            tp_pct = _dyn_tp_pct
            tp_sell = config.get("take_profit_sell_pct", 0.5)
            sl_pct = _dyn_sl_pct
            mom_sell = config.get("momentum_sell", 2.0)
            max_pos = _dyn_max_pos

            # 🔴 止损: 亏损超过阈值（指数型或配置了no_stop_loss则跳过）
            no_sl = config.get("no_stop_loss", False)
            # 动态止损：浮盈 >20% 收紧到从高点回撤15%，浮盈 >40% 收紧到10%
            effective_sl = sl_pct
            if _dyn_dynsl and cum_return > 20:
                if drawdown_from_peak < -15:
                    should_sell = True
                    sell_reason = f"dyn_stop_loss profit={cum_return:.1f}% dd={drawdown_from_peak:.1f}%"
                elif cum_return > 40 and drawdown_from_peak < -10:
                    should_sell = True
                    sell_reason = f"dyn_stop_loss profit={cum_return:.1f}% dd={drawdown_from_peak:.1f}%"
            elif not no_sl and cum_return < effective_sl:
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

            # 🟡 方案D1：阶梯止盈 — 分批卖出锁利
            _step_tp = config.get("step_take_profit", False)
            if _step_tp and cum_return > 20 and code in portfolio.holdings:
                _step_levels = config.get("step_tp_levels", [(30, 0.3), (50, 0.3), (80, 0.4)])
                _sold_key = f"_step_tp_sold_{int(cum_return // 10) * 10}"
                if not h.get(_sold_key, False):
                    for _level, _frac in _step_levels:
                        if cum_return >= _level and not h.get(f"_step_tp_sold_{_level}", False):
                            _sell_val = h["shares"] * sell_price * _frac
                            if _sell_val >= 100:
                                portfolio.sell(code, _sell_val, sell_price, cutoff_full,
                                              sell_reason=f"step_tp {_level}% sell{_frac*100:.0f}%")
                                h[f"_step_tp_sold_{_level}"] = True
                                print(f"  SELL_STEP_TP {code} {h['name'][:16]} level={_level}% frac={_frac*100:.0f}% amt={_sell_val:.0f}")
                                break

            # 🟢 移动止盈: 盈利达到激活阈值后，从最高点回撤超过阈值则卖出锁利
            # 与 peak_drawdown_exit 的区别：只在盈利状态下触发，避免亏损时误卖
            if _dyn_trail_act > 0 and cum_return >= _dyn_trail_act and drawdown_from_peak < -_dyn_trail_dd:
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

            # 🔴 动量崩溃: 动量分低于阈值（牛市不触发，减少假信号）
            _mom_sell_actual = mom_sell
            # 方案S1: 动量崩溃阈值调整 — 浮亏时更严格，浮盈时更宽松
            _mom_adj = config.get("momentum_sell_adjust", 0)
            if _mom_adj > 0:
                if cum_return < 0:
                    _mom_sell_actual = mom_sell * (1 - _mom_adj)  # 亏损时更严格(更低才卖)
                elif cum_return > 30:
                    _mom_sell_actual = mom_sell * (1 + _mom_adj)  # 盈利时更宽松
            if mom.score < _mom_sell_actual and _market_state != "bull":
                should_sell = True
                sell_reason = f"momentum_crash mom={mom.score:.2f} threshold={_mom_sell_actual:.2f}"

            # KDJ死叉卖出 — K下穿D且在超买区
            _kdj_sell_mode = config.get("kdj_sell_mode", "")  # "death_cross" / "overbought_exit"
            if _kdj_sell_mode and not should_sell:
                try:
                    _sell_navs = [(100 + _float(p.get("yAxis", 0))) / 100 for p in valid]
                    if len(_sell_navs) >= 11:
                        _kdj_s = compute_kdj_series(_sell_navs, _kdj_n)
                        if len(_kdj_s) >= 2:
                            _pk, _pd, _pj = _kdj_s[-2]
                            _ck, _cd, _cj = _kdj_s[-1]
                            if _kdj_sell_mode == "death_cross":
                                # 死叉：前一天K>D，今天K<D
                                if _pk >= _pd and _ck < _cd:
                                    should_sell = True
                                    sell_reason = f"kdj_death_cross K={_ck:.1f} D={_cd:.1f}"
                            elif _kdj_sell_mode == "overbought_exit":
                                # 超买区死叉：K>80时K下穿D
                                if _pk > _kdj_overbought_k and _pk >= _pd and _ck < _cd:
                                    should_sell = True
                                    sell_reason = f"kdj_overbought_exit K={_ck:.1f} D={_cd:.1f}"
                except Exception:
                    pass

            # 动量加速卖出 — 持仓中基金出现3月涨30%+1月加速 → 获利了结
            _maccel_sell = config.get("maccel_sell", False)
            if _maccel_sell and not should_sell and cum_return > 0:
                try:
                    _sell_navs = [(100 + _float(p.get("yAxis", 0))) / 100 for p in valid]
                    if len(_sell_navs) >= 64:
                        _ma = detect_momentum_acceleration(_sell_navs, threshold_3m=_maccel_3m, accel_ratio=_maccel_ratio)
                        if _ma["should_warn"]:
                            should_sell = True
                            sell_reason = f"maccel_sell 3m={_ma['ret_3m']:.1f}% 1m={_ma['ret_1m']:.1f}% avg={_ma['monthly_avg']:.1f}%"
                except Exception:
                    pass

            # 🟡 OpenClaw策略：RSI超买卖出 — RSI>阈值且盈利中，部分卖出锁利
            _rsi_sell_threshold = config.get("rsi_sell_threshold", 0)
            if _rsi_sell_threshold > 0 and cum_return > 10 and code in portfolio.holdings:
                try:
                    _sell_nav_values = [(100 + _float(p.get("yAxis", 0))) / 100 for p in valid]
                    _sell_rsi = compute_rsi(_sell_nav_values, 14)
                    if _sell_rsi > _rsi_sell_threshold:
                        sell_value = h["shares"] * sell_price * config.get("rsi_sell_pct", 0.3)
                        if sell_value >= 100:
                            portfolio.sell(code, sell_value, sell_price, cutoff_full,
                                          sell_reason=f"rsi_overbought rsi={_sell_rsi:.0f} profit={cum_return:.1f}%")
                            print(f"  SELL_RSI {code} {h['name'][:16]} rsi={_sell_rsi:.0f} profit={cum_return:.1f}% amt={sell_value:.0f}")
                            continue
                except Exception:
                    pass

            # 🟡 OpenClaw策略：N日不创新高卖出 — 连续N个交易日未创净值新高 → 趋势走平卖出
            _no_new_high_days = config.get("no_new_high_days", 0)
            if _no_new_high_days > 0 and cum_return > 0 and code in portfolio.holdings:
                try:
                    _recent_pts = valid[-min(_no_new_high_days + 1, len(valid)):] if len(valid) >= _no_new_high_days else []
                    if _recent_pts:
                        _recent_navs = [(100 + _float(p.get("yAxis", 0))) / 100 for p in _recent_pts]
                        _recent_max = max(_recent_navs[:-1]) if len(_recent_navs) > 1 else 0
                        if current_nav < _recent_max:
                            should_sell = True
                            sell_reason = f"no_new_high {_no_new_high_days}d profit={cum_return:.1f}%"
                except Exception:
                    pass

            # 🟡 OpenClaw策略：均线死叉卖出 — MA5下穿MA20 → 趋势反转卖出
            _ma_cross_sell = config.get("ma_death_cross_sell", False)
            if _ma_cross_sell and cum_return > 0 and code in portfolio.holdings and len(valid) >= 25:
                try:
                    _sell_nav_values = [(100 + _float(p.get("yAxis", 0))) / 100 for p in valid]
                    _ma5_now = statistics.mean(_sell_nav_values[-5:])
                    _ma20_now = statistics.mean(_sell_nav_values[-20:])
                    _ma5_prev = statistics.mean(_sell_nav_values[-6:-1])
                    _ma20_prev = statistics.mean(_sell_nav_values[-21:-1])
                    if _ma5_prev >= _ma20_prev and _ma5_now < _ma20_now:
                        should_sell = True
                        sell_reason = f"ma_death_cross MA5={_ma5_now:.4f}<MA20={_ma20_now:.4f}"
                except Exception:
                    pass

            # 🔴 OpenClaw策略：时间止损 — 持仓满N天且收益不足 → 卖出释放资金
            _time_stop_days = config.get("time_stop_days", 0)
            if _time_stop_days > 0 and code in portfolio.holdings:
                _hold_days = portfolio._holding_days(code, cutoff_full)
                _time_stop_profit = config.get("time_stop_min_profit", 5)
                if _hold_days >= _time_stop_days and cum_return < _time_stop_profit:
                    should_sell = True
                    sell_reason = f"time_stop {_hold_days}d profit={cum_return:.1f}%"

            # 方案S2: 盈利保护卖出 — 浮亏>阈值且持续N天 → 卖出止损
            _loss_hold_days = config.get("loss_hold_days", 0)
            if _loss_hold_days > 0 and cum_return < -10 and code in portfolio.holdings:
                _hold_d = portfolio._holding_days(code, cutoff_full)
                if _hold_d >= _loss_hold_days:
                    should_sell = True
                    sell_reason = f"loss_hold {_hold_d}d return={cum_return:.1f}%"

            # 方案S3: 动态移动止盈 — 浮盈越高，回撤阈值越紧
            _tp_trail_dynamic = config.get("tp_trail_dynamic", False)
            if _tp_trail_dynamic and cum_return > 20 and code in portfolio.holdings:
                # 20%盈利→回撤12%卖, 40%→8%, 60%→6%, 80%+→5%
                _trail_dd = max(5, 14 - int(cum_return / 20))
                if drawdown_from_peak < -_trail_dd:
                    should_sell = True
                    sell_reason = f"tp_trail_dynamic profit={cum_return:.1f}% dd={drawdown_from_peak:.1f}% threshold={_trail_dd}%"

            # 方案S4: 动量衰退卖出 — 动量分连续N天下隆 → 提前离场
            _mom_decay_days = config.get("mom_decay_days", 0)
            if _mom_decay_days > 0 and code in portfolio.holdings and cum_return > 5:
                _decay_key = f"_mom_history_{code}"
                if not hasattr(portfolio, _decay_key):
                    setattr(portfolio, _decay_key, [])
                _mom_hist = getattr(portfolio, _decay_key)
                _mom_hist.append(mom.score)
                if len(_mom_hist) > _mom_decay_days:
                    _mom_hist.pop(0)
                if len(_mom_hist) >= _mom_decay_days:
                    _recent_avg = statistics.mean(_mom_hist[-_mom_decay_days:])
                    _prev_avg = statistics.mean(_mom_hist[:-1]) if len(_mom_hist) > 1 else _recent_avg
                    if _recent_avg < _prev_avg * 0.8:  # 动量下降20%
                        should_sell = True
                        sell_reason = f"mom_decay {_mom_decay_days}d avg={_recent_avg:.2f} prev={_prev_avg:.2f}"

            # 🔴 方案U1：MA50趋势破位卖出 — 跌破50日均线卖出（长趋势跟随）
            _ma50_exit = config.get("ma50_trend_exit", False)
            if _ma50_exit and code in portfolio.holdings and len(valid) >= 50:
                try:
                    _sell_navs = [(100 + _float(p.get("yAxis", 0))) / 100 for p in valid]
                    _ma50 = statistics.mean(_sell_navs[-50:])
                    if _sell_navs[-1] < _ma50:
                        should_sell = True
                        sell_reason = f"ma50_break nav={_sell_navs[-1]:.4f} ma50={_ma50:.4f}"
                except Exception:
                    pass

            # 🔴 方案U2：波动率突增卖出 — 日波动率>2倍均值时=恐慌逃离
            _vol_spike_mult = config.get("vol_spike_mult", 0)
            if _vol_spike_mult > 0 and code in portfolio.holdings and len(valid) >= 30:
                try:
                    _sell_navs = [(100 + _float(p.get("yAxis", 0))) / 100 for p in valid]
                    _daily_rets = [abs(_sell_navs[i] - _sell_navs[i-1]) for i in range(1, len(_sell_navs))]
                    _avg_vol = statistics.mean(_daily_rets[-20:]) if len(_daily_rets) >= 20 else 0
                    _recent_vol = statistics.mean(_daily_rets[-3:]) if len(_daily_rets) >= 3 else 0
                    if _avg_vol > 0 and _recent_vol > _vol_spike_mult * _avg_vol:
                        should_sell = True
                        sell_reason = f"vol_spike recent={_recent_vol:.4f} avg={_avg_vol:.4f} ratio={_recent_vol/_avg_vol:.1f}x"
                except Exception:
                    pass

            # 🔴 方案U3：组合级回撤减仓 — 组合回撤>X%时每只减仓Y%（不全清）
            _port_dd_reduce_pct = config.get("portfolio_dd_reduce_pct", 0)
            if _port_dd_reduce_pct > 0 and code in portfolio.holdings:
                _total_value = portfolio.cash + sum(
                    h2["shares"] * (100 + _float((_bisect_valid(fund_charts.get(c2, []), cutoff_full) or [{"yAxis":0}])[-1].get("yAxis", 0))) / 100
                    for c2, h2 in portfolio.holdings.items()
                )
                _port_peak = getattr(portfolio, "_peak_value", _total_value)
                if _total_value > _port_peak:
                    portfolio._peak_value = _total_value
                    _port_peak = _total_value
                _port_dd = (_total_value / _port_peak - 1) * 100 if _port_peak > 0 else 0
                _port_dd_threshold = config.get("portfolio_dd_reduce_threshold", 10)
                if _port_dd < -_port_dd_threshold:
                    _reduce_frac = config.get("portfolio_dd_reduce_frac", 0.3)
                    _sell_val = h["shares"] * sell_price * _reduce_frac
                    if _sell_val >= 100 and not h.get("_dd_reduced_today", False):
                        portfolio.sell(code, _sell_val, sell_price, cutoff_full,
                                      sell_reason=f"port_dd_reduce dd={_port_dd:.1f}% frac={_reduce_frac*100:.0f}%")
                        h["_dd_reduced_today"] = True
                        print(f"  SELL_PORT_DD_REDUCE {code} {h['name'][:16]} dd={_port_dd:.1f}% amt={_sell_val:.0f}")
                        continue

            # 🔴 方案D2：ATR动态止损 — 止损线随波动率自适应
            _atr_mult = config.get("atr_stop_loss_mult", 0)
            if _atr_mult > 0 and code in portfolio.holdings and len(valid) >= 15:
                try:
                    _sell_nav_values = [(100 + _float(p.get("yAxis", 0))) / 100 for p in valid[-15:]]
                    _trs = [abs(_sell_nav_values[i] - _sell_nav_values[i-1]) for i in range(1, len(_sell_nav_values))]
                    _atr_val = statistics.mean(_trs) if _trs else 0
                    _atr_stop = buy_nav - _atr_mult * _atr_val
                    if current_nav <= _atr_stop:
                        should_sell = True
                        sell_reason = f"atr_stop nav={current_nav:.4f} stop={_atr_stop:.4f} atr={_atr_val:.4f}"
                except Exception:
                    pass

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
                            valid = _bisect_valid(pts, cutoff_full)
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
                        "score": _effective_min_score - 0.3,  # 买回门槛降低0.3（与主逻辑一致，支持regime/ML降门槛）
                        "buy_count": 1,
                        "day_limit": 999999,
                        "sector": sector,
                        "is_qdii": is_qdii,
                        "_buy_back": True,
                    })
                    print(f"  BUY_BACK_SIGNAL {bb_code} {bb_name[:16]} RSI={bb_timing['rsi']:.0f} trend=UP")

        # 方案D4：动态凯利 — 根据市场风险分数调整仓位
        _dyn_kelly_frac = config.get("kelly_fraction", 0.5)
        if _market_risk_enabled and _market_risk_score > 0:
            _risk_factor = max(0.1, 1.0 - _market_risk_score / 100)
            _dyn_kelly_frac = _dyn_kelly_frac * _risk_factor

        to_buy = kelly_allocate(candidates, portfolio.cash + sum(
            h["shares"] * fund_prices.get(code, h.get("buy_nav", 1.0))
            for code, h in portfolio.holdings.items()),
            kelly_cap=_dyn_kelly,
            cash_reserve=_dyn_cash_reserve,
            max_pos=_dyn_max_pos / 100,
            market_discount=_market_discount,
            kelly_fraction=_dyn_kelly_frac,
            max_single_buy_pct=config.get("max_single_buy_pct", 0.30),
            equal_allocate=config.get("equal_allocate", False))
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
            # 已持仓的基金：检查是否满足金字塔补仓条件
            if c["code"] in portfolio.holdings:
                # 金字塔补仓：浮亏 >5% 且大佬信号持续 → 越跌越买
                if not _dyn_pyramid:
                    continue
                h = portfolio.holdings[c["code"]]
                buy_nav = h.get("buy_nav", 1.0)
                current_nav = 1.0
                pts = fund_charts.get(c["code"], [])
                if pts:
                    valid = _bisect_valid(pts, day)
                    if valid:
                        current_nav = (100 + _float(valid[-1].get("yAxis", 0))) / 100
                loss_pct = (current_nav / buy_nav - 1) * 100 if buy_nav > 0 else 0
                # 浮亏 >5% 才补仓，跌 15% 以上不再加
                if loss_pct > -5 or loss_pct < -15:
                    continue
                # 补仓系数：跌5-10% → ×0.5，跌10-15% → ×0.3
                if loss_pct > -10:
                    pyramid_mult = 0.5
                else:
                    pyramid_mult = 0.3
                pyramid_amt = c["_suggested"] * pyramid_mult
                if pyramid_amt >= 100:
                    portfolio.buy(c["code"], c["name"], pyramid_amt, price=current_nav,
                                 day_str=day)
                    print(f"  PYRAMID {c['code']} {c['name'][:16]} loss={loss_pct:.1f}% mult={pyramid_mult} amt={pyramid_amt:.0f}")
                continue
            # 跳过已持仓或有待确认买入的基金（防止重复买入导致仓位超100%）
            if c["code"] in portfolio.holdings:
                continue
            if any(pb["code"] == c["code"] for pb in portfolio.pending_buys):
                continue
            # 计算实际买入净值
            buy_price = 1.0
            pts = fund_charts.get(c["code"], [])
            if pts:
                cutoff_full = day
                valid = _bisect_valid(pts, cutoff_full)
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
            valid = _bisect_valid(pts, cutoff_full)
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