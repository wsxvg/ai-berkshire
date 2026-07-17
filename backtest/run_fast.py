#!/usr/bin/env python3
"""精选版：A共识5 + B评分5 + J最优6 = 16策略, ~3h出结论"""
import sys, json, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backtest.engine.backtest import run_backtest

BASE = {
    "start_date": "2025-01-05", "end_date": "2026-07-01",
    "initial_cash": 100000, "monthly_injection": 0,
    "weights": {"quality": 25, "cost": 20, "manager": 20, "momentum": 15, "smart_money": 20},
}

# Only key strategies: consensus scan + score scan + optimal combos
STRATEGIES = [
    # === A: 共识门槛扫描 ===
    {"name": "A1_共识=3",  "group": "共识扫描", "desc": "3人买入即触发", "config": {"min_consensus": 3}},
    {"name": "A2_共识=4",  "group": "共识扫描", "desc": "4人共识",         "config": {"min_consensus": 4}},
    {"name": "A3_共识=5",  "group": "共识扫描", "desc": "5人共识(基准)",   "config": {"min_consensus": 5}},
    {"name": "A4_共识=6",  "group": "共识扫描", "desc": "6人共识",         "config": {"min_consensus": 6}},
    {"name": "A5_共识=8",  "group": "共识扫描", "desc": "8人共识(极端)",   "config": {"min_consensus": 8}},
    # === B: 评分门槛扫描 ===
    {"name": "B1_评分2.5", "group": "评分扫描", "desc": "低门槛广撒网",    "config": {"min_score": 2.5}},
    {"name": "B2_评分3.0", "group": "评分扫描", "desc": "中等偏低",        "config": {"min_score": 3.0}},
    {"name": "B3_评分3.3", "group": "评分扫描", "desc": "基准门槛",        "config": {"min_score": 3.3}},
    {"name": "B4_评分3.5", "group": "评分扫描", "desc": "偏严格",          "config": {"min_score": 3.5}},
    {"name": "B5_评分3.8", "group": "评分扫描", "desc": "极严格精选",      "config": {"min_score": 3.8}},
    # === J: 最优组合 (用A+B结论的最优值打包) ===
    {"name": "J1_进化最优", "group": "最优组合",
     "desc": "best_config进化4代最优基因",
     "config": {"weights": {"quality": 19.41, "cost": 18.3, "manager": 17.68, "momentum": 19.15, "smart_money": 24.72},
               "min_score": 3.52, "min_consensus": 5, "max_position_pct": 19.89, "cash_reserve_pct": 0.14,
               "cooldown_days": 5, "take_profit_pct": 15, "stop_loss_pct": -10, "dynamic_ranking": True,
               "ranking_window": 90, "max_correlation": 0.85, "max_holdings": 5,
               "cooldown_profit_days": 10, "cooldown_loss_days": 30}},
    {"name": "J2_高共识精选", "group": "最优组合",
     "desc": "共识8+评分3.8+集中5只+移动止盈",
     "config": {"min_consensus": 8, "min_score": 3.8, "max_correlation": 0.80, "max_holdings": 5,
               "trailing_tp_activate": 10, "trailing_tp_drawdown": 8, "timing_filter": True, "block_overbought": True}},
    {"name": "J3_广覆盖森林", "group": "最优组合",
     "desc": "共识3+评分2.5+分散12只",
     "config": {"min_consensus": 3, "min_score": 2.5, "max_correlation": 0.90, "max_holdings": 12}},
    {"name": "J4_SM跟投增强", "group": "最优组合",
     "desc": "SM35+共识6+择时全开+移动止盈",
     "config": {"weights": {"quality": 18, "cost": 13, "manager": 16, "momentum": 18, "smart_money": 35},
               "min_consensus": 6, "min_score": 3.5, "timing_filter": True, "block_overbought": True,
               "net_signal": True, "trailing_tp_activate": 10, "trailing_tp_drawdown": 8,
               "max_correlation": 0.80, "max_holdings": 6}},
    {"name": "J5_长持稳健", "group": "最优组合",
     "desc": "质量35+保守风控+不限熊市",
     "config": {"weights": {"quality": 35, "cost": 18, "manager": 20, "momentum": 12, "smart_money": 15},
               "min_consensus": 4, "min_score": 3.5, "stop_loss_pct": -15, "take_profit_pct": 35,
               "cooldown_days": 10, "bear_market_no_buy": False, "max_correlation": 0.80, "max_holdings": 5}},
    {"name": "J6_全功能极限", "group": "最优组合",
     "desc": "ML+择时+移动止盈+Kelly+再平衡",
     "config": {"weights": {"quality": 20, "cost": 15, "manager": 17, "momentum": 20, "smart_money": 28},
               "min_consensus": 5, "min_score": 3.3, "timing_filter": True, "block_overbought": True,
               "dynamic_ranking": True, "ranking_window": 90, "trailing_tp_activate": 10, "trailing_tp_drawdown": 8,
               "net_signal": True, "max_correlation": 0.80, "max_holdings": 6}},
]

results = []
t_start = time.time()
for i, s in enumerate(STRATEGIES):
    print(f"\n{'='*60}")
    print(f"[{i+1}/{len(STRATEGIES)}] {s['name']} | {s['group']} | {s['desc']}")
    print(f"{'='*60}")
    cfg = dict(BASE)
    cfg.update(s["config"])
    if "weights" in s["config"]:
        cfg["weights"] = dict(BASE["weights"])
        cfg["weights"].update(s["config"]["weights"])
    try:
        r = run_backtest(cfg)
        irr = ((1 + r["total_return"]/100) ** (12/18) - 1) * 100
        sharpe = r.get("sharpe_ratio", r["total_return"] / max(r["max_drawdown"], 1))
        results.append({
            "name": s["name"], "group": s["group"], "desc": s["desc"],
            "return": round(r["total_return"], 2), "annualized": round(irr, 2),
            "dd": round(r["max_drawdown"], 2), "trades": r["trade_count"],
            "sharpe": round(sharpe, 2), "vs_benchmark": round(r["total_return"] - r.get("benchmark_return", 0), 2),
            "fees": round(r.get("total_fees", 0), 1), "config": s["config"],
        })
        print(f"  -> 收益{r['total_return']:+.2f}% 年化{irr:+.1f}% DD{r['max_drawdown']:.2f}% 夏普{sharpe:.2f}")
    except Exception as e:
        import traceback
        print(f"  -> FAILED: {e}")
        traceback.print_exc()
        results.append({"name": s["name"], "group": s["group"], "error": str(e)})

elapsed = (time.time() - t_start) / 60
valid = [r for r in results if "return" in r]
valid.sort(key=lambda x: x["sharpe"], reverse=True)

print(f"\n\n{'='*80}")
print(f"精选策略排名 ({len(valid)}/{len(STRATEGIES)} 完成, {elapsed:.0f} min)")
print(f"{'='*80}")
print(f"{'策略':20s} {'分组':10s} {'收益':>8s} {'年化':>8s} {'回撤':>8s} {'夏普':>7s} {'超额':>8s}")
print(f"{'-'*75}")
for r in valid:
    print(f"{r['name']:20s} {r['group']:10s} {r['return']:>+7.2f}% {r['annualized']:>+7.1f}% "
          f"{r['dd']:>7.2f}% {r['sharpe']:>6.2f} {r['vs_benchmark']:>+7.2f}%")

print(f"\nTOP 3:")
for i, r in enumerate(valid[:3]):
    print(f"  #{i+1} {r['name']}: 收益{r['return']:+.1f}% 夏普{r['sharpe']:.2f} 回撤{r['dd']:.1f}%")
    print(f"     配置: {json.dumps(r.get('config',{}), ensure_ascii=False)}")

out = Path(__file__).resolve().parent / "reports" / "strategy_fast_v1.json"
out.parent.mkdir(parents=True, exist_ok=True)
json.dump({"strategies": valid, "period": "2025-01-05 ~ 2026-07-01", "elapsed_min": round(elapsed, 1)},
          open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print(f"\n报告: {out}")
