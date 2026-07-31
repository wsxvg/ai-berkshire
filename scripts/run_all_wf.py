"""Run all 9 walk-forward windows sequentially."""
import subprocess, sys, json, time

WINDOWS = list(range(9))

for wi in WINDOWS:
    print(f"\n{'='*60}")
    print(f"=== Running Window {wi} ===")
    print(f"{'='*60}")
    sys.stdout.flush()
    
    start = time.time()
    result = subprocess.run(
        [sys.executable, 'scripts/expert_wf_runner.py', str(wi)],
        capture_output=True, text=True, timeout=1200
    )
    
    elapsed = time.time() - start
    print(f"Window {wi} completed in {elapsed:.0f}s")
    print(f"STDOUT:\n{result.stdout[-500:]}")
    if result.stderr:
        print(f"STDERR:\n{result.stderr[-300:]}")
    sys.stdout.flush()

# Aggregate results
print("\n" + "="*60)
print("=== COMBINED RESULTS ===")
print("="*60)

import glob
all_results = []
for wi in sorted(glob.glob('expert_wf_window*.json')):
    with open(wi) as f:
        r = json.load(f)
    all_results.append(r)

# Print summary table
labels = ['EXP_3P', 'EXP_2P', 'EXP_MOM', 'V8_ORIGINAL']
print(f"\n{'Window':>6} {'Test Period':>24} " + " ".join(f"{l:>12}" for l in labels))
print("-" * (30 + 12 * len(labels)))

for r in all_results:
    wi = r['window']
    period = r['test_period']
    rets = [r['test_results'].get(l, {}).get('return', 0) for l in labels]
    ret_str = " ".join(f"{v:>+11.2f}%" for v in rets)
    print(f"{wi:>6} {period:>24} {ret_str}")

# Average
if all_results:
    print("-" * (30 + 12 * len(labels)))
    avg_ret = {}
    for l in labels:
        vals = [r['test_results'].get(l, {}).get('return', 0) for r in all_results]
        avg_ret[l] = sum(vals) / len(vals)
    print(f"{'AVG':>6} {'':>24} " + " ".join(f"{avg_ret[l]:>+11.2f}%" for l in labels))
    
    # Min/Max
    for stat_label, stat_func in [('MIN', min), ('MAX', max)]:
        stats = {}
        for l in labels:
            vals = [r['test_results'].get(l, {}).get('return', 0) for r in all_results]
            stats[l] = stat_func(vals)
        print(f"{stat_label:>6} {'':>24} " + " ".join(f"{stats[l]:>+11.2f}%" for l in labels))

print("\nDone!")
