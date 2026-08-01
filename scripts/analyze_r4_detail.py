import json, sys
with open("v9-results/strict_oos_r4_eval.json") as f:
    data = json.load(f)

by_name = sorted(data["summary"].items(), key=lambda x: -x[1]["avg_return"])

print("=" * 100)
print("R4 Per-Window Detail — All 5 candidates")
print("=" * 100)

for name, s in by_name:
    print(f"\n### {name} — avg_ret={s['avg_return']:.3f}%, bench={s['avg_benchmark']:.3f}%, beats={s['beats_count']}/{s['total_windows']}")
    for w in sorted(s["details"], key=lambda x: x["wi"]):
        marker = "OK" if w["return"] > w["benchmark"] else "XX"
        print(f"  W{w['wi']:2d}  {w['period'][:7]}  ret={w['return']:+7.2f}%  bench={w['benchmark']:+6.2f}%  {marker}  trades={w['trades']:2d}  fees={w['fees']:5.1f}")

print("\n\n" + "=" * 100)
print("WINDOW-LEVEL COMPARISON TABLE")
print("=" * 100)
all_details = {name: {w["wi"]: w for w in s["details"]} for name, s in by_name}
windows = sorted(set(w["wi"] for s in data["summary"].values() for w in s["details"]))

header = f"{'Window':<12s}"
for name, _ in by_name:
    header += f" {name[:15]:>15s}"
header += f" {'CSI300':>10s}"
print(header)

for wi in windows:
    first_name = by_name[0][0]
    period = all_details[first_name][wi]["period"][:7]
    bench = all_details[first_name][wi]["benchmark"]
    row = f"W{wi:2d} {period:<8s}"
    for name, _ in by_name:
        ret = all_details[name][wi]["return"]
        row += f" {ret:+14.2f}%"
    row += f" {bench:+9.2f}%"
    print(row)
