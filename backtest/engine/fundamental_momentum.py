"""基本面动量维度 — 不依赖大佬交易的独立评分信号。

基于 fund_charts.json 的累计收益率曲线，计算：
- 滚动收益排名（1M/3M/6M/12M）
- 夏普比率
- 最大回撤
- 动量强度

核心价值: 在大佬交易稀疏的时期（如2024年）仍能产生有效信号。
"""

import statistics, math


def _to_daily_returns(yaxis_values):
    """累计收益率% → 日收益率序列"""
    navs = [(100 + v) / 100 for v in yaxis_values]
    rets = []
    for i in range(1, len(navs)):
        rets.append((navs[i] - navs[i-1]) / navs[i-1])
    return rets


def compute_fundamental_scores(fund_charts, cutoff_date, lookback_days=252):
    """在 cutoff_date 对全体基金计算基本面动量评分。

    返回: {fund_code: {"rank_1m": pct, "rank_3m": pct, "sharpe": float, "max_dd": float, "score": float}}
    """
    results = {}

    for code, points in fund_charts.items():
        # 截断到 cutoff_date
        valid = [p for p in points if p.get("xAxis", "") <= cutoff_date]
        if len(valid) < 60:  # 至少60个交易日
            continue

        yaxis = [float(p.get("yAxis", 0)) for p in valid]
        cur = yaxis[-1]

        # 滚动收益
        n_days = len(yaxis)
        ret_1m = 0
        ret_3m = 0
        ret_6m = 0
        ret_12m = 0

        if n_days >= 21:
            ret_1m = (cur - yaxis[-21]) / (abs(yaxis[-21]) / 100 + 0.01)
        if n_days >= 63:
            ret_3m = (cur - yaxis[-63]) / (abs(yaxis[-63]) / 100 + 0.01)
        if n_days >= 126:
            ret_6m = (cur - yaxis[-126]) / (abs(yaxis[-126]) / 100 + 0.01)
        if n_days >= 252:
            ret_12m = (cur - yaxis[-252]) / (abs(yaxis[-252]) / 100 + 0.01)

        # 夏普比率（从日收益）
        daily_rets = _to_daily_returns(yaxis[-lookback_days:])
        if len(daily_rets) < 20:
            sharpe = 0
        else:
            avg_ret = statistics.mean(daily_rets)
            std_ret = statistics.stdev(daily_rets) if len(daily_rets) > 1 else 0.0001
            sharpe = (avg_ret / std_ret) * math.sqrt(252) if std_ret > 0 else 0

        # 最大回撤
        peak = yaxis[-lookback_days]
        max_dd = 0
        for v in yaxis[-lookback_days:]:
            if v > peak:
                peak = v
            dd = (peak - v) / (abs(peak) + 0.01) * 100
            if dd > max_dd:
                max_dd = dd

        results[code] = {
            "ret_1m": round(ret_1m, 2),
            "ret_3m": round(ret_3m, 2),
            "ret_6m": round(ret_6m, 2),
            "ret_12m": round(ret_12m, 2),
            "sharpe": round(sharpe, 2),
            "max_dd": round(max_dd, 2),
        }

    # 排名（百分位，越高越好）
    if len(results) < 3:
        return {code: {"score": 3.0} for code in results}

    for metric in ["ret_3m", "ret_6m", "sharpe"]:
        vals = [(code, d[metric]) for code, d in results.items() if d[metric] is not None]
        vals.sort(key=lambda x: x[1])  # asc → low rank = bad
        n = len(vals)
        for rank, (code, _) in enumerate(vals):
            results[code][f"{metric}_rank"] = round(rank / max(n-1, 1) * 100, 1)

    # max_dd 排名（越低越好，反向）
    vals = [(code, d["max_dd"]) for code, d in results.items()]
    vals.sort(key=lambda x: x[1])  # asc → low dd = good
    n = len(vals)
    for rank, (code, _) in enumerate(vals):
        results[code]["max_dd_rank"] = round(rank / max(n-1, 1) * 100, 1)

    # 综合评分 (0-5分)
    for code, d in results.items():
        rank_3m = d.get("ret_3m_rank", 50)
        rank_6m = d.get("ret_6m_rank", 50)
        rank_sharpe = d.get("sharpe_rank", 50)
        rank_dd = d.get("max_dd_rank", 50)

        # 各维度映射为0-5
        s_3m = 5 * rank_3m / 100
        s_6m = 5 * rank_6m / 100
        s_sharpe = 5 * rank_sharpe / 100
        s_dd = 5 * rank_dd / 100

        # 加权: 收益40% + 夏普30% + 抗回撤30%
        score = s_3m * 0.2 + s_6m * 0.2 + s_sharpe * 0.3 + s_dd * 0.3
        d["score"] = round(score, 2)

    return results


def score_fundamental_backtest(fund_code, fundamental_scores):
    """获取单只基金的基本面动量评分修正值。

    返回: 修正值（正=加分，负=扣分），用于直接加到 raw_score
    """
    if fund_code not in fundamental_scores:
        return 0.0

    score = fundamental_scores[fund_code].get("score", 3.0)
    # 映射: 3.0分(中性)→修正0, 5.0分→+1.0, 1.0分→-1.0
    return (score - 3.0) * 0.5
