#!/usr/bin/env python3
"""网格搜索回测 — 探索最优参数组合，输出绩效排名。

搜索维度（2^7 = 128 组）:
  用户权重 / 止损 / 止盈 / 移动止盈回撤 / 冷却 / 持仓数 / 择时
  固定: min_score=2.5, bear_market_no_buy=True, max_correlation=0.85

运行: python scripts/grid_search.py          # 全量 128 组 (~1.5小时)
     python scripts/grid_search.py --quick  # 快速 16 组 (~10分钟)
     python scripts/grid_search.py --resume # 断点续跑

金融方法已涵盖: 申购费/赎回费/T+N确认/滑点/RSI/布林带/MACD/凯利仓位/ATR/相关性过滤/冷却期
"""

import argparse
import hashlib
import json
import sys
import time
from datetime import datetime
from itertools import product
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))

CHECKPOINT_FILE = PROJECT / "data" / "grid_checkpoint.json"


def build_grid(quick=False):
    """构建参数网格。去掉无意义组合 (-5止损/10止盈/3天冷却)"""
    if quick:
        return {
            "user_weight_scenario": ["baseline", "extreme"],
            "min_score": [2.8, 3.5],
            "stop_loss_pct": [-10, -15],
            "take_profit_pct": [15, 25],
            "min_consensus": [3, 5],
            "pyramiding_enabled": [False, True],
            "timing_filter": [False, True],
        }  # 2^7 = 128

    return {
        "user_weight_scenario": ["baseline", "extreme"],    # ×2: 默认权重 vs 激进权重
        "min_score": [2.8, 3.5],                             # ×2: 信号门槛
        "stop_loss_pct": [-8, -12],                         # ×2: 止损线
        "take_profit_pct": [15, 20],                         # ×2: 止盈线
        "min_consensus": [3, 5],                             # ×2: 最少多少大佬同时买入
        "pyramiding_enabled": [False, True],                 # ×2: 金字塔加仓开关
        "timing_filter": [False, True],                      # ×2: RSI择时
        # 固定: max_holdings=5, cooldown_days=5, circuit_breaker=15%, corr_sell=0.95
        # 固定: use_weighted_consensus=True, dynamic_ranking=True, trailing_tp=10
    }
    # 2^7 = 128 组


def _params_hash(params):
    """参数组合的稳定哈希"""
    raw = json.dumps(params, sort_keys=True, default=str)
    return hashlib.md5(raw.encode()).hexdigest()[:8]


def load_checkpoint():
    """加载已完成的 checkpoint → {hash: result}"""
    if CHECKPOINT_FILE.exists():
        try:
            data = json.loads(CHECKPOINT_FILE.read_text("utf-8"))
            return {e["hash"]: e for e in data.get("results", [])}
        except Exception:
            return {}
    return {}


def save_checkpoint(grid, all_results, base_annual):
    """全量保存 checkpoint（每次覆盖写，保证数据一致性）"""
    CHECKPOINT_FILE.parent.mkdir(parents=True, exist_ok=True)
    entries = []
    for r in all_results:
        entry = dict(r)
        entry["hash"] = _params_hash({k: entry[k] for k in grid.keys() if k in entry})
        entries.append(entry)
    CHECKPOINT_FILE.write_text(json.dumps({
        "timestamp": datetime.now().isoformat(),
        "total": len(all_results),
        "grid": {k: list(v) for k, v in grid.items()},
        "base_annual": base_annual,
        "results": entries,
    }, ensure_ascii=False, indent=2), encoding="utf-8")


def build_config(template, combo_params):
    """从模板 + 参数组合构建回测配置"""
    import copy
    cfg = copy.deepcopy(template["config"])

    # 自动从交易数据取最早日期
    import json as _json
    # 对齐基准：从 2024-03-11 起步，跳过 2023 年冷启动
    cfg["start_date"] = "2024-03-11"
    cfg["end_date"] = "2026-07-14"
    # 固定值（不在网格搜索中）
    cfg["use_weighted_consensus"] = True   # 大佬权重影响实际买数
    cfg["cooldown_days"] = 5               # 冷却期固定
    cfg["max_holdings"] = 5                # 持仓数固定
    cfg["trailing_tp_drawdown"] = 10       # 移动止盈
    cfg["circuit_breaker_pct"] = 15        # 组合回撤 15% 熔断
    cfg["circuit_breaker_resume"] = 8      # 回撤恢复至 8%
    cfg["correlation_sell_threshold"] = 0.95  # 相关性 >0.95 卖弱势方

    for key, value in combo_params.items():
        if key == "user_weight_scenario":
            cfg["weight_scenario"] = value
            w = 40 if value == "extreme" else 24.72
            cfg["weights"] = dict(cfg.get("weights", {}))
            cfg["weights"]["smart_money"] = w
        else:
            cfg[key] = value

    return cfg


def run_single_backtest(config):
    """运行单次回测，返回绩效指标。stderr 静音。"""
    import os as _os
    _old_stderr = _os.dup(2)
    _devnull = _os.open(_os.devnull, _os.O_WRONLY)
    _os.dup2(_devnull, 2)
    _os.close(_devnull)
    try:
        from backtest.engine.backtest import run_backtest
        import tools.jd_finance_api as api
        scenario = config.get("weight_scenario", "baseline")
        w = api._load_user_weights(scenario)
        api.USER_WEIGHT = w

        result = run_backtest(config)
        if not result:
            return {"error": "null result"}

        annual = result.get("annualized_return", 0)
        sharpe = result.get("sharpe", 0)
        dd = result.get("max_drawdown", 0)
        total = result.get("total_return", 0)
        bench = result.get("benchmark_return", 0)

        return {
            "annual_return": round(annual, 2),
            "sharpe": round(sharpe, 4),
            "max_drawdown": round(dd, 2),
            "total_return": round(total, 2),
            "excess": round(total - bench, 2),
            "benchmark": round(bench, 2),
            "trades": result.get("trade_count", 0),
            "win_rate": round(result.get("win_rate", 0), 2),
        }
    except Exception as e:
        return {"error": str(e)[:80]}
    finally:
        _os.dup2(_old_stderr, 2)
        _os.close(_old_stderr)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--quick", action="store_true", help="快速模式 16 组")
    parser.add_argument("--resume", action="store_true", help="断点续跑")
    args = parser.parse_args()

    template = json.loads((PROJECT / "data" / "evolution" / "best_config.json").read_text("utf-8"))
    baseline = template["config"]
    base_annual = 24.1

    grid = build_grid(quick=args.quick)
    keys = list(grid.keys())
    all_combos = list(product(*[grid[k] for k in keys]))

    # ── 断点续跑：跳过已完成组 ──
    completed = load_checkpoint() if args.resume else {}
    pending = []
    skipped = 0
    for combo in all_combos:
        params = dict(zip(keys, combo))
        h = _params_hash(params)
        if h in completed:
            skipped += 1
        else:
            pending.append((h, params))

    total_new = len(pending)
    total_all = len(all_combos)

    if args.resume and skipped > 0:
        print(f"断点续跑: 已完成 {skipped}, 剩余 {total_new}/{total_all}")
    else:
        print(f"参数网格: {total_all} 组")
    print(f"维度: {' × '.join(f'{k}({len(grid[k])})' for k in keys)}")
    print(f"基底 夏普={baseline.get('sharpe',1.52)} 年化={base_annual}%")
    print(f"开始: {datetime.now().strftime('%H:%M:%S')}")

    # ── 加载已有结果 ──
    results = list(completed.values()) if args.resume else []
    t_start = time.time()

    for idx, (phash, params) in enumerate(pending):
        cfg = build_config(template, params)

        t0 = time.time()
        r = run_single_backtest(cfg)
        dt = time.time() - t0

        entry = {**params, "hash": phash}
        if r and "error" not in r:
            entry.update(r)
        else:
            entry["error"] = r.get("error", "?") if isinstance(r, dict) else str(r)

        results.append(entry)

        # 每完成一组就存盘
        save_checkpoint(grid, results, base_annual)

        ann = r.get("annual_return", 0) if isinstance(r, dict) else 0
        sp = r.get("sharpe", 0) if isinstance(r, dict) else 0
        done = len(results)
        pct = done / total_all * 100
        elapsed_sec = time.time() - t_start
        if done > 1:
            avg_sec = elapsed_sec / done
        else:
            avg_sec = elapsed_sec / (idx + 1) if idx > 0 else elapsed_sec
        eta_min = avg_sec * (total_all - done) / 60
        round_min = dt / 60

        star = "★" if ann > base_annual else " "
        tp_val = params.get("take_profit_pct", "?")
        print(f"  [{done:3d}/{total_all}] {ann:+6.1f}% S={sp:.3f} {star} | "
              f"{params.get('user_weight_scenario','?'):>13} "
              f"ms={params.get('min_score','?'):>4} "
              f"sl={params.get('stop_loss_pct','?'):>4} "
              f"tp={tp_val:>3} "
              f"mc={params.get('min_consensus','?'):>3} "
              f"py={'ON' if params.get('pyramiding_enabled') else 'OFF':>5} "
              f"RSI={str(params.get('timing_filter','?')):>5} "
              f"| {round_min:.1f}m/轮 ETA{eta_min:.0f}m")

    # ── 排名 ──
    elapsed = (time.time() - t_start) / 60
    valid = [r for r in results if "error" not in r]
    valid.sort(key=lambda x: x.get("sharpe", 0), reverse=True)

    print(f"\n{'='*80}")
    print(f"总耗时: {elapsed:.0f}min | 有效: {len(valid)}/{len(results)}")
    print(f"\nTOP 15 (按夏普排序, ★=超基准年化{base_annual}%):")
    header = (f"{'#':<4} {'年化':>8} {'夏普':>7} {'回撤':>7} {'超额':>7} {'交易':>5} "
              f"{'场景':>13} {'sl':>5} {'tp':>4} {'cd':>4} {'hold':>5} {'RSI':>6}")
    print(header)
    print("-" * len(header))

    for i, r in enumerate(valid[:15]):
        star = "★" if r["annual_return"] > base_annual else " "
        print(f"{i+1:<4} {r['annual_return']:>+7.1f}% {r['sharpe']:>7.4f} "
              f"{r['max_drawdown']:>+6.1f}% {r['excess']:>+6.1f}% {r.get('trades','?'):>5} "
              f"{r.get('user_weight_scenario','?'):>13} "
              f"{r.get('stop_loss_pct','?'):>5} "
              f"{r.get('take_profit_pct','?'):>4} "
              f"{r.get('trailing_tp_drawdown','?'):>4} "
              f"{r.get('cooldown_days','?'):>4} "
              f"{r.get('max_holdings','?'):>5} "
              f"{str(r.get('timing_filter','?')):>6} "
              f"{star}")

    # ── 维度分析 ──
    print(f"\n权重场景对比:")
    for sc in sorted(set(r.get("user_weight_scenario", "?") for r in valid)):
        sr = [r for r in valid if r.get("user_weight_scenario") == sc]
        if sr:
            avg = sum(r["annual_return"] for r in sr) / len(sr)
            avg_s = sum(r["sharpe"] for r in sr) / len(sr)
            beats = sum(1 for r in sr if r["annual_return"] > base_annual)
            print(f"  {sc:14s} avg={avg:+.1f}% sharpe={avg_s:.3f} 超基准:{beats}/{len(sr)}")

    print(f"\n择时过滤器对比:")
    for tf in [True, False]:
        sr = [r for r in valid if r.get("timing_filter") == tf]
        if sr:
            avg = sum(r["annual_return"] for r in sr) / len(sr)
            print(f"  timing={tf}: avg={avg:+.1f}% ({len(sr)}组)")

    print(f"\n止损线对比:")
    for sl in sorted(set(r.get("stop_loss_pct", 0) for r in valid)):
        sr = [r for r in valid if r.get("stop_loss_pct") == sl]
        if sr:
            avg = sum(r["annual_return"] for r in sr) / len(sr)
            print(f"  sl={sl:>4}%: avg={avg:+.1f}% ({len(sr)}组)")

    print(f"\n止盈线对比:")
    for tp in sorted(set(r.get("take_profit_pct", 0) for r in valid)):
        sr = [r for r in valid if r.get("take_profit_pct") == tp]
        if sr:
            avg = sum(r["annual_return"] for r in sr) / len(sr)
            print(f"  tp={tp:>4}%: avg={avg:+.1f}% ({len(sr)}组)")

    # ── 保存最终结果 ──
    save_checkpoint(grid, results, base_annual)
    print(f"\n结果: {CHECKPOINT_FILE}")
    print(f"续跑: python scripts/grid_search.py --resume")


if __name__ == "__main__":
    main()
