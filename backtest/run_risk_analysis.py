#!/usr/bin/env python3
"""P3: 冠军风险面深度分析 — 从回测结果提取利润贡献/连亏/月度收益

用法:
    py -3.10 backtest/run_risk_analysis.py
"""
import sys, json, copy
from pathlib import Path
from collections import defaultdict

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))
REPORTS_DIR = PROJECT / "backtest" / "reports"

from backtest.engine.backtest import run_backtest

BASE = {
    "start_date": "2025-01-05", "end_date": "2026-07-01",
    "initial_cash": 100000, "monthly_injection": 0,
    "weights": {"quality": 25, "cost": 20, "manager": 20, "momentum": 15, "smart_money": 20},
    "min_score": 0.0, "min_consensus": 2,
    "max_position_pct": 25, "cash_reserve_pct": 0.10,
    "cooldown_days": 0, "take_profit_pct": 50, "stop_loss_pct": -30,
    "trailing_tp_activate": 0, "trailing_tp_drawdown": 10,
    "dynamic_ranking": False, "ranking_window": 90,
    "kelly_cap": 0.2, "momentum_sell": 2.0,
    "profit_mode": "half", "no_stop_loss": False,
    "use_weighted_consensus": False, "cost_penalty": 0, "limit_boost": 0,
    "top_n": 0, "top_n_pct": 0, "consensus_priority": False,
    "net_signal": False, "max_sector_pct": 40, "max_qdii_pct": 100,
    "rebalance": True,
    "fund_type_filter": "active", "sell_consensus": 0,
    "cooldown_profit_days": 10, "cooldown_loss_days": 30,
    "max_correlation": 0, "ml_signal": False, "ml_weight": 1.0,
    "ml_retrain_days": 30, "timing_filter": False,
    "block_overbought": False, "bear_market_no_buy": False,
    "min_score_bull": 0.0, "min_score_neutral": 0.0, "min_score_bear": 0.0,
    "downtrend_penalty": 0.5, "risk_free_rate": 0.025,
    "slippage_pct": 0.0, "verbose_ranking": False,
    "ranking_half_life": 45,
    "exclude_uids": ["14345330", "550027", "8670487", "3032839", "2690580",
                     "10951797", "183856", "1094463", "10542838", "2804244"],
}


def analyze_trades(trades, initial_cash=100000):
    """分析交易记录，提取风险指标"""
    # P3.1: 利润贡献前5 + 亏损前5
    fund_pnl = defaultdict(lambda: {"profit": 0, "buy_dates": [], "sell_dates": [], "name": ""})
    for t in trades:
        code = t.get("code", "")
        action = t.get("action", "")
        amount = t.get("amount", 0)
        fee = t.get("fee", 0)
        reason = t.get("reason", "")
        name = t.get("name", code)
        if code == "CASH":
            continue
        if action in ("sell", "sell_all"):
            fund_pnl[code]["profit"] += amount - fee
            fund_pnl[code]["sell_dates"].append(t.get("date", ""))
            fund_pnl[code]["name"] = name
        elif action == "buy":
            fund_pnl[code]["profit"] -= amount + fee
            fund_pnl[code]["buy_dates"].append(t.get("date", ""))
            fund_pnl[code]["name"] = name

    # 排序
    sorted_pnl = sorted(fund_pnl.items(), key=lambda x: x[1]["profit"], reverse=True)
    top5_profit = [{"code": c, "name": d["name"], "profit": round(d["profit"], 2),
                     "buy_dates": d["buy_dates"][:3], "sell_dates": d["sell_dates"][:3]}
                    for c, d in sorted_pnl[:5] if d["profit"] > 0]
    top5_loss = [{"code": c, "name": d["name"], "profit": round(d["profit"], 2),
                  "buy_dates": d["buy_dates"][:3], "sell_dates": d["sell_dates"][:3]}
                 for c, d in sorted_pnl[-5:] if d["profit"] < 0]

    # P3.2: 连续亏损天数和幅度
    # 从 daily_values 提取
    return {
        "pnl_top5": top5_profit,
        "loss_top5": top5_loss,
        "total_funds_traded": len(fund_pnl),
        "profitable_funds": sum(1 for d in fund_pnl.values() if d["profit"] > 0),
        "losing_funds": sum(1 for d in fund_pnl.values() if d["profit"] < 0),
    }


def analyze_daily_values(daily_values, initial_cash=100000):
    """从每日净值提取连亏/月度收益"""
    if not daily_values:
        return {}

    # P3.2: 最大连续亏损天数
    max_consec_loss_days = 0
    current_loss_streak = 0
    max_single_loss = 0
    max_single_loss_pct = 0
    prev_total = initial_cash

    for dv in daily_values:
        total = dv.get("total", prev_total)
        daily_change = total - prev_total
        if daily_change < 0:
            current_loss_streak += 1
            max_consec_loss_days = max(max_consec_loss_days, current_loss_streak)
            if daily_change < max_single_loss:
                max_single_loss = daily_change
                max_single_loss_pct = (daily_change / prev_total * 100) if prev_total > 0 else 0
        else:
            current_loss_streak = 0
        prev_total = total

    # P3.3: 月度收益分布
    monthly = defaultdict(list)
    for dv in daily_values:
        date = dv.get("date", "")
        month = date[:7]
        if month:
            monthly[month].append(dv.get("total", 0))

    monthly_returns = {}
    prev_month_end = initial_cash
    for month in sorted(monthly.keys()):
        values = monthly[month]
        month_end = values[-1] if values else prev_month_end
        ret = (month_end / prev_month_end - 1) * 100 if prev_month_end > 0 else 0
        monthly_returns[month] = round(ret, 2)
        prev_month_end = month_end

    winning_months = sum(1 for v in monthly_returns.values() if v > 0)
    total_months = len(monthly_returns)
    winrate = winning_months / total_months * 100 if total_months > 0 else 0

    # 最大回撤
    peak = initial_cash
    max_dd = 0
    for dv in daily_values:
        total = dv.get("total", 0)
        if total > peak:
            peak = total
        dd = (peak - total) / peak * 100 if peak > 0 else 0
        max_dd = max(max_dd, dd)

    return {
        "max_consecutive_loss_days": max_consec_loss_days,
        "max_single_loss": round(max_single_loss, 2),
        "max_single_loss_pct": round(max_single_loss_pct, 2),
        "monthly_returns": monthly_returns,
        "winning_months": winning_months,
        "total_months": total_months,
        "monthly_winrate": round(winrate, 1),
        "max_drawdown": round(max_dd, 2),
    }


def main():
    print("=== P3: 冠军风险面深度分析 ===")
    print("跑冠军回测获取完整数据...")
    result = run_backtest(BASE)

    trades = result.get("trades", [])
    daily_values = result.get("daily_values", [])

    print(f"  交易数: {len(trades)}")
    print(f"  日净值数: {len(daily_values)}")

    trade_analysis = analyze_trades(trades, BASE["initial_cash"])
    daily_analysis = analyze_daily_values(daily_values, BASE["initial_cash"])

    report = {
        "total_return": round(result.get("total_return", 0), 2),
        "max_drawdown": daily_analysis.get("max_drawdown", 0),
        "trade_count": result.get("trade_count", 0),
        **trade_analysis,
        **daily_analysis,
    }

    # 打印摘要
    print(f"\n{'='*60}")
    print(f"  P3 风险面分析结果")
    print(f"{'='*60}")

    print(f"\n总收益: {report['total_return']}% | 回撤: {report['max_drawdown']}% | 交易: {report['trade_count']}")
    print(f"交易基金数: {report['total_funds_traded']} (盈利{report['profitable_funds']} / 亏损{report['losing_funds']})")

    print(f"\n--- P3.1 利润贡献 TOP5 ---")
    for f in report.get("pnl_top5", []):
        print(f"  {f['name']} ({f['code']}): +{f['profit']:,.0f}  买入{f['buy_dates'][:1]}")

    print(f"\n--- P3.1 亏损 TOP5 ---")
    for f in report.get("loss_top5", []):
        print(f"  {f['name']} ({f['code']}): {f['profit']:,.0f}  买入{f['buy_dates'][:1]}")

    print(f"\n--- P3.2 连亏与回撤 ---")
    print(f"  最大连续亏损天数: {report.get('max_consecutive_loss_days', 0)}")
    print(f"  最大单日亏损: {report.get('max_single_loss', 0):,.0f} ({report.get('max_single_loss_pct', 0):.2f}%)")

    print(f"\n--- P3.3 月度收益 ---")
    for month, ret in report.get("monthly_returns", {}).items():
        bar = "+" * int(abs(ret) / 2) if ret > 0 else "-" * int(abs(ret) / 2)
        print(f"  {month}: {ret:+.2f}% {bar}")

    print(f"  月胜率: {report.get('winnning_months', 0)}/{report.get('total_months', 0)} = {report.get('monthly_winrate', 0):.1f}%")

    # P9.2: 去赢家影响
    top5_profit_sum = sum(f["profit"] for f in report.get("pnl_top5", []))
    total_profit = sum(f["profit"] for f in report.get("pnl_top5", []) + report.get("loss_top5", []))
    if top5_profit_sum > 0:
        print(f"\n--- P9.2 去赢家分析 ---")
        print(f"  TOP5 利润合计: {top5_profit_sum:,.0f}")
        print(f"  如果去掉 TOP1 赢家 ({report['pnl_top5'][0]['name'] if report.get('pnl_top5') else '?'}):")
        if report.get("pnl_top5"):
            top1 = report["pnl_top5"][0]
            print(f"    去掉 {top1['name']} (+{top1['profit']:,.0f}) 后利润减少 {top1['profit']/total_profit*100:.1f}%")

    # 保存
    out_path = REPORTS_DIR / "champion_risk_profile.json"
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n保存: {out_path}")

    # P9.2: 去 TOP5 赢家的模拟
    # 排除利润最高的 5 只基金，重新回测
    if report.get("pnl_top5"):
        exclude_codes = [f["code"] for f in report["pnl_top5"][:5]]
        print(f"\n=== P9.2: 去掉 TOP5 赢家重新回测 ===")
        print(f"  排除: {exclude_codes}")
        # 通过设置 exclude_fund_codes 来排除（如果引擎支持）
        # 如果引擎不支持，用 stop_loss_pct 更严格来近似
        cfg_no_winners = copy.deepcopy(BASE)
        cfg_no_winners["exclude_fund_codes"] = exclude_codes
        try:
            result2 = run_backtest(cfg_no_winners)
            ret2 = result2.get("total_return", 0)
            print(f"  去赢家收益: {ret2:.2f}% (vs 冠军 {report['total_return']}%)")
            print(f"  降幅: {report['total_return'] - ret2:.2f}pp")
            report["no_winners_return"] = round(ret2, 2)
            report["no_winners_diff"] = round(report["total_return"] - ret2, 2)
        except Exception as e:
            print(f"  去赢家回测失败: {e}")
            report["no_winners_error"] = str(e)

    # 重新保存
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n最终报告: {out_path}")


if __name__ == "__main__":
    main()
