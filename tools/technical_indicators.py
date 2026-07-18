#!/usr/bin/env python3
"""技术指标模块 — 融合 QuantDinger 的 RSI/MACD/布林带算法。

适配场外基金场景：
- 输入为基金累计收益率序列（yAxis%），自动转换为净值序列
- 纯Python实现，无numpy/pandas依赖
- 所有函数支持日期截断（防未来函数）

算法来源：
- RSI: QuantDinger multi_indicator_composite.py
- MACD: QuantDinger multi_indicator_composite.py
- 布林带: 经典技术分析
- MA交叉: QuantDinger dual_ma_with_params.py
"""
import statistics
from typing import List, Tuple, Optional


def _to_nav(values: List[float]) -> List[float]:
    """将累计收益率%转换为净值序列。 yAxis=5.23 → nav=1.0523"""
    return [(100 + v) / 100 for v in values]


def compute_rsi(nav_values: List[float], period: int = 14) -> float:
    """计算RSI指标。

    来源: QuantDinger multi_indicator_composite.py
    RSI > 70: 超买（可能高位接盘）
    RSI < 30: 超卖（可能低位机会）
    RSI 30-50: 回调区间（均值回归买点）

    Returns: RSI值 (0-100)，数据不足返回50（中性）
    """
    if len(nav_values) < period + 1:
        return 50.0

    deltas = [nav_values[i] - nav_values[i-1] for i in range(1, len(nav_values))]
    recent = deltas[-(period):]

    gains = [d for d in recent if d > 0]
    losses = [-d for d in recent if d < 0]

    avg_gain = sum(gains) / period if gains else 0
    avg_loss = sum(losses) / period if losses else 0

    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi


def compute_macd(nav_values: List[float],
                 fast: int = 12, slow: int = 26, signal: int = 9) -> Tuple[float, float, float]:
    """计算MACD指标。

    来源: QuantDinger multi_indicator_composite.py
    使用指数移动平均(EMA)。

    Returns: (macd_line, signal_line, histogram)
    """
    if len(nav_values) < slow + signal:
        return (0.0, 0.0, 0.0)

    def ema(data, period):
        multiplier = 2 / (period + 1)
        ema_val = data[0]
        for v in data[1:]:
            ema_val = v * multiplier + ema_val * (1 - multiplier)
        return ema_val

    # 计算快慢EMA序列
    def ema_series(data, period):
        multiplier = 2 / (period + 1)
        result = [data[0]]
        for v in data[1:]:
            result.append(v * multiplier + result[-1] * (1 - multiplier))
        return result

    ema_fast = ema_series(nav_values, fast)
    ema_slow = ema_series(nav_values, slow)

    # MACD线 = 快EMA - 慢EMA
    macd_line = [f - s for f, s in zip(ema_fast, ema_slow)]

    # 信号线 = MACD的EMA
    if len(macd_line) < slow:
        return (macd_line[-1] if macd_line else 0, 0, 0)

    signal_line = ema(macd_line[-(signal + 10):], signal)
    histogram = macd_line[-1] - signal_line

    return (macd_line[-1], signal_line, histogram)


def compute_bollinger_bands(nav_values: List[float],
                            period: int = 20, std_mult: float = 2.0) -> Tuple[float, float, float, float]:
    """计算布林带。

    Returns: (upper, middle, lower, %b)
    %b > 1.0: 价格突破上轨（超买）
    %b < 0.0: 价格突破下轨（超卖）
    """
    if len(nav_values) < period:
        return (0, 0, 0, 0.5)

    recent = nav_values[-period:]
    middle = statistics.mean(recent)
    std = statistics.stdev(recent) if len(recent) > 1 else 0
    upper = middle + std_mult * std
    lower = middle - std_mult * std

    current = nav_values[-1]
    if upper == lower:
        pct_b = 0.5
    else:
        pct_b = (current - lower) / (upper - lower)

    return (upper, middle, lower, pct_b)


def compute_atr(nav_values: List[float], period: int = 14) -> float:
    """计算 ATR (Average True Range) — 真实波幅均值。

    ATR 是衡量波动率的标准指标，常用于：
    - 仓位管理：高 ATR → 小仓位（防止单日大幅亏损）
    - 止损设置：止损 = 当前价 - k * ATR
    - 趋势强度：ATR 上升表示趋势增强

    简化版本（场外基金场景用日收益率代替真实波幅）：
    - TR = |今日净值 - 昨日净值| （基金无跳空缺口，无需 max(HL-C, ...) 形式）
    - ATR = TR 的 period 日简单平均

    Args:
        nav_values: 净值序列（已转换自累计收益率%）
        period: 周期，默认 14

    Returns:
        float: ATR 净值单位。例如 ATR=0.02 表示日均波动 2%
    """
    if len(nav_values) < period + 1:
        return 0.0

    trs = []
    for i in range(1, len(nav_values)):
        trs.append(abs(nav_values[i] - nav_values[i - 1]))

    # 取最近 period 个 TR 的平均
    recent_trs = trs[-period:]
    return sum(recent_trs) / len(recent_trs) if recent_trs else 0.0


def compute_atr_pct(nav_values: List[float], period: int = 14) -> float:
    """计算 ATR 占当前净值的百分比（便于跨基金比较）。

    Returns:
        float: 例如 0.015 表示日均波动 1.5%
    """
    atr = compute_atr(nav_values, period)
    if not nav_values or nav_values[-1] <= 0:
        return 0.0
    return atr / nav_values[-1]


def atr_position_size(available_cash: float, atr_pct: float,
                      target_daily_risk: float = 0.005,
                      baseline_atr: float = 0.015) -> float:
    """基于 ATR 的仓位计算（波动率倒数加权）。

    原理（风险平价思想）：
    - 每只基金每天损失不应超过 target_daily_risk
    - 高波动基金（高 ATR）应配小仓位
    - 低波动基金（低 ATR）应配大仓位
    - 仓位 = (target_daily_risk / ATR_pct) * 可用资金

    与 baseline_atr 的比值作为调整因子：
    - ATR == baseline → 调整因子 = 1.0
    - ATR > baseline  → 调整因子 < 1.0（减仓）
    - ATR < baseline  → 调整因子 > 1.0（加仓）

    Args:
        available_cash: 可用资金
        atr_pct: 当前 ATR 占净值百分比
        target_daily_risk: 目标日损失占总资金比例（默认 0.5%）
        baseline_atr: 基准 ATR（用于归一化），默认 1.5%

    Returns:
        float: 建议买入金额
    """
    if atr_pct <= 0:
        return available_cash * 0.1  # 兜底
    # 基础仓位：让该基金 1 日损失 = target_daily_risk
    base_size = (target_daily_risk / atr_pct) * available_cash
    # 归一化因子：以 baseline_atr 为基准
    norm_factor = baseline_atr / atr_pct
    return base_size * norm_factor


def ma_crossover_signal(nav_values: List[float],
                        short_period: int = 20, long_period: int = 60) -> int:
    """均线交叉信号。

    来源: QuantDinger dual_ma_with_params.py
    Returns:
        1: 金叉（短线上穿长线，买入信号）
       -1: 死叉（短线下穿长线，卖出信号）
        0: 无交叉
    """
    if len(nav_values) < long_period + 2:
        return 0

    ma_short_curr = statistics.mean(nav_values[-short_period:])
    ma_long_curr = statistics.mean(nav_values[-long_period:])
    ma_short_prev = statistics.mean(nav_values[-short_period-1:-1])
    ma_long_prev = statistics.mean(nav_values[-long_period-1:-1])

    # 金叉: 之前短线在长线下方，现在在上方
    if ma_short_prev <= ma_long_prev and ma_short_curr > ma_long_curr:
        return 1
    # 死叉
    if ma_short_prev >= ma_long_prev and ma_short_curr < ma_long_curr:
        return -1
    return 0


def ma_trend(nav_values: List[float],
             short_period: int = 20, long_period: int = 60) -> int:
    """均线趋势方向（非交叉，仅判断当前相对位置）。

    Returns:
        1: 短线在长线上方（上升趋势）
       -1: 短线在长线下方（下降趋势）
        0: 数据不足
    """
    if len(nav_values) < long_period:
        return 0
    ma_short = statistics.mean(nav_values[-short_period:])
    ma_long = statistics.mean(nav_values[-long_period:])
    return 1 if ma_short > ma_long else -1


def compute_overbought_score(nav_values: List[float]) -> float:
    """综合超买评分，融合RSI+布林带+涨幅。

    Returns: 超买扣分值 (0 = 无超买, 负数 = 超买程度)
    - RSI > 75: 扣0.5-1.5分
    - 布林带上轨突破: 扣0.3-0.8分
    - 近20日涨幅 > 15%: 扣0.2-0.5分
    """
    penalty = 0.0

    # RSI超买
    rsi = compute_rsi(nav_values, 14)
    if rsi > 80:
        penalty -= 1.5
    elif rsi > 75:
        penalty -= 1.0
    elif rsi > 70:
        penalty -= 0.5

    # 布林带超买
    _, _, _, pct_b = compute_bollinger_bands(nav_values, 20, 2.0)
    if pct_b > 1.0:
        penalty -= 0.8
    elif pct_b > 0.9:
        penalty -= 0.3

    # 近20日涨幅过大
    if len(nav_values) >= 21:
        ret_20d = (nav_values[-1] / nav_values[-21] - 1) * 100
        if ret_20d > 20:
            penalty -= 0.5
        elif ret_20d > 15:
            penalty -= 0.2

    return penalty


def compute_mean_reversion_score(nav_values: List[float]) -> float:
    """均值回归评分 — 奖励在回调中买入。

    来源: QuantDinger cross_sectional_momentum_rsi.py 的 RSI反转思路
    当基金从近期高点回调但长期趋势仍然向上时，给予买入奖励。

    Returns: 均值回归加分 (0 = 无奖励, 正数 = 奖励)
    - RSI在30-50区间（回调但非超卖）: +0.3-0.5
    - 价格在布林带中轨下方但非下轨: +0.2-0.4
    - 从近期高点回调5-15%但MA趋势向上: +0.3-0.5
    """
    bonus = 0.0

    if len(nav_values) < 30:
        return 0.0

    rsi = compute_rsi(nav_values, 14)

    # RSI在回调区间（30-50）：非超卖但回调中，是好的买点
    if 30 <= rsi <= 50:
        bonus += 0.4
    elif 25 <= rsi < 30:
        # 接近超卖，如果趋势向上则是更好的买点
        trend = ma_trend(nav_values, 20, 60)
        if trend > 0:
            bonus += 0.5

    # 布林带：价格在中轨下方但非下轨突破
    _, middle, _, pct_b = compute_bollinger_bands(nav_values, 20, 2.0)
    if 0.2 < pct_b < 0.5:
        bonus += 0.3

    # 从近期高点回调5-15%但长期趋势向上
    recent_high = max(nav_values[-60:]) if len(nav_values) >= 60 else max(nav_values)
    current = nav_values[-1]
    pullback = (recent_high - current) / recent_high * 100 if recent_high > 0 else 0
    trend = ma_trend(nav_values, 20, 60)
    if 5 <= pullback <= 15 and trend > 0:
        bonus += 0.4

    return bonus


def compute_entry_timing_score(chart_points: List[dict], cutoff_date: str) -> dict:
    """综合择时评分 — 判断当前是否为好的买入时机。

    Args:
        chart_points: [{xAxis: "2026-01-15", yAxis: 5.23}, ...]
        cutoff_date: "2026-03-15"

    Returns: {
        "rsi": float,
        "overbought_penalty": float,
        "mean_reversion_bonus": float,
        "trend": int (1=上升, -1=下降, 0=数据不足),
        "macd_histogram": float,
        "entry_score": float,  # 综合择时分（正=适合买入，负=不适合）
        "should_warn": bool,   # 是否发出超买警告
    }
    """
    valid = [p for p in chart_points if p.get("xAxis", "") <= cutoff_date]
    if len(valid) < 30:
        return {
            "rsi": 50, "overbought_penalty": 0, "mean_reversion_bonus": 0,
            "trend": 0, "macd_histogram": 0, "entry_score": 0, "should_warn": False,
        }

    values = [_float(p.get("yAxis", 0)) for p in valid]
    nav_values = _to_nav(values)

    rsi = compute_rsi(nav_values, 14)
    overbought = compute_overbought_score(nav_values)
    reversion = compute_mean_reversion_score(nav_values)
    trend = ma_trend(nav_values, 20, 60)
    _, _, macd_hist = compute_macd(nav_values)

    # 综合择时分 = 均值回归奖励 + 趋势确认 + MACD方向 - 超买惩罚
    entry_score = reversion + (0.3 if trend > 0 else -0.3) + (0.2 if macd_hist > 0 else -0.1) + overbought

    should_warn = rsi > 70 or overbought < -0.8

    return {
        "rsi": round(rsi, 1),
        "overbought_penalty": round(overbought, 2),
        "mean_reversion_bonus": round(reversion, 2),
        "trend": trend,
        "macd_histogram": round(macd_hist, 4),
        "entry_score": round(entry_score, 2),
        "should_warn": should_warn,
    }


def _float(v, default=0.0):
    try:
        return float(v)
    except (ValueError, TypeError):
        return default


# ============================================================
# 长周期技术指标（周线/年线级别，用于市场状态判断与仓位调节）
# ============================================================

def _resample_weekly(nav_values: List[float]) -> List[float]:
    """将日线净值序列重采样为周线：每5个交易日取最后一个点。

    场外基金按交易日计，5个交易日≈1自然周。
    """
    if not nav_values:
        return []
    # 每5天取最后一天的净值，不足5天的取最后一天
    weekly = []
    for i in range(4, len(nav_values), 5):
        weekly.append(nav_values[i])
    # 如果最后一段不足5天，补上最后一个点
    if len(nav_values) % 5 != 0 and len(nav_values) > 4:
        weekly.append(nav_values[-1])
    return weekly


def compute_weekly_rsi(nav_values: List[float], period: int = 14) -> float:
    """周线RSI：将日线NAV每5天取1点重采样为周线，再算RSI。

    周线RSI比日线RSI更稳定，适合判断中期超买超卖。
    period=14 周 ≈ 3个月。

    Returns: RSI值 (0-100)，数据不足返回50（中性）
    """
    weekly = _resample_weekly(nav_values)
    return compute_rsi(weekly, period)


def compute_weekly_macd(nav_values: List[float],
                        fast: int = 12, slow: int = 26, signal: int = 9) -> Tuple[float, float, float]:
    """周线MACD：将日线NAV重采样为周线后计算MACD。

    周线MACD过滤了日线噪音，交叉信号更可靠。
    注意：period是周线周期，12周≈3个月，26周≈半年。

    Returns: (macd_line, signal_line, histogram)
    """
    weekly = _resample_weekly(nav_values)
    return compute_macd(weekly, fast, slow, signal)


def compute_macd_divergence(nav_values: List[float]) -> Optional[str]:
    """检测周线MACD顶背离/底背离。

    顶背离 = 价格创新高但MACD未创新高 → 返回 "top"（见顶信号）
    底背离 = 价格创新低但MACD未创新低 → 返回 "bottom"（见底信号）
    无背离 = 返回 None

    算法：将日线重采样为周线，找近120周（≈2.5年）内的价格局部高/低点，
    对比最近两个高点（或低点）的价格与MACD值。

    Args:
        nav_values: 日线净值序列

    Returns: "top" / "bottom" / None
    """
    weekly = _resample_weekly(nav_values)
    if len(weekly) < 60:  # 至少60周数据
        return None

    # 限制到最近120周（约2.5年）便于找拐点
    lookback = weekly[-120:] if len(weekly) > 120 else weekly[:]

    # 计算每周MACD值序列（需要足够数据）
    def _ema_series(data, period):
        multiplier = 2 / (period + 1)
        result = [data[0]]
        for v in data[1:]:
            result.append(v * multiplier + result[-1] * (1 - multiplier))
        return result

    if len(lookback) < 26 + 9:
        return None

    ema_fast = _ema_series(lookback, 12)
    ema_slow = _ema_series(lookback, 26)
    macd_series = [f - s for f, s in zip(ema_fast, ema_slow)]

    if len(macd_series) < 9:
        return None

    # 信号线序列
    sig_multiplier = 2 / (9 + 1)
    signal_series = [macd_series[0]]
    for v in macd_series[1:]:
        signal_series.append(v * sig_multiplier + signal_series[-1] * (1 - sig_multiplier))

    histogram = [m - s for m, s in zip(macd_series, signal_series)]

    # 找价格的局部极值点（窗口=5周）
    window = 5
    highs = []  # [(index, price, macd)]
    lows = []
    for i in range(window, len(lookback) - window):
        is_high = all(lookback[i] >= lookback[i - j] for j in range(1, window + 1)) and \
                  all(lookback[i] >= lookback[i + j] for j in range(1, window + 1))
        is_low = all(lookback[i] <= lookback[i - j] for j in range(1, window + 1)) and \
                 all(lookback[i] <= lookback[i + j] for j in range(1, window + 1))
        if is_high:
            highs.append((i, lookback[i], macd_series[i]))
        if is_low:
            lows.append((i, lookback[i], macd_series[i]))

    # 顶背离：最近两个高点，价格创新高但MACD未创新高
    if len(highs) >= 2:
        idx1, price1, macd1 = highs[-2]
        idx2, price2, macd2 = highs[-1]
        # 价格新高（price2 > price1）但MACD未新高（macd2 < macd1）
        if price2 > price1 and macd2 < macd1:
            return "top"

    # 底背离：最近两个低点，价格创新低但MACD未创新低
    if len(lows) >= 2:
        idx1, price1, macd1 = lows[-2]
        idx2, price2, macd2 = lows[-1]
        # 价格新低（price2 < price1）但MACD未新低（macd2 > macd1）
        if price2 < price1 and macd2 > macd1:
            return "bottom"

    return None


def compute_weekly_bollinger(nav_values: List[float],
                             period: int = 20, std_mult: float = 2.0) -> Tuple[float, float, float, float]:
    """周线布林带：将日线NAV重采样为周线后计算布林带。

    period=20 周 ≈ 4个月。%b > 0.8 接近上轨，%b < 0.2 接近下轨。

    Returns: (upper, middle, lower, %b)
    """
    weekly = _resample_weekly(nav_values)
    return compute_bollinger_bands(weekly, period, std_mult)


def compute_ma_250(nav_values: List[float]) -> Tuple[float, float, bool]:
    """250日移动平均线（年线）。

    年线是经典的牛熊分界线：
    - 价格在年线上方 → 中长期牛市
    - 价格跌破年线 → 中长期熊市

    Args:
        nav_values: 日线净值序列

    Returns: (current_nav, ma_250, above_ma)
        - current_nav: 当前净值
        - ma_250: 250日均线值（数据不足时返回当前净值）
        - above_ma: 当前净值是否在年线上方
    """
    if not nav_values:
        return (0.0, 0.0, False)

    current = nav_values[-1]
    if len(nav_values) < 250:
        # 数据不足，返回中性值
        return (current, current, True)

    ma_250 = statistics.mean(nav_values[-250:])
    above_ma = current > ma_250
    return (current, ma_250, above_ma)
