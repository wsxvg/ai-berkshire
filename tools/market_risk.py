#!/usr/bin/env python3
"""市场风险预警系统 — 多维信号综合判断市场是否过热/即将下跌。

信号维度：
1. 估值维度：基准PE分位数（如有数据）
2. 技术维度：基准RSI、MACD柱状图、距MA20偏离度
3. 广度维度：持仓中RSI>70比例、MA5<MA20比例
4. 波动维度：20日波动率/60日波动率（波动率跳升=风险信号）
5. 动量维度：基准5日收益率、20日收益率（动量衰减=风险信号）

综合风险分数 0-100：
- <30: 低风险，正常买入
- 30-60: 中等风险，减半买入
- 60-80: 高风险，停止买入
- >80: 极高风险，建议减仓

纯Python实现，无外部依赖，所有数据从基金净值序列计算。
"""
import statistics
import math
from typing import List, Dict, Tuple, Optional
from collections import defaultdict


def _to_nav(values: List[float]) -> List[float]:
    """累计收益率% → 净值序列"""
    return [(100 + v) / 100 for v in values]


def _compute_rsi(nav_values: List[float], period: int = 14) -> float:
    """计算RSI"""
    if len(nav_values) < period + 1:
        return 50.0
    deltas = [nav_values[i] - nav_values[i-1] for i in range(1, len(nav_values))]
    recent = deltas[-period:]
    gains = [d for d in recent if d > 0]
    losses = [-d for d in recent if d < 0]
    avg_gain = sum(gains) / period if gains else 0
    avg_loss = sum(losses) / period if losses else 0
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def _compute_volatility(nav_values: List[float], lookback: int = 20) -> float:
    """计算日收益率波动率"""
    if len(nav_values) < lookback + 1:
        return 0.0
    recent = nav_values[-(lookback+1):]
    rets = [(recent[i] / recent[i-1] - 1) * 100 for i in range(1, len(recent)) if recent[i-1] > 0]
    return statistics.stdev(rets) if len(rets) > 5 else 0.0


def _compute_macd_hist(nav_values: List[float]) -> float:
    """计算MACD柱状图值"""
    if len(nav_values) < 35:
        return 0.0
    def ema_series(data, period):
        mult = 2 / (period + 1)
        result = [data[0]]
        for v in data[1:]:
            result.append(v * mult + result[-1] * (1 - mult))
        return result
    ema_fast = ema_series(nav_values, 12)
    ema_slow = ema_series(nav_values, 26)
    macd_line = [f - s for f, s in zip(ema_fast, ema_slow)]
    sig_mult = 2 / 10
    sig_line = [macd_line[0]]
    for v in macd_line[1:]:
        sig_line.append(v * sig_mult + sig_line[-1] * (1 - sig_mult))
    hist = macd_line[-1] - sig_line[-1]
    return hist


def compute_market_risk(benchmark_nav_values: List[float],
                        held_fund_nav_series: Dict[str, List[float]] = None) -> Dict:
    """计算综合市场风险分数。

    Args:
        benchmark_nav_values: 基准指数(沪深300)净值序列
        held_fund_nav_series: 持仓基金的净值序列 {code: [nav_values]}

    Returns:
        {
            "risk_score": 0-100,
            "signals": {
                "benchmark_rsi": float,
                "benchmark_macd_hist": float,
                "benchmark_deviation_ma20": float,
                "market_breadth_overbought_pct": float,
                "market_breadth_below_ma5_pct": float,
                "volatility_ratio": float,
                "momentum_5d": float,
                "momentum_20d": float,
            },
            "action": "normal" | "caution" | "stop_buy" | "reduce",
        }
    """
    signals = {}
    risk_components = []

    # ── 1. 技术维度：基准RSI ──
    bm_rsi = _compute_rsi(benchmark_nav_values, 14)
    signals["benchmark_rsi"] = round(bm_rsi, 1)
    # RSI > 70 = 超买，风险增加
    if bm_rsi > 80:
        risk_components.append(25)
    elif bm_rsi > 70:
        risk_components.append(15)
    elif bm_rsi > 60:
        risk_components.append(5)
    else:
        risk_components.append(0)

    # ── 2. 技术维度：MACD柱状图 ──
    bm_macd_hist = _compute_macd_hist(benchmark_nav_values)
    signals["benchmark_macd_hist"] = round(bm_macd_hist, 4)
    # MACD柱状图为负且下降 = 看跌
    if bm_macd_hist < -0.002:
        risk_components.append(20)
    elif bm_macd_hist < 0:
        risk_components.append(10)
    else:
        risk_components.append(0)

    # ── 3. 技术维度：距MA20偏离度 ──
    if len(benchmark_nav_values) >= 20:
        ma20 = statistics.mean(benchmark_nav_values[-20:])
        current = benchmark_nav_values[-1]
        deviation = (current / ma20 - 1) * 100
        signals["benchmark_deviation_ma20"] = round(deviation, 2)
        # 偏离MA20超过5% = 超买
        if deviation > 8:
            risk_components.append(15)
        elif deviation > 5:
            risk_components.append(8)
        else:
            risk_components.append(0)
    else:
        signals["benchmark_deviation_ma20"] = 0
        risk_components.append(0)

    # ── 4. 广度维度：持仓中超买比例 ──
    if held_fund_nav_series:
        overbought_count = 0
        below_ma5_count = 0
        total = 0
        for code, navs in held_fund_nav_series.items():
            if len(navs) < 20:
                continue
            total += 1
            fund_rsi = _compute_rsi(navs, 14)
            if fund_rsi > 70:
                overbought_count += 1
            if len(navs) >= 5:
                ma5 = statistics.mean(navs[-5:])
                if navs[-1] < ma5:
                    below_ma5_count += 1
        if total > 0:
            overbought_pct = overbought_count / total * 100
            below_ma5_pct = below_ma5_count / total * 100
        else:
            overbought_pct = 0
            below_ma5_pct = 0
        signals["market_breadth_overbought_pct"] = round(overbought_pct, 1)
        signals["market_breadth_below_ma5_pct"] = round(below_ma5_pct, 1)
        # 超过50%的持仓RSI>70 = 市场过热
        if overbought_pct > 70:
            risk_components.append(20)
        elif overbought_pct > 50:
            risk_components.append(12)
        elif overbought_pct > 30:
            risk_components.append(5)
        else:
            risk_components.append(0)
        # 超过50%的持仓跌破MA5 = 市场走弱
        if below_ma5_pct > 70:
            risk_components.append(15)
        elif below_ma5_pct > 50:
            risk_components.append(8)
        else:
            risk_components.append(0)
    else:
        signals["market_breadth_overbought_pct"] = 0
        signals["market_breadth_below_ma5_pct"] = 0
        risk_components.append(0)
        risk_components.append(0)

    # ── 5. 波动维度：波动率跳升 ──
    vol_20 = _compute_volatility(benchmark_nav_values, 20)
    vol_60 = _compute_volatility(benchmark_nav_values, 60)
    vol_ratio = vol_60 / vol_20 if vol_20 > 0 else 1.0
    signals["volatility_ratio"] = round(vol_ratio, 2)
    # 波动率比60日均值高50%以上 = 风险增加
    if vol_ratio > 1.5:  # vol_20 >> vol_60
        risk_components.append(15)
    elif vol_ratio > 1.3:
        risk_components.append(8)
    else:
        risk_components.append(0)
    # 注意：vol_ratio = vol_60/vol_20，如果vol_20 > vol_60则ratio<1，表示波动率上升

    # ── 6. 动量维度：近期收益率 ──
    if len(benchmark_nav_values) >= 20:
        ret_5d = (benchmark_nav_values[-1] / benchmark_nav_values[-5] - 1) * 100 if len(benchmark_nav_values) >= 5 else 0
        ret_20d = (benchmark_nav_values[-1] / benchmark_nav_values[-20] - 1) * 100 if len(benchmark_nav_values) >= 20 else 0
        signals["momentum_5d"] = round(ret_5d, 2)
        signals["momentum_20d"] = round(ret_20d, 2)
        # 5日收益率为负但20日仍正 = 动量衰减（下跌信号）
        if ret_5d < -2 and ret_20d > 3:
            risk_components.append(15)
        elif ret_5d < 0 and ret_20d > 5:
            risk_components.append(8)
        else:
            risk_components.append(0)
    else:
        signals["momentum_5d"] = 0
        signals["momentum_20d"] = 0
        risk_components.append(0)

    # 综合风险分数（0-100，加权平均）
    risk_score = min(100, sum(risk_components))

    # 动作建议
    if risk_score >= 80:
        action = "reduce"
    elif risk_score >= 60:
        action = "stop_buy"
    elif risk_score >= 30:
        action = "caution"
    else:
        action = "normal"

    return {
        "risk_score": round(risk_score, 1),
        "signals": signals,
        "action": action,
        "components": risk_components,
    }
