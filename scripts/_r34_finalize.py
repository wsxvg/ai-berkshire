"""Finalize R34: clean up temp artifacts, update handoff, prepare eval commit."""
import json, os, shutil
from collections import defaultdict

# --- Load eval ---
with open("v9-results/strict_oos_taa_eval.json") as f:
    eval_data = json.load(f)

# --- Compute richer stats ---
summary_lines = []
for name in ["C_EQW13", "C_TAA_K4", "C_TAA_K3", "C_TAA_K5"]:
    d = eval_data[name]
    per = d["per_window"]
    
    # Buckets: bull vs bear (benchmark return sign)
    bull_returns = [p["return"] for p in per if p["benchmark"] > 0]
    bear_returns  = [p["return"] for p in per if p["benchmark"] <= 0]
    bull_bench   = [p["benchmark"] for p in per if p["benchmark"] > 0]
    bear_bench   = [p["benchmark"] for p in per if p["benchmark"] <= 0]
    
    # Non-overlapping compounded return (use windows 0, 4, 9, 14, 19, ... as a rough proxy)
    non_overlapping = [per[i] for i in range(0, len(per), 5)]
    compounded_start = 1.0
    for p in non_overlapping:
        compounded_start *= (1 + p["return"] / 100)
    compounded_bench_start = 1.0
    for p in non_overlapping:
        compounded_bench_start *= (1 + p["benchmark"] / 100)
    
    summary_lines.append(f"{name}:")
    summary_lines.append(f"  avg_return={d['avg_return']:+.3f}%  benchmark={d['avg_benchmark']:+.3f}%")
    summary_lines.append(f"  beats={d['beats']}/{d['count']} ({d['beats']/(d['count'] or 1)*100:.1f}%)  mdd_avg={d['avg_mdd']:.2f}%  mdd_peak={d['peak_mdd']:.2f}%")
    summary_lines.append(f"  BULL windows (n={len(bull_returns)}): strat avg {sum(bull_returns)/max(len(bull_returns),1):+.2f}%  bench avg {sum(bull_bench)/max(len(bull_bench),1):+.2f}%")
    summary_lines.append(f"  BEAR windows (n={len(bear_returns)}): strat avg {sum(bear_returns)/max(len(bear_returns),1):+.2f}%  bench avg {sum(bear_bench)/max(len(bear_bench),1):+.2f}%")
    summary_lines.append(f"  compounded (non-overlapping, n={len(non_overlapping)} windows): strat {(compounded_start-1)*100:+.1f}%  bench {(compounded_bench_start-1)*100:+.1f}%")
    summary_lines.append("")

print("\n".join(summary_lines))

# --- Cleanup temp artifacts ---
shutil.rmtree("temp_r34_artifacts", ignore_errors=True)
for f in os.listdir("."):
    if f.startswith("strict_test_taa_") and f.endswith(".json"):
        os.remove(f)
print("Cleaned up temp files.")
