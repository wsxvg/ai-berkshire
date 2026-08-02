"""自定义时间段回测 — 6-8 月和单 7 月。

使用 R4_BASELINE 模型 (max_holdings=12, weights=20/25/15/10/30)。
模型在 train_end 日期打分, 模拟 test period 的收益率。
"""
import copy, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backtest.engine.backtest import run_backtest

BASE_CFG = {
    "initial_cash": 10000,
    "no_stop_loss": True,
    "take_profit_pct": 50.0,
    "min_consensus": 3,
    "max_holdings": 5,
    "kelly_cap_bull": 0.5,
    "kelly_cap_bear": 0.25,
    "pyramiding_enabled": False,
    "smart_swap": True,
    "regime_specific": True,
}

R4_OVERRIDE = {
    "max_holdings": 12,
    "weights": {"quality": 20, "cost": 25, "manager": 15, "momentum": 10, "smart_money": 30},
    "no_stop_loss": True,
}


def run_period(name, start_date, end_date):
    cfg = copy.deepcopy(BASE_CFG)
    cfg.update(R4_OVERRIDE)
    cfg['start_date'] = start_date
    cfg['end_date'] = end_date
    print(f"\n{'='*60}")
    print(f"  {name}")
    print(f"  期间: {start_date} → {end_date}")
    print(f"{'='*60}")
    res = run_backtest(cfg, clear_cache=True)
    ret = res.get('total_return', 0)
    bench = res.get('benchmark_csi300', res.get('benchmark_return', 0))
    trades = res.get('trade_count', 0)
    fees = res.get('total_fees', 0)
    max_dd = res.get('max_drawdown', 0)
    wr = res.get('win_rate', 0)
    avg_hld = res.get('avg_hold_days', 0)
    
    print(f"\n  📊 结果:")
    print(f"  策略收益率:    {ret:+.2f}%")
    print(f"  CSI300 基准:  {bench:+.2f}%")
    print(f"  超额收益:      {ret - bench:+.2f}%")
    print(f"  交易次数:      {trades}")
    print(f"  总费用:        {fees:.0f}")
    print(f"  最大回撤:      {max_dd:.1f}%")
    print(f"  胜率:          {wr:.1f}%")
    print(f"  平均持仓天数:  {avg_hld:.0f}")
    return {
        'name': name, 'start': start_date, 'end': end_date,
        'return': ret, 'benchmark': bench, 'excess': ret - bench,
        'trades': trades, 'fees': fees, 'max_dd': max_dd,
        'win_rate': wr, 'avg_hold_days': avg_hld,
    }


if __name__ == "__main__":
    print("=" * 60)
    print("  R4_BASELINE 自定义时间段回测")
    print("  模型: max_holdings=12, weights=Q20/C25/M15/Mo10/SM30")
    print("=" * 60)
    
    # 因为 8 月数据尚未全部确认 (最新只到 7/31).
    # 所以 "6-8月" 改为 "6/1-7/31", "单7月" 为 "7/1-7/31"
    results = []
    
    # Period A: June 1 - July 31 (最接近 6-8 月)
    results.append(run_period(
        "A. 6/1 → 7/31 (含 6月+7月, 截至最新数据)",
        "2026-06-01", "2026-07-31"
    ))
    
    # Period B: July only
    results.append(run_period(
        "B. 仅 7月 (7/1 → 7/31)",
        "2026-07-01", "2026-07-31"
    ))
    
    print("\n" + "=" * 60)
    print("  汇总")
    print("=" * 60)
    for r in results:
        print(f"  {r['name']:<35}  收益={r['return']:+.2f}%  基准={r['benchmark']:+.2f}%  超额={r['excess']:+.2f}%")
    
    # Save results
    out_path = Path("v9-results/custom_period_backtest.json")
    out_path.parent.mkdir(exist_ok=True)
    out_path.write_text(json.dumps({
        'note': '8月数据尚未完全确认(最新7/31), 因此6-8月改为6/1-7/31',
        'periods': results,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n结果已保存: {out_path}")
