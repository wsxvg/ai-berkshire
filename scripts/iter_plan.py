#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
迭代规划器 — 分析严格 OOS 结果 + 设计下一轮候选

使用规则:
1. 只在 test 结果出来后设计下一轮 (之前不能看)
2. 每轮最多 5 个候选
3. 记录每轮假设和结果
"""
import json, sys, os
from datetime import datetime


LOG_FILE = "v9-results/STRICT_OOS_LOG.md"


def analyze_round(round_num, eval_file, train_file):
    """分析一轮 OOS 结果"""
    with open(eval_file) as f:
        eval_data = json.load(f)
    with open(train_file) as f:
        train_data = json.load(f)
    
    summary = eval_data.get("summary", {})
    train_summary = train_data.get("summary", {})
    
    print(f"\n{'='*60}")
    print(f"STRICT OOS ROUND {round_num} — RESULTS")
    print(f"{'='*60}")
    
    best_test = None
    best_test_ret = -999
    
    for name, s in sorted(summary.items(), key=lambda x: -x[1]['avg_return']):
        ret = s['avg_return']
        bench = s['avg_benchmark']
        beats = s['beats_count']
        total = s['total_windows']
        status = "BEAT ✅" if ret > bench else "LOSE ❌"
        print(f"  {name}: +{ret:.3f}%/q vs CSI300 {bench:+.3f}%/q [{status}] beats {beats}/{total}")
        if ret > best_test_ret:
            best_test_ret = ret
            best_test = name
    
    # Check for overfitting: compare train vs test performance
    print(f"\n  --- Train vs Test comparison ---")
    train_best = train_data.get("best_candidate", "?")
    train_best_ret = train_summary.get(train_best, {}).get("avg_return", 0) if train_best in train_summary else 0
    
    overfit_ratio = best_test_ret / train_best_ret if train_best_ret > 0 else 0
    print(f"  Train best: {train_best} = +{train_best_ret:.3f}%/q")
    print(f"  Test best:  {best_test} = +{best_test_ret:.3f}%/q")
    print(f"  Overfit ratio (test/train): {overfit_ratio:.2f}")
    
    if overfit_ratio > 0.7:
        print(f"  → Decent generalization (ratio > 0.7)")
    elif overfit_ratio > 0.3:
        print(f"  → Mild overfitting (ratio 0.3-0.7)")
    else:
        print(f"  → SEVERE overfitting (ratio < 0.3) — discard results")
    
    return {
        "round": round_num,
        "test_best": best_test,
        "test_best_return": best_test_ret,
        "test_best_benchmark": summary.get(best_test, {}).get("avg_benchmark", 0),
        "train_best": train_best,
        "train_best_return": train_best_ret,
        "overfit_ratio": overfit_ratio,
    }


def propose_next_round(analysis):
    """根据本轮分析，提出下一轮候选 (在看到结果之前不能调用)"""
    round_num = analysis["round"] + 1
    best = analysis["test_best"]
    ret = analysis["test_best_return"]
    bench = analysis["test_best_benchmark"]
    ratio = analysis["overfit_ratio"]
    
    print(f"\n{'='*60}")
    print(f"PROPOSAL FOR ROUND {round_num}")
    print(f"{'='*60}")
    
    if ret > bench and ratio > 0.5:
        print(f"  → PROMISING: Train-test consistency is good.")
        print(f"  → Direction: explore around {best}")
        hypothesis = f"Ablation around {best}: vary 1 parameter at a time"
    elif ret > bench and ratio <= 0.5:
        print(f"  → MIXED: Beats bench but overfits. Need simpler model or more train data.")
        hypothesis = "Simplify model: reduce weight dimensions or reduce params"
    else:
        print(f"  → FAIL: {best} doesn't beat CSI300 in OOS.")
        hypothesis = "Reject current approach. Try new signal or mechanism."
    
    print(f"  hypothesis: {hypothesis}")
    return {"round": round_num, "hypothesis": hypothesis, "prev_analysis": analysis}


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "help"
    
    if mode == "analyze":
        round_num = int(sys.argv[2])
        eval_file = sys.argv[3]
        train_file = sys.argv[4]
        result = analyze_round(round_num, eval_file, train_file)
        # Save result
        with open(f"v9-results/strict_oos_r{round_num}_analysis.json", "w") as f:
            json.dump(result, f, indent=2)
        # Propose next round
        proposal = propose_next_round(result)
        with open(f"v9-results/strict_oos_r{round_num}_next.json", "w") as f:
            json.dump(proposal, f, indent=2)
    
    elif mode == "propose":
        round_num = int(sys.argv[2])
        with open(f"v9-results/strict_oos_r{round_num}_analysis.json") as f:
            analysis = json.load(f)
        propose_next_round(analysis)
    
    else:
        print("Usage:")
        print("  python iter_plan.py analyze <round> <eval_file> <train_file>")
        print("  python iter_plan.py propose <round>")
