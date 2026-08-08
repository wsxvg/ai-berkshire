#!/usr/bin/env python3
"""Local parallel runner for R10 experiments using all CPU cores."""
import sys, os, json, time, subprocess
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime

sys.path.insert(0, '.')
from scripts.exp_strict_oos import ROUND, CANDIDATES, TRAIN_WINDOWS, TEST_WINDOWS, ALL_WINDOWS, BASE_CFG, window_range
from backtest.engine.backtest import run_backtest
import copy


def run_one(args):
    ci, wi_global, phase = args
    train_end, test_end = window_range(wi_global)
    cfg = copy.deepcopy(BASE_CFG)
    cfg_override = CANDIDATES[ci][1]
    cfg.update(cfg_override)
    cfg['start_date'] = train_end
    cfg['end_date'] = test_end
    t0 = time.time()
    res = run_backtest(cfg, clear_cache=True)
    elapsed = time.time() - t0
    r = {
        "phase": phase,
        "round": ROUND,
        "candidate": CANDIDATES[ci][0],
        "ci": ci,
        "wi": wi_global - len(TRAIN_WINDOWS) if phase == "test" else wi_global,
        "period": f"{train_end}~{test_end}",
        "return": res.get("total_return", 0),
        "trades": res.get("trade_count", 0),
        "fees": res.get("total_fees", 0),
        "max_dd": res.get("max_drawdown", 0),
        "benchmark": res.get("benchmark_return", 0),
        "win_rate": res.get("win_rate", 0),
        "avg_hold_days": res.get("avg_hold_days", 0),
        "elapsed": elapsed,
    }
    if phase == "train":
        fname = f"strict_ci{ci}_wi{wi_global}.json"
    else:
        fname = f"strict_test_ci{ci}_wi{wi_global - len(TRAIN_WINDOWS)}.json"
    with open(fname, "w") as f:
        json.dump(r, f, ensure_ascii=False)
    return r


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "test"
    max_workers = int(sys.argv[2]) if len(sys.argv) > 2 else 4
    
    if mode == "train":
        tasks = [(ci, wi, "train") for ci in range(len(CANDIDATES)) for wi in range(len(TRAIN_WINDOWS))]
    elif mode == "test":
        tasks = [(ci, len(TRAIN_WINDOWS) + wi, "test") for ci in range(len(CANDIDATES)) for wi in range(len(TEST_WINDOWS))]
    elif mode == "all":
        tasks = [(ci, wi, "train") for ci in range(len(CANDIDATES)) for wi in range(len(TRAIN_WINDOWS))]
        tasks += [(ci, len(TRAIN_WINDOWS) + wi, "test") for ci in range(len(CANDIDATES)) for wi in range(len(TEST_WINDOWS))]
    else:
        print(f"Unknown mode: {mode}")
        sys.exit(1)
    
    total = len(tasks)
    print(f"R{ROUND} {mode}: {total} tasks with {max_workers} workers")
    t_start = time.time()
    
    results = []
    with ProcessPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(run_one, t): t for t in tasks}
        for i, fut in enumerate(as_completed(futures), 1):
            try:
                r = fut.result()
                results.append(r)
                if i % 5 == 0 or i == total:
                    elapsed = time.time() - t_start
                    eta = elapsed / i * (total - i)
                    print(f"  [{i}/{total}] {r['candidate']} {r['period']} = {r['return']:.2f}% ({r['elapsed']:.0f}s) ETA={eta/60:.1f}min")
            except Exception as e:
                t = futures[fut]
                print(f"  FAILED ci={t[0]} wi={t[1]}: {e}")
    
    total_time = time.time() - t_start
    print(f"\nDone in {total_time/60:.1f} minutes")
    
    # Aggregate
    from collections import defaultdict
    by_cand = defaultdict(list)
    for r in results:
        by_cand[r["candidate"]].append(r)
    
    print(f"\nR{ROUND} Results (sorted by avg return):")
    for name, items in sorted(by_cand.items(), key=lambda x: -sum(i["return"] for i in x[1])/len(x[1])):
        avg = sum(i["return"] for i in items) / len(items)
        avg_b = sum(i["benchmark"] for i in items) / len(items)
        beats = sum(1 for i in items if i["return"] > i["benchmark"])
        print(f"  {name}: avg={avg:.3f}% bench={avg_b:.3f}% beats={beats}/{len(items)}")


if __name__ == "__main__":
    main()
