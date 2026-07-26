#!/usr/bin/env python3
"""Auto-evolution: monitor V6+ actions, fetch results, design next version, push & trigger, repeat until convergence."""
import subprocess, json, time, os, sys, copy, glob, re, tempfile
from pathlib import Path

TOKEN = os.environ.get("GH_TOKEN", "")
REPO = "wsxvg/ai-berkshire"
REPO_DIR = r"c:\fund"
GH_API = f"https://api.github.com/repos/{REPO}"
POLL_INTERVAL = 120  # 2 minutes
MAX_VERSIONS = 8     # V6 -> V7 -> ... -> V13 max
IMPROVEMENT_THRESHOLD = 2.0  # min return improvement % to continue
LOG_FILE = os.path.join(REPO_DIR, "auto_evolve.log")

# Track best across all versions
champion_history = []  # [(version, name, return, sharpe, dd, config)]

def log(msg):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")

def curl_api(url, method="GET", data=None):
    """Call GitHub API using curl.exe (schannel SSL works through firewall)."""
    cmd = ["curl.exe", "--connect-timeout", "30", "--max-time", "120",
           "--insecure", "-L", "-s",
           "-H", f"Authorization: token {TOKEN}",
           "-H", "Accept: application/vnd.github+json"]
    if method == "POST" and data:
        cmd += ["-X", "POST"]
        tf = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        json.dump(data, tf)
        tf.close()
        cmd += ["--data", f"@{tf.name}"]
    cmd.append(url)
    r = subprocess.run(cmd, capture_output=True)
    out = r.stdout.decode("utf-8", errors="replace")
    try:
        return json.loads(out) if out.strip() else {}
    except:
        log(f"  API parse error: {out[:200]}")
        return {}

def git(args):
    cmd = ["git"] + args
    r = subprocess.run(cmd, capture_output=True, cwd=REPO_DIR)
    out = (r.stdout + r.stderr).decode("utf-8", errors="replace")
    return r.returncode, out

def check_workflows_done(version_prefix):
    """Check if all runs for given version (e.g. 'v6') are completed."""
    data = curl_api(f"{GH_API}/actions/runs?per_page=20")
    runs = data.get("workflow_runs", [])
    if not runs:
        log("  No runs found, waiting...")
        return False, []

    # Filter runs matching our version
    matching = [r for r in runs if r.get("name", "").lower().startswith(version_prefix.lower())]
    if not matching:
        log(f"  No runs matching '{version_prefix}', checking all recent...")
        for r in runs[:5]:
            log(f"    {r['name']} status={r['status']} conclusion={r.get('conclusion','?')}")
        return False, []

    all_done = True
    statuses = []
    for r in matching:
        status = r["status"]
        conclusion = r.get("conclusion", "?")
        statuses.append(f"{r['name']}:{status}/{conclusion}")
        if status != "completed":
            all_done = False

    if all_done:
        log(f"  All {len(matching)} runs completed!")
        for s in statuses:
            log(f"    {s}")
    else:
        log(f"  Still running ({len(matching)} runs): {statuses[:3]}...")

    return all_done, matching

def pull_results():
    """Git pull to get results committed by Actions."""
    rc, out = git(["pull", "--rebase", "origin", "master"])
    if rc != 0:
        log(f"  Pull conflict, trying checkout strategy: {out[:200]}")
        git(["checkout", "--theirs", "."])
        git(["add", "-A"])
        env = dict(os.environ, GIT_EDITOR="true")
        r2 = subprocess.run(["git", "rebase", "--continue"], capture_output=True, cwd=REPO_DIR, env=env)
        log(f"  Rebase continue: {r2.returncode}")
    else:
        log("  Pull successful")
    return rc == 0

def parse_phase1_results(version_dir):
    """Parse Phase 1 results from a version's results directory."""
    results = []
    # Try v6a-results/phase1-merged/all_strategies.json etc
    for pattern in [f"{version_dir}*/phase1-merged/all_strategies.json",
                    f"{version_dir}*/phase1/all_strategies.json"]:
        for f in glob.glob(os.path.join(REPO_DIR, pattern)):
            try:
                data = json.load(open(f, "r", encoding="utf-8"))
                strategies = data.get("strategies", data if isinstance(data, list) else [])
                results.extend(strategies)
                log(f"  Loaded {len(strategies)} strategies from {os.path.basename(f)}")
            except Exception as e:
                log(f"  Error loading {f}: {e}")
    return results

def parse_phase2_results(version_prefix):
    """Parse Phase 2 rolling window results."""
    results = []
    # Try v6a-results/final/rolling_window_final.json
    for pattern in [f"{version_prefix}*/final/rolling_window_final.json",
                    f"{version_prefix}*/phase2-*/rolling_window_chunk*.json",
                    f"{version_prefix}*/v5-phase2-*/rolling_window_chunk*.json"]:
        for f in glob.glob(os.path.join(REPO_DIR, pattern)):
            try:
                data = json.load(open(f, "r", encoding="utf-8"))
                strategies = data.get("strategies", data if isinstance(data, list) else [])
                results.extend(strategies)
                log(f"  Loaded {len(strategies)} RW strategies from {os.path.basename(f)}")
            except Exception as e:
                log(f"  Error loading {f}: {e}")

    # Also check backtest/results_revalidation/
    for f in glob.glob(os.path.join(REPO_DIR, "backtest/results_revalidation/rolling_window_chunk*.json")):
        try:
            data = json.load(open(f, "r", encoding="utf-8"))
            strategies = data.get("strategies", data if isinstance(data, list) else [])
            results.extend(strategies)
        except:
            pass

    return results

def analyze_results(phase1, phase2):
    """Analyze results and return best strategies per direction."""
    # Phase 1: sort by Sharpe
    phase1.sort(key=lambda x: x.get("sharpe", 0), reverse=True)

    # Phase 2: sort by anti_overfit_score
    phase2.sort(key=lambda x: x.get("anti_overfit_score", 0), reverse=True)
    passed = [s for s in phase2 if s.get("anti_overfit_passed", False)]

    log(f"\n{'='*80}")
    log(f"PHASE 1 TOP 10 (by Sharpe):")
    for s in phase1[:10]:
        log(f"  {s['name']:45s} ret={s.get('return',0):>+8.2f}% dd={s.get('dd',0):>6.2f}% sharpe={s.get('sharpe',0):>5.2f} trades={s.get('trades',0)}")

    if passed:
        log(f"\nPHASE 2 PASSED (anti-overfit): {len(passed)}")
        for s in passed[:10]:
            log(f"  {s['name']:45s} ret={s.get('full_return',0):>+8.2f}% sharpe={s.get('full_sharpe',0):>5.2f} AO={s.get('anti_overfit_score',0):>5.1f}")
    elif phase2:
        log(f"\nPHASE 2 TOP 10 (no anti-overfit pass, by score):")
        for s in phase2[:10]:
            log(f"  {s['name']:45s} ret={s.get('full_return',0):>+8.2f}% AO={s.get('anti_overfit_score',0):>5.1f} passed={s.get('anti_overfit_passed',False)}")

    return phase1, passed if passed else phase2

def extract_best_configs(phase1, phase2_passed, top_n=5):
    """Extract top N configs from each direction for cross-combination."""
    # Use phase2 if available, else phase1
    source = phase2_passed if phase2_passed else phase1
    best = source[:top_n]
    configs = []
    for s in best:
        cfg = s.get("config", {})
        if cfg:
            configs.append((s["name"], cfg, s.get("return", s.get("full_return", 0)),
                          s.get("sharpe", s.get("full_sharpe", 0))))
    return configs

def generate_next_version(version_num, best_configs, prev_champion_return):
    """Generate next version configs by cross-combining best strategies."""
    version_letter = chr(ord('a') + version_num - 6)  # V6->a, V7->b, etc
    version_name = f"V{version_num}"
    S = []

    BASE = {
        "start_date": "2023-07-17", "end_date": "2026-07-24", "initial_cash": 10000,
        "monthly_injection": 0,
        "weights": {"quality": 25, "cost": 20, "manager": 20, "momentum": 15, "smart_money": 20},
        "min_score": 3.3, "no_stop_loss": True, "take_profit_pct": 1000, "profit_mode": "half",
        "cost_penalty": 0, "min_consensus": 2, "fund_type_filter": "all", "momentum_sell": 0,
        "max_candidates_per_day": 0, "max_holdings": 8, "kelly_cap": 0.35,
        "smart_swap": True, "smart_swap_margin": 1.0, "smart_swap_min_hold_days": 30,
        "dynamic_max_holdings": True, "max_holdings_bull_mult": 1.5, "max_holdings_bear_mult": 0.6,
    }

    def add(name, overrides):
        cfg = copy.deepcopy(BASE)
        cfg.update(overrides)
        S.append({"name": name, "desc": "", "config": cfg})

    # Collect unique non-base params from best configs
    all_params = set()
    for _, cfg, _, _ in best_configs:
        for k in cfg:
            if k not in BASE and k not in ("start_date", "end_date", "initial_cash", "weights"):
                all_params.add(k)

    log(f"  Unique params from best: {sorted(all_params)}")

    # Strategy 1: Cross-combine top configs pairwise
    for i in range(len(best_configs)):
        for j in range(i+1, len(best_configs)):
            name1, cfg1, _, _ = best_configs[i]
            name2, cfg2, _, _ = best_configs[j]
            # Merge non-base params from both
            merged = {}
            for k in all_params:
                if k in cfg1:
                    merged[k] = cfg1[k]
                if k in cfg2 and k not in merged:
                    merged[k] = cfg2[k]
            # If both have same param with different values, use cfg1's (higher ranked)
            add(f"{version_name}_X1_{i}_{j}", merged)

    # Strategy 2: Each best config as-is (baseline reproduction)
    for i, (name, cfg, _, _) in enumerate(best_configs):
        overrides = {k: v for k, v in cfg.items() if k not in BASE}
        add(f"{version_name}_Z0_best{i}", overrides)

    # Strategy 3: Champion + fine-tuning around key params
    if best_configs:
        champ_name, champ_cfg, champ_ret, champ_sharpe = best_configs[0]
        champ_overrides = {k: v for k, v in champ_cfg.items() if k not in BASE}

        # Fine-tune contrarian_buy_drop
        if "contrarian_buy_drop" in champ_overrides:
            drop = champ_overrides["contrarian_buy_drop"]
            for d_offset in [-0.005, 0.005]:
                new_drop = round(drop + d_offset, 4)
                if new_drop > 0:
                    o = copy.deepcopy(champ_overrides)
                    o["contrarian_buy_drop"] = new_drop
                    add(f"{version_name}_F1_drop{new_drop}", o)

        # Fine-tune kelly_cap
        kc = champ_overrides.get("kelly_cap", 0.35)
        for kc_new in [0.30, 0.40, 0.45, 0.50]:
            if abs(kc_new - kc) > 0.01:
                o = copy.deepcopy(champ_overrides)
                o["kelly_cap"] = kc_new
                add(f"{version_name}_F1_kc{kc_new}", o)

        # Fine-tune monthly_injection
        inj = champ_overrides.get("monthly_injection", 0)
        if inj > 0:
            for inj_new in [inj // 2, inj * 2]:
                if inj_new > 0:
                    o = copy.deepcopy(champ_overrides)
                    o["monthly_injection"] = inj_new
                    add(f"{version_name}_F1_inj{inj_new}", o)

        # Fine-tune trailing_tp
        trail_act = champ_overrides.get("trailing_tp_activate", 0)
        if trail_act > 0:
            for (ta, td) in [(trail_act-5, 8), (trail_act+5, 12), (trail_act, 6), (trail_act, 14)]:
                if ta > 0:
                    o = copy.deepcopy(champ_overrides)
                    o["trailing_tp_activate"] = ta
                    o["trailing_tp_drawdown"] = td
                    add(f"{version_name}_F1_trail{ta}_{td}", o)

        # Fine-tune require_4433_pass
        r4433 = champ_overrides.get("require_4433_pass", 0)
        if r4433 > 0:
            o = copy.deepcopy(champ_overrides)
            o["require_4433_pass"] = r4433 + 1
            add(f"{version_name}_F1_4433_{r4433+1}", o)

        # Champion + equal_allocate variant
        o = copy.deepcopy(champ_overrides)
        o["equal_allocate"] = True
        add(f"{version_name}_F1_equal", o)

        # Champion + max_sector_count
        for msc in [2, 3]:
            o = copy.deepcopy(champ_overrides)
            o["max_sector_count"] = msc
            add(f"{version_name}_F1_sec{msc}", o)

    # Strategy 4: Weight variants on champion (almost free due to score cache)
    if best_configs:
        champ_name, champ_cfg, _, _ = best_configs[0]
        champ_overrides = {k: v for k, v in champ_cfg.items() if k not in BASE}
        weight_variants = [
            ("equal_w", {"quality": 20, "cost": 20, "manager": 20, "momentum": 20, "smart_money": 20}),
            ("mom_heavy", {"quality": 20, "cost": 15, "manager": 15, "momentum": 30, "smart_money": 20}),
            ("sm_heavy", {"quality": 20, "cost": 15, "manager": 15, "momentum": 15, "smart_money": 35}),
            ("qual_heavy", {"quality": 35, "cost": 20, "manager": 20, "momentum": 10, "smart_money": 15}),
            ("cost_heavy", {"quality": 25, "cost": 35, "manager": 15, "momentum": 10, "smart_money": 15}),
        ]
        for wname, weights in weight_variants:
            o = copy.deepcopy(champ_overrides)
            add(f"{version_name}_W1_{wname}", {**o, "weights": weights})

    # Strategy 5: Ultimate combo - all best params merged
    if len(best_configs) >= 3:
        ultimate = {}
        for _, cfg, _, _ in best_configs[:3]:
            for k, v in cfg.items():
                if k not in BASE and k not in ("start_date", "end_date", "initial_cash", "weights"):
                    if k not in ultimate:
                        ultimate[k] = v
        add(f"{version_name}_H1_ultimate", ultimate)

    # Baseline
    add(f"{version_name}_Z0_baseline", {})

    # Deduplicate by config content
    seen = set()
    unique = []
    for s in S:
        key = json.dumps(s["config"], sort_keys=True)
        if key not in seen:
            seen.add(key)
            unique.append(s)

    log(f"  Generated {len(unique)} strategies for {version_name} (deduped from {len(S)})")
    return unique

def create_workflow_yml(version_num, strategy_count):
    """Create workflow YAML by copying V5 template and replacing."""
    version_letter = chr(ord('a') + version_num - 6)  # V6->a, V7->b...
    version_name = f"v{version_num}"
    version_upper = f"V{version_num}"

    template = open(os.path.join(REPO_DIR, ".github/workflows/v5-sweep.yml"), "r", encoding="utf-8").read()
    # Only replace v5/V5 in specific contexts (not action versions like @v5)
    yml = template.replace("V5 Fine-Tuned Sweep", f"{version_upper} Auto-Evolution Sweep")
    yml = yml.replace("v5_sweep_configs", f"{version_name}_sweep_configs")
    yml = yml.replace("v5-results", f"{version_name}-results")
    yml = yml.replace("v5-phase1", f"{version_name}-phase1")
    yml = yml.replace("v5-phase2", f"{version_name}-phase2")
    yml = yml.replace("v5-final", f"{version_name}-final")
    yml = yml.replace("v5-phase1-merged", f"{version_name}-phase1-merged")
    yml = yml.replace("'20'", "'10'")
    yml = yml.replace("max-parallel: 20", "max-parallel: 10")
    yml = yml.replace("top30", "top20")
    yml = yml.replace("Top30", "Top20")
    yml = yml.replace("top_n || 30", "top_n || 20")
    yml = yml.replace("94 strategies", f"{strategy_count} strategies")

    out_path = os.path.join(REPO_DIR, f".github/workflows/{version_name}-sweep.yml")
    open(out_path, "w", encoding="utf-8").write(yml)
    log(f"  Created workflow: {out_path}")
    return out_path

def push_and_trigger(version_num, strategies, workflow_path):
    """Save configs, commit, push, and trigger workflow."""
    version_name = f"v{version_num}"
    version_upper = f"V{version_num}"

    # Save configs JSON
    config_path = os.path.join(REPO_DIR, f"backtest/{version_name}_sweep_configs.json")
    json.dump(strategies, open(config_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    # Also save configs generator for reproducibility
    gen_path = os.path.join(REPO_DIR, f"backtest/{version_name}_configs.py")
    with open(gen_path, "w", encoding="utf-8") as f:
        f.write(f"#!/usr/bin/env python3\n\"\"\"{version_upper} auto-generated configs ({len(strategies)} strategies).\"\"\"\n")
        f.write(f"import json\nconfigs = json.load(open('{version_name}_sweep_configs.json', encoding='utf-8'))\n")
        f.write(f"print(f'{version_upper}: {len(configs)} strategies')\n")

    # Git add, commit, push
    git(["add", config_path, gen_path, workflow_path])
    git(["commit", "-m", f"{version_upper} auto-evolution: {len(strategies)} strategies cross-combined from previous best"])

    rc, out = git(["push", "origin", "master"])
    if rc != 0:
        log(f"  Push failed, trying pull rebase: {out[:200]}")
        git(["pull", "--rebase", "origin", "master"])
        git(["push", "origin", "master"])

    # Trigger workflow
    wf_name = f"{version_name}-sweep.yml"
    result = curl_api(f"{GH_API}/actions/workflows/{wf_name}/dispatches",
                      method="POST",
                      data={"ref": "master", "inputs": {"chunks": "10", "top_n": "20"}})

    log(f"  Triggered {wf_name}")
    return True

def run_evolution():
    """Main evolution loop."""
    log("=" * 80)
    log("AUTO-EVOLUTION STARTED")
    log(f"Max versions: V6 -> V{6+MAX_VERSIONS-1}")
    log(f"Improvement threshold: {IMPROVEMENT_THRESHOLD}%")
    log("=" * 80)

    current_version = 6  # Start by monitoring V6

    while current_version < 6 + MAX_VERSIONS:
        version_letter = chr(ord('a') + current_version - 6)
        version_prefix = f"v{current_version}"

        log(f"\n{'='*80}")
        log(f"MONITORING {version_prefix.upper()} (prefix: {version_prefix})")
        log(f"{'='*80}")

        # Wait for current version to complete
        wait_count = 0
        while True:
            done, runs = check_workflows_done(version_prefix)
            if done:
                break
            wait_count += 1
            if wait_count % 15 == 0:  # Every 30 minutes
                log(f"  Still waiting... ({wait_count * POLL_INTERVAL / 60:.0f} min elapsed)")
            time.sleep(POLL_INTERVAL)

        # Pull results
        log("\nPulling results...")
        pull_results()

        # Parse results from all sub-versions (v6a, v6b, v6c)
        log("\nParsing Phase 1 results...")
        phase1 = []
        for letter in "abcdefgh":
            phase1 += parse_phase1_results(f"{version_prefix}{letter}-results")
            phase1 += parse_phase1_results(f"{version_prefix}{letter}")

        # Also try direct patterns
        phase1 += parse_phase1_results(version_prefix)

        if not phase1:
            # Try downloading artifacts via API
            log("  No local results found, trying artifact download...")
            for run in runs:
                run_id = run.get("id")
                if run_id:
                    artifacts = curl_api(f"{GH_API}/actions/runs/{run_id}/artifacts")
                    for art in artifacts.get("artifacts", []):
                        if "final" in art["name"].lower() or "merged" in art["name"].lower():
                            log(f"    Found artifact: {art['name']}")

        log(f"\nTotal Phase 1 strategies: {len(phase1)}")

        # Parse Phase 2 results
        log("\nParsing Phase 2 results...")
        phase2 = []
        for letter in "abcdefgh":
            phase2 += parse_phase2_results(f"{version_prefix}{letter}")
        phase2 += parse_phase2_results(version_prefix)

        log(f"Total Phase 2 strategies: {len(phase2)}")

        if not phase1 and not phase2:
            log("ERROR: No results found! Skipping to next version...")
            current_version += 1
            continue

        # Analyze
        phase1_sorted, phase2_passed = analyze_results(phase1, phase2)

        # Extract best configs
        best_configs = extract_best_configs(phase1_sorted, phase2_passed, top_n=5)

        if not best_configs:
            log("ERROR: No best configs found! Skipping...")
            current_version += 1
            continue

        # Record champion
        champ = best_configs[0]
        champ_return = champ[2]
        champ_sharpe = champ[3]
        champion_history.append((current_version, champ[0], champ_return, champ_sharpe, champ[1]))
        log(f"\nCHAMPION: {champ[0]} ret={champ_return:+.2f}% sharpe={champ_sharpe:.2f}")

        # Check convergence
        if len(champion_history) >= 2:
            prev_ret = champion_history[-2][2]
            improvement = champ_return - prev_ret
            log(f"  Previous champion return: {prev_ret:+.2f}%, improvement: {improvement:+.2f}%")
            if improvement < IMPROVEMENT_THRESHOLD:
                log(f"  CONVERGENCE: improvement {improvement:+.2f}% < {IMPROVEMENT_THRESHOLD}% threshold")
                log("  Stopping evolution.")
                break

        # Generate next version
        next_version = current_version + 1
        log(f"\nGENERATING V{next_version} configs...")
        strategies = generate_next_version(next_version, best_configs, champ_return)

        if not strategies:
            log("ERROR: No strategies generated! Skipping...")
            current_version += 1
            continue

        # Create workflow and push
        workflow_path = create_workflow_yml(next_version, len(strategies))
        push_and_trigger(next_version, strategies, workflow_path)

        log(f"\nV{next_version} pushed and triggered! Monitoring next...")
        current_version = next_version

        # Brief pause before monitoring
        time.sleep(30)

    # Final summary
    log("\n" + "=" * 80)
    log("EVOLUTION COMPLETE - FINAL SUMMARY")
    log("=" * 80)
    log(f"\nChampion History:")
    for ver, name, ret, sharpe, cfg in champion_history:
        log(f"  V{ver}: {name:45s} ret={ret:+8.2f}% sharpe={sharpe:.2f}")

    if champion_history:
        best = max(champion_history, key=lambda x: x[3])  # Best Sharpe
        log(f"\nULTIMATE CHAMPION: V{best[0]} {best[1]}")
        log(f"  Return: {best[2]:+.2f}% | Sharpe: {best[3]:.2f}")
        log(f"  Config: {json.dumps(best[4], ensure_ascii=False)[:500]}")

    log("\nDone!")

if __name__ == "__main__":
    try:
        run_evolution()
    except KeyboardInterrupt:
        log("\nInterrupted by user")
    except Exception as e:
        import traceback
        log(f"\nFATAL ERROR: {e}")
        log(traceback.format_exc())
