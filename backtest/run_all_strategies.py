#!/usr/bin/env python3
"""统一回测脚本：12种基础策略 + Y5冠军 + 113种参数变体。

用法:
  python backtest/run_all_strategies.py                    # 跑全部 (默认)
  python backtest/run_all_strategies.py --base-only         # 只跑12种基础策略
  python backtest/run_all_strategies.py --champion-only     # 只跑Y5冠军
  python backtest/run_all_strategies.py --sweep-only        # 只跑113种变体
  python backtest/run_all_strategies.py --start 2023-07-17 --end 2026-07-17  # 3年回测
"""
import sys, json, time, argparse
from pathlib import Path
from copy import deepcopy

# 项目根目录
PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))

from backtest.engine.backtest import run_backtest
from backtest.sweep_configs import SWEEP_CONFIGS, SWEEP_LABELS
try:
    with open(Path(__file__).resolve().parent / "mega_sweep_configs.json", encoding="utf-8") as _f:
        MEGA_SWEEP = json.loads(_f.read())
except (FileNotFoundError, ImportError):
    MEGA_SWEEP = []
try:
    with open(Path(__file__).resolve().parent / "player_sweep_configs.json", encoding="utf-8") as _f:
        PLAYER_SWEEP = json.loads(_f.read())
except (FileNotFoundError, ImportError):
    PLAYER_SWEEP = []

# ── 基础配置 ──
BASE = {
    "start_date": "2023-07-17",
    "end_date": "2026-07-17",
    "initial_cash": 10000,
    "monthly_injection": 0,
    "weights": {"quality": 25, "cost": 20, "manager": 20, "momentum": 15, "smart_money": 20},
}

# ── 12种基础策略 (来自 run_strategies.py) ──
BASE_STRATEGIES = [
    {"name": "A 费用敏感", "desc": "高费率惩罚+标准止损", "config": {
        "min_score": 3.3, "stop_loss_pct": -10, "take_profit_pct": 30,
        "profit_mode": "half", "cost_penalty": 1.2, "min_consensus": 2, "fund_type_filter": "all"}},
    {"name": "B 指数优先", "desc": "只买指数,低门槛,不止损", "config": {
        "min_score": 3.0, "no_stop_loss": True, "take_profit_pct": 50,
        "profit_mode": "half", "cost_penalty": 0, "min_consensus": 1, "fund_type_filter": "passive"}},
    {"name": "C 主动精选", "desc": "只买主动,高门槛,高共识", "config": {
        "min_score": 3.5, "stop_loss_pct": -15, "take_profit_pct": 30,
        "profit_mode": "half", "cost_penalty": 0, "min_consensus": 3, "fund_type_filter": "active"}},
    {"name": "D 智能费用", "desc": "费用敏感+标准操作", "config": {
        "min_score": 3.3, "stop_loss_pct": -10, "take_profit_pct": 30,
        "profit_mode": "half", "cost_penalty": 1.0, "min_consensus": 2, "fund_type_filter": "all"}},
    {"name": "E 分批建仓", "desc": "低费用惩罚+浅止损", "config": {
        "min_score": 3.3, "stop_loss_pct": -8, "take_profit_pct": 25,
        "profit_mode": "quarter", "cost_penalty": 1.0, "min_consensus": 2, "fund_type_filter": "all"}},
    {"name": "F 趋势跟踪", "desc": "不止损,阶梯止盈,动量优先", "config": {
        "min_score": 3.3, "no_stop_loss": True, "take_profit_pct": 20,
        "profit_mode": "step", "cost_penalty": 0, "min_consensus": 2,
        "fund_type_filter": "all", "momentum_sell": 1.0}},
    {"name": "G 绝对收益", "desc": "严止损,早止盈,低仓位", "config": {
        "min_score": 3.5, "stop_loss_pct": -5, "take_profit_pct": 15,
        "profit_mode": "all", "cost_penalty": 1.0, "min_consensus": 2,
        "fund_type_filter": "all", "max_position_pct": 15, "momentum_sell": 2.5}},
    {"name": "H 默认基准", "desc": "原始默认参数", "config": {
        "min_score": 3.3, "stop_loss_pct": -15, "take_profit_pct": 30,
        "profit_mode": "half", "cost_penalty": 0, "min_consensus": 2, "fund_type_filter": "all"}},
    {"name": "I 优化器最优", "desc": "min_score=2.5, 浅止损", "config": {
        "min_score": 2.5, "stop_loss_pct": -8, "take_profit_pct": 30,
        "profit_mode": "half", "cost_penalty": 0, "min_consensus": 2, "fund_type_filter": "all"}},
    {"name": "J 买入持有", "desc": "买入后不动, 不止盈不止损", "config": {
        "min_score": 3.3, "no_stop_loss": True, "take_profit_pct": 1000,
        "profit_mode": "half", "cost_penalty": 0, "min_consensus": 2,
        "fund_type_filter": "all", "momentum_sell": 0}},
    {"name": "K 无脑跟投", "desc": "不评分, 2人买我就买", "config": {
        "min_score": 0.0, "stop_loss_pct": -30, "take_profit_pct": 50,
        "profit_mode": "half", "cost_penalty": 0, "min_consensus": 2, "fund_type_filter": "all"}},
    {"name": "L 月定投2500", "desc": "每月定投+均分买入", "config": {
        "min_score": 3.3, "stop_loss_pct": -15, "take_profit_pct": 30,
        "profit_mode": "half", "cost_penalty": 0, "min_consensus": 2,
        "fund_type_filter": "all", "monthly_injection": 2500}},
]

# ── Y5 冠军策略 (来自 best_config.json) ──
Y5_CHAMPION = {
    "name": "Y5 加权共识冠军",
    "desc": "3年回测58.94%/年化16.84%, use_weighted_consensus=true",
    "config": {
        "min_score": 0.0, "min_consensus": 2, "adaptive_consensus": True,
        "max_holdings": 0, "max_position_pct": 40, "cash_reserve_pct": 0.05,
        "cooldown_days": 0, "take_profit_pct": 100, "stop_loss_pct": -30,
        "trailing_tp_activate": 0, "trailing_tp_drawdown": 10,
        "dynamic_ranking": False, "ranking_window": 90, "kelly_cap": 0.35,
        "momentum_sell": 1.5, "profit_mode": "step", "no_stop_loss": False,
        "use_weighted_consensus": True, "cost_penalty": 0, "limit_boost": 0,
        "top_n": 0, "top_n_pct": 0, "consensus_priority": False, "net_signal": False,
        "max_sector_pct": 40, "max_qdii_pct": 100, "rebalance": True,
        "fund_type_filter": "active", "sell_consensus": 0,
        "cooldown_profit_days": 10, "cooldown_loss_days": 30,
        "max_correlation": 0.6, "ml_signal": False, "ml_weight": 1.0,
        "ml_retrain_days": 30, "timing_filter": True, "block_overbought": True,
        "bear_market_no_buy": False, "min_score_bull": 0.0,
        "min_score_neutral": 0.0, "min_score_bear": 0.0,
        "downtrend_penalty": 0.5, "risk_free_rate": 0.025,
        "slippage_pct": 0.0, "ranking_half_life": 45,
        "pyramiding_enabled": False, "dynamic_stop_loss": True,
        "regime_specific": True,
        "take_profit_pct_bull": 120, "take_profit_pct_neutral": 80, "take_profit_pct_bear": 50,
        "stop_loss_pct_bull": -25, "stop_loss_pct_neutral": -30, "stop_loss_pct_bear": -20,
        "kelly_cap_bull": 0.40, "kelly_cap_neutral": 0.30, "kelly_cap_bear": 0.15,
        "pyramiding_enabled_bull": False, "pyramiding_enabled_neutral": False, "pyramiding_enabled_bear": True,
        "trailing_tp_activate_bull": 20, "trailing_tp_activate_neutral": 15, "trailing_tp_activate_bear": 10,
        "trailing_tp_drawdown_bull": 8, "trailing_tp_drawdown_neutral": 10, "trailing_tp_drawdown_bear": 6,
    },
}

# Y5 基础配置（sweep 变体基于此修改）
Y5_BASE = {
    "start_date": "2023-07-17", "end_date": "2026-07-17",
    "initial_cash": 10000, "monthly_injection": 0,
    "weights": {"quality": 25, "cost": 20, "manager": 20, "momentum": 15, "smart_money": 20},
}


def run_one(name, desc, config, base=None):
    """运行单个策略，返回结果。"""
    b = deepcopy(base or BASE)
    b.update(config)
    if config.get("monthly_injection", 0) > 0:
        b["initial_cash"] = 0
    try:
        t0 = time.time()
        r = run_backtest(b)
        elapsed = time.time() - t0
        # 计算年化
        days = 0
        from datetime import datetime
        try:
            d1 = datetime.strptime(b["start_date"], "%Y-%m-%d")
            d2 = datetime.strptime(b["end_date"], "%Y-%m-%d")
            days = (d2 - d1).days
        except Exception:
            days = 1095  # ~3 years
        years = max(days / 365.25, 0.1)
        ann = ((1 + r["total_return"] / 100) ** (1 / years) - 1) * 100
        result = {
            "name": name, "desc": desc,
            "return": r["total_return"], "annualized": ann,
            "dd": r["max_drawdown"], "trades": r["trade_count"],
            "holdings": r["final_holdings"],
            "sharpe": r["total_return"] / max(r["max_drawdown"], 1),
            "fees": r.get("total_fees", 0),
            "injected": r.get("monthly_injections", 0),
            "elapsed": elapsed,
        }
        print(f"  {name:40s} ret={r['total_return']:+8.2f}% ann={ann:+7.1f}% "
              f"dd={r['max_drawdown']:6.2f}% trades={r['trade_count']:4d} "
              f"sharpe={result['sharpe']:5.2f} ({elapsed:.0f}s)")
        return result
    except Exception as e:
        import traceback
        print(f"  {name:40s} FAILED: {e}")
        traceback.print_exc()
        return None


def main():
    parser = argparse.ArgumentParser(description="统一回测: 12基础 + Y5冠军 + 113变体")
    parser.add_argument("--base-only", action="store_true", help="只跑12种基础策略")
    parser.add_argument("--champion-only", action="store_true", help="只跑Y5冠军")
    parser.add_argument("--sweep-only", action="store_true", help="只跑113种变体")
    parser.add_argument("--start", type=str, default="2023-07-17", help="回测开始日期")
    parser.add_argument("--end", type=str, default="2026-07-17", help="回测结束日期")
    parser.add_argument("--output", type=str, default="backtest/results_revalidation/", help="输出目录")
    parser.add_argument("--mega", action="store_true", help="包含超大规模扫描(2187个)")
    parser.add_argument("--player", action="store_true", help="包含大佬精选策略(335个)")
    parser.add_argument("--chunk", type=int, default=0, help="当前分片ID (0-based)")
    parser.add_argument("--total", type=int, default=1, help="总分片数")
    args = parser.parse_args()

    # 更新基础配置的日期
    BASE["start_date"] = args.start
    BASE["end_date"] = args.end
    Y5_BASE["start_date"] = args.start
    Y5_BASE["end_date"] = args.end

    all_strategies = []

    if not args.sweep_only and not args.champion_only and not args.mega:
        all_strategies.extend([(s["name"], s["desc"], s["config"], BASE) for s in BASE_STRATEGIES])
    if not args.base_only and not args.sweep_only and not args.mega:
        all_strategies.append((Y5_CHAMPION["name"], Y5_CHAMPION["desc"], Y5_CHAMPION["config"], Y5_BASE))
    if not args.base_only and not args.champion_only and not args.mega:
        for key, cfg in SWEEP_CONFIGS.items():
            label = SWEEP_LABELS.get(key, key)
            base = deepcopy(Y5_BASE)
            base.update(Y5_CHAMPION["config"])
            all_strategies.append((f"SW_{key}", label, cfg, base))
    if args.mega or (not args.base_only and not args.champion_only and not args.sweep_only and not args.player):
        for s in MEGA_SWEEP:
            all_strategies.append((s["name"], s["desc"], s["config"], deepcopy(BASE)))
    if args.player or (not args.base_only and not args.champion_only and not args.sweep_only and not args.mega):
        for s in PLAYER_SWEEP:
            all_strategies.append((s["name"], s["desc"], s["config"], deepcopy(BASE)))

    # 分片: 只跑当前 chunk 的策略
    if args.total > 1:
        chunk_size = (len(all_strategies) + args.total - 1) // args.total
        start_idx = args.chunk * chunk_size
        end_idx = min(start_idx + chunk_size, len(all_strategies))
        all_strategies = all_strategies[start_idx:end_idx]
        print(f"分片 {args.chunk}/{args.total}: 策略 [{start_idx}:{end_idx}] = {len(all_strategies)} 个")

    total = len(all_strategies)
    print(f"\n{'='*70}")
    print(f"统一回测: {total} 个策略 (分片 {args.chunk}/{args.total})")
    print(f"期间: {args.start} ~ {args.end}")
    print(f"{'='*70}\n")

    results = []
    t_start = time.time()

    for i, (name, desc, config, base) in enumerate(all_strategies):
        if (i + 1) % 10 == 0 or i == 0:
            print(f"\n--- [{i+1}/{total}] ---")
        r = run_one(name, desc, config, base)
        if r:
            results.append(r)

    elapsed_total = time.time() - t_start

    # 排序输出（按夏普降序）
    results.sort(key=lambda x: x["sharpe"], reverse=True)

    print(f"\n{'='*70}")
    print(f"回测完成: {len(results)}/{total} 成功, 耗时 {elapsed_total:.0f}s")
    print(f"{'='*70}")
    print(f"{'策略':42s} {'收益':>8s} {'年化':>8s} {'回撤':>8s} {'夏普':>6s} {'交易':>5s}")
    print(f"{'-'*70}")
    for r in results:
        print(f"{r['name']:42s} {r['return']:>+7.2f}% {r['annualized']:>+7.1f}% "
              f"{r['dd']:>7.2f}% {r['sharpe']:>5.2f} {r['trades']:>4d}")

    # 保存 (分片模式下用 chunk 后缀)
    out_dir = PROJECT / args.output
    out_dir.mkdir(parents=True, exist_ok=True)
    suffix = f"_chunk{args.chunk}" if args.total > 1 else ""
    out_file = out_dir / f"all_strategies{suffix}.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump({
            "strategies": results,
            "period": f"{args.start} ~ {args.end}",
            "total": total,
            "succeeded": len(results),
            "elapsed_sec": elapsed_total,
        }, f, ensure_ascii=False, indent=2)
    print(f"\n保存到 {out_file}")

    # 也保存 top20
    top20_file = out_dir / "top20.json"
    with open(top20_file, "w", encoding="utf-8") as f:
        json.dump({
            "top20": results[:20],
            "period": f"{args.start} ~ {args.end}",
        }, f, ensure_ascii=False, indent=2)
    print(f"Top20 保存到 {top20_file}")


if __name__ == "__main__":
    main()
