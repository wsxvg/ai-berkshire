"""Aggregate expert WF results from downloaded artifacts."""
import json, glob

results = []
for f in sorted(glob.glob('artifacts/expert-wf-*/expert_wf_window*.json')):
    with open(f) as fh:
        r = json.load(fh)
    results.append(r)
    print(f"Loaded {f}: window {r['window']}")

labels = ['EXP_3P', 'EXP_2P', 'EXP_MOM', 'V8_ORIGINAL']

print("\n" + "="*80)
print("EXPERT WALK-FORWARD RESULTS")
print("="*80)
print(f"\n{'Window':>6} {'Test Period':>24} " + " ".join(f"{l:>12}" for l in labels))
print("-" * (30 + 12 * len(labels)))

for r in sorted(results, key=lambda x: x['window']):
    wi = r['window']
    period = r['test_period']
    rets = [r['test_results'].get(l, {}).get('return', 0) for l in labels]
    ret_str = " ".join(f"{v:>+11.2f}%" for v in rets)
    print(f"{wi:>6} {period:>24} {ret_str}")

# Summary stats
print("-" * (30 + 12 * len(labels)))
avgs = {}
for l in labels:
    vals = [r['test_results'].get(l, {}).get('return', 0) for r in results]
    avgs[l] = sum(vals) / len(vals) if vals else 0

print(f"{'AVG':>6} {'':>24} " + " ".join(f"{avgs[l]:>+11.2f}%" for l in labels))

print("\nWin Rate (% windows positive):")
for l in labels:
    vals = [r['test_results'].get(l, {}).get('return', 0) for r in results]
    pos = sum(1 for v in vals if v > 0)
    neg = sum(1 for v in vals if v < 0)
    print(f"  {l:12s}: +{pos}/{len(vals)}  -{neg}/{len(vals)}  win_rate={pos/len(vals)*100:.0f}%")

# Trade stats
print("\nTrade Stats:")
for l in labels:
    trades = [r['test_results'].get(l, {}).get('trades', 0) for r in results]
    fees = [r['test_results'].get(l, {}).get('fees', 0) for r in results]
    print(f"  {l:12s}: Total trades={sum(trades):4d}, Total fees={sum(fees):.0f}, Avg trades/window={sum(trades)/len(trades):.1f}")

# Drawdown
print("\nMax Drawdown (worst window):")
for l in labels:
    dds = [r['test_results'].get(l, {}).get('drawdown', 0) for r in results]
    print(f"  {l:12s}: worst={max(dds):.2f}%, avg={sum(dds)/len(dds):.2f}%")

print("\n" + "="*80)
