#!/usr/bin/env python3
"""聚焦策略扫描运行器——配合 focused_sweep_configs.json 使用。

用法:
  python backtest/run_focused_sweep.py                          # 跑全部174个策略
  python backtest/run_focused_sweep.py --chunk 0 --total 20     # 分片模式
"""
import sys, json, time, argparse
from pathlib import Path
from copy import deepcopy

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))

from backtest.engine.backtest import run_backtest

# 加载策略配置
configs_path = Path(__file__).resolve().parent / "focused_sweep_configs.json"
with open(configs_path, encoding="utf-8") as f:
    FOCUSED_CONFIGS = json.loads(f.read())

BASE = {
    "start_date": "2023-07-17",
    "end_date": "2026-07-24",
    "initial_cash": 10000,
    "monthly_injection": 0,
    "weights": {"quality": 25, "cost": 20, "manager": 20, "momentum": 15, "smart_money": 20},
}


def run_one(name, desc, config, base=None, clear_cache=True):
    b = deepcopy(base or BASE)
    b.update(config)
    if config.get("monthly_injection", 0) > 0:
        b["initial_cash"] = 0
    try:
        t0 = time.time()
        r = run_backtest(b, clear_cache=clear_cache)
        elapsed = time.time() - t0
        from datetime import datetime
        try:
            d1 = datetime.strptime(b["start_date"], "%Y-%m-%d")
            d2 = datetime.strptime(b["end_date"], "%Y-%m-%d")
            days = (d2 - d1).days
        except Exception:
            days = 1095
        years = max(days / 365.25, 0.1)
        ann = ((1 + r["total_return"] / 100) ** (1 / years) - 1) * 100
        result = {
            "name": name, "desc": desc,
            "return": r["total_return"], "annualized": ann,
            "dd": r["max_drawdown"], "trades": r["trade_count"],
            "holdings": r.get("final_holdings", 0),
            "sharpe": r["total_return"] / max(r["max_drawdown"], 1),
            "fees": r.get("total_fees", 0),
            "elapsed": elapsed,
            "config": b,
        }
        print(f"  {name:42s} ret={r['total_return']:+8.2f}% ann={ann:+7.1f}% "
              f"dd={r['max_drawdown']:6.2f}% trades={r['trade_count']:4d} "
              f"sharpe={result['sharpe']:5.2f} ({elapsed:.0f}s)", flush=True)
        return result
    except Exception as e:
        import traceback
        print(f"  {name:42s} FAILED: {e}", flush=True)
        traceback.print_exc()
        return None


def main():
    parser = argparse.ArgumentParser(description="聚焦策略扫描")
    parser.add_argument("--start", type=str, default="2023-07-17")
    parser.add_argument("--end", type=str, default="2026-07-24")
    parser.add_argument("--output", type=str, default="backtest/results_focused/")
    parser.add_argument("--chunk", type=int, default=0)
    parser.add_argument("--total", type=int, default=1)
    args = parser.parse_args()

    BASE["start_date"] = args.start
    BASE["end_date"] = args.end

    # 分片
    all_strategies = FOCUSED_CONFIGS
    chunk_size = len(all_strategies) // args.total + 1
    start_idx = args.chunk * chunk_size
    end_idx = min(start_idx + chunk_size, len(all_strategies))
    my_chunk = all_strategies[start_idx:end_idx]

    print(f"=== Focused Sweep: chunk {args.chunk}/{args.total} ===")
    print(f"Strategies: {len(my_chunk)} (index {start_idx}-{end_idx-1} of {len(all_strategies)})")
    print(f"Period: {args.start} ~ {args.end}")
    print(flush=True)

    results = []
    for i, s in enumerate(my_chunk):
        print(f"[{i+1}/{len(my_chunk)}] ", end="", flush=True)
        clear_cache = (i == 0)  # 第一个清缓存，后续复用
        r = run_one(s["name"], s["desc"], s["config"], BASE, clear_cache=clear_cache)
        if r:
            results.append(r)

    # 保存
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"chunk_{args.chunk}.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump({"strategies": results, "chunk": args.chunk, "total": len(my_chunk)},
                  f, ensure_ascii=False, indent=2)

    # 汇总
    print(f"\n=== Chunk {args.chunk} Summary ===")
    if results:
        results.sort(key=lambda x: x["sharpe"], reverse=True)
        print(f"{'Strategy':42s} {'Return':>8s} {'Annual':>8s} {'MaxDD':>8s} {'Sharpe':>6s} {'Trades':>6s}")
        for r in results[:10]:
            print(f"{r['name']:42s} {r['return']:>+7.2f}% {r['annualized']:>+7.1f}% "
                  f"{r['dd']:>7.2f}% {r['sharpe']:>5.2f} {r['trades']:>5d}")
    print(f"\nSaved to {out_file}")


if __name__ == "__main__":
    main()
