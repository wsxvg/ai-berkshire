"""Diagnose EXP_MOM bottleneck: where is the alpha gap?

Theoretical: Expert consensus 7-day alpha = +1.4% per trade
Current realized: +0.33% per quarter across all trades (~2.4 trades/qtr)
Gap: ~10x

Hypotheses to test:
1. min_score filters out too many good trades
2. Kelly cap is too conservative (deploying too little)
3. Take profit / rebalancing too aggressive
4. Consensus window miss-timed
5. Better expert selection (not all experts are equal)
"""
import json
import glob

# Load all windows
all_results = []
for f in sorted(glob.glob('artifacts/expert-wf-*/expert_wf_window*.json')):
    with open(f) as fh:
        r = json.load(fh)
    all_results.append(r)

# EXP_MOM stats
mom_trades = []
for r in all_results:
    tr = r['test_results'].get('EXP_MOM', {})
    if tr:
        mom_trades.append(tr)

print("EXP_MOM Trade Summary Across 8 Windows:")
print(f"  Total trades: {sum(t['trades'] for t in mom_trades)}")
print(f"  Total fees: {sum(t['fees'] for t in mom_trades):.0f}")
print(f"  Per-window avg trades: {sum(t['trades'] for t in mom_trades)/len(mom_trades):.1f}")
print(f"  Per-window avg fees: {sum(t['fees'] for t in mom_trades)/len(mom_trades):.1f}")
print(f"  Per-window avg return: {sum(t['return'] for t in mom_trades)/len(mom_trades):.3f}%")
print()

# Show bad windows
print("Window-by-window EXP_MOM returns:")
for r in all_results:
    wi = r['window']
    ret = r['test_results'].get('EXP_MOM', {}).get('return', 0)
    trades = r['test_results'].get('EXP_MOM', {}).get('trades', 0)
    print(f"  W{wi}: {ret:+.2f}% ({trades} trades)")

print()
print("Diagnosis: We need to understand WHY only 7 trades/quarter.")
print("Is it signal scarcity or over-filtering?")
