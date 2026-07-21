#!/usr/bin/env python3
"""3年完整回测验证最终激进方案（含kelly_allocate+阶梯止盈改进）
只跑1个策略，详细输出分段收益和年化"""
import sys, json, time, copy, os, math
os.environ["PYTHONUNBUFFERED"] = "1"
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))

from backtest.engine.backtest import run_backtest

BASE = json.loads((PROJECT / "data" / "evolution" / "best_config.json").read_text("utf-8"))["config"]

# 3年完整回测
BASE["start_date"] = "2023-07-17"
BASE["end_date"] = "2026-07-17"
BASE["initial_cash"] = 100000

print("=" * 70, flush=True)
print("最终激进方案 3年完整回测 (2023-07-17 ~ 2026-07-17)", flush=True)
print("含改进: 3/4凯利 + 50%单次上限 + 平缓阶梯止盈(0.3/0.3/0.2/0.2)", flush=True)
print("=" * 70, flush=True)

t0 = time.time()
print("\n[RUN] FINAL_AGGRESSIVE_3y...", flush=True)
try:
    r = run_backtest(BASE)
    elapsed = time.time() - t0

    # 修复: 用正确的字段名
    final_value = r.get("final_value", 0)
    total_return = r.get("total_return", 0)
    annualized_return = r.get("annualized_return", 0)  # 修复字段名
    annualized_volatility = r.get("annualized_volatility", 0)
    max_dd = r.get("max_drawdown", 0)
    sharpe = r.get("sharpe_ratio", 0)
    calmar = r.get("calmar_ratio", 0)
    trades = r.get("trade_count", 0)
    benchmark_return = r.get("benchmark_return", 0)
    buyhold_return = r.get("buyhold_return", 0)
    total_fees = r.get("total_fees", 0)

    # 分段收益 (修复: 字段是 total 不是 value)
    daily_values = r.get("daily_values", [])
    seg = {}
    if daily_values:
        for seg_name, (start, end) in [("A_bear_2023H2", ("2023-07-17", "2024-06-30")),
                                         ("B_oscillate_2024H2_2025H1", ("2024-07-01", "2025-06-30")),
                                         ("C_bull_2025H2_2026H1", ("2025-07-01", "2026-07-17"))]:
            start_val = None
            end_val = None
            for dv in daily_values:
                d = dv.get("date", "")
                if d <= start:
                    start_val = dv.get("total", 0)
                if d <= end:
                    end_val = dv.get("total", 0)
            if start_val and end_val and start_val > 0:
                seg[seg_name] = round((end_val / start_val - 1) * 100, 2)

    print(f"\n{'='*70}", flush=True)
    print(f"最终激进方案 3年完整回测结果 ({elapsed:.0f}s)", flush=True)
    print(f"{'='*70}", flush=True)
    print(f"  最终资产:     ¥{final_value:>12,.2f}", flush=True)
    print(f"  总收益率:     {total_return:>+8.2f}%", flush=True)
    print(f"  年化收益率:   {annualized_return:>+8.2f}%", flush=True)
    print(f"  年化波动率:   {annualized_volatility:>8.2f}%", flush=True)
    print(f"  最大回撤:     {max_dd:>8.2f}%", flush=True)
    print(f"  夏普比率:     {sharpe:>8.2f}", flush=True)
    print(f"  卡玛比率:     {calmar:>8.2f}", flush=True)
    print(f"  交易次数:     {trades:>8d}", flush=True)
    print(f"  总手续费:     ¥{total_fees:>12,.2f}", flush=True)
    print(f"  基准(沪深300): {benchmark_return:>+8.2f}%", flush=True)
    print(f"  买入持有:     {buyhold_return:>+8.2f}%", flush=True)
    print(f"\n  分段收益:", flush=True)
    for k, v in seg.items():
        print(f"    {k}: {v:>+8.2f}%", flush=True)

    # 手动计算年化（验证）
    if daily_values:
        n_days = len(daily_values)
        years = n_days / 252.0
        if years > 0 and final_value > 0:
            manual_ann = (math.pow(final_value / 100000, 1.0 / years) - 1) * 100
            print(f"\n  手动年化(252天/年, {n_days}天, {years:.2f}年): {manual_ann:>+8.2f}%", flush=True)
        # 按日历年算
        from datetime import datetime
        d0 = daily_values[0].get("date", "")
        d1 = daily_values[-1].get("date", "")
        if d0 and d1:
            days = (datetime.strptime(d1, "%Y-%m-%d") - datetime.strptime(d0, "%Y-%m-%d")).days
            years_cal = days / 365.25
            if years_cal > 0:
                cal_ann = (math.pow(final_value / 100000, 1.0 / years_cal) - 1) * 100
                print(f"  手动年化(日历年, {days}天, {years_cal:.2f}年): {cal_ann:>+8.2f}%", flush=True)

    # 保存结果
    out = PROJECT / "backtest" / "reports" / "final_aggressive_3y.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    result = {
        "label": "FINAL_AGGRESSIVE_3y",
        "final_value": final_value,
        "total_return": total_return,
        "annualized_return": annualized_return,
        "annualized_volatility": annualized_volatility,
        "max_drawdown": max_dd,
        "sharpe": sharpe,
        "calmar": calmar,
        "trades": trades,
        "total_fees": total_fees,
        "benchmark_return": benchmark_return,
        "buyhold_return": buyhold_return,
        "segments": seg,
        "time": round(elapsed, 0),
    }
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n结果已保存: {out}", flush=True)

except Exception as e:
    elapsed = time.time() - t0
    import traceback
    print(f"ERROR: {e} ({elapsed:.0f}s)", flush=True)
    traceback.print_exc()
