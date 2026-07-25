#!/usr/bin/env python3
"""
v2策略扫描配置生成器：在通过验证的17个独立策略上叠加新机制参数组合。

新机制：
1. smart_swap: 择优换仓（持仓已满时，弱持仓被强候选替换）
2. rank_elimination: 持仓排名淘汰（弱持仓+有更好候选 → 卖出）
3. dynamic_max_holdings: 动态持仓上限（牛市×1.5，熊市×0.6）
4. max_sector_count: 板块集中度限制

策略设计：
- 从44个通过验证的策略中提取17个独立策略
- 对每个策略生成：
  A. 原版（不开新机制）作为对照
  B. 仅开smart_swap
  C. 仅开rank_elimination
  D. 仅开dynamic_max_holdings
  E. 仅开max_sector_count
  F. smart_swap + rank_elimination
  G. smart_swap + dynamic_max_holdings
  H. smart_swap + rank_elim + dynamic_max_holdings
  I. 全部开启
  J. 全部开启 + 不同smart_swap_margin
  K. 全部开启 + 不同rank_elim_threshold
"""
import json
import copy
import os

INPUT_FILE = os.path.join(os.path.dirname(__file__), "..", "backtest", "results_focused", "anti_overfit_passed.json")
OUTPUT_FILE = os.path.join(os.path.dirname(__file__), "v2_sweep_configs.json")

def load_passed_strategies():
    with open(INPUT_FILE, encoding="utf-8") as f:
        data = json.load(f)
    return data.get("strategies", [])

def get_unique_base_configs(strategies):
    """提取真正独立的策略——按收益+夏普+回撤去重"""
    seen_results = set()
    unique = []
    for s in sorted(strategies, key=lambda x: x.get("full_return", 0), reverse=True):
        ret = round(s.get("full_return", 0), 1)
        sharpe = round(s.get("full_sharpe", 0), 2)
        dd = round(s.get("full_dd", 0), 2)
        fingerprint = (ret, sharpe, dd)
        if fingerprint in seen_results:
            continue
        seen_results.add(fingerprint)
        unique.append({
            "name": s["name"],
            "config": s.get("config", {}),
            "return": ret,
            "sharpe": sharpe,
            "dd": dd,
        })
    return unique

def generate_v2_configs(unique_strategies):
    configs = []

    for s in unique_strategies:
        base_cfg = copy.deepcopy(s["config"])
        base_name = s["name"]
        base_ret = s["return"]

        # 确保有max_holdings（如果原版没有，默认8）
        if base_cfg.get("max_holdings", 0) == 0:
            base_cfg["max_holdings"] = 8

        # A. 原版对照
        cfg_a = copy.deepcopy(base_cfg)
        configs.append({
            "name": f"V2_{base_name}_baseline",
            "desc": f"原版对照 ret={base_ret:+.1f}%",
            "config": cfg_a,
        })

        # B. 仅smart_swap
        cfg_b = copy.deepcopy(base_cfg)
        cfg_b["smart_swap"] = True
        cfg_b["smart_swap_margin"] = 1.0
        cfg_b["smart_swap_min_hold_days"] = 30
        configs.append({
            "name": f"V2_{base_name}_swap",
            "desc": f"smart_swap margin=1.0 (原ret={base_ret:+.1f}%)",
            "config": cfg_b,
        })

        # C. 仅rank_elimination
        cfg_c = copy.deepcopy(base_cfg)
        cfg_c["rank_elimination"] = True
        cfg_c["rank_elim_threshold"] = 2.0
        cfg_c["rank_elim_min_hold_days"] = 30
        cfg_c["rank_elim_margin"] = 0.5
        configs.append({
            "name": f"V2_{base_name}_elim",
            "desc": f"rank_elim thresh=2.0 (原ret={base_ret:+.1f}%)",
            "config": cfg_c,
        })

        # D. 仅dynamic_max_holdings
        cfg_d = copy.deepcopy(base_cfg)
        cfg_d["dynamic_max_holdings"] = True
        cfg_d["max_holdings_bull_mult"] = 1.5
        cfg_d["max_holdings_bear_mult"] = 0.6
        configs.append({
            "name": f"V2_{base_name}_dynmh",
            "desc": f"dynamic_mh bull=1.5x bear=0.6x (原ret={base_ret:+.1f}%)",
            "config": cfg_d,
        })

        # E. 仅max_sector_count
        cfg_e = copy.deepcopy(base_cfg)
        cfg_e["max_sector_count"] = 3
        configs.append({
            "name": f"V2_{base_name}_sector3",
            "desc": f"max_sector_count=3 (原ret={base_ret:+.1f}%)",
            "config": cfg_e,
        })

        # F. smart_swap + rank_elim
        cfg_f = copy.deepcopy(base_cfg)
        cfg_f["smart_swap"] = True
        cfg_f["smart_swap_margin"] = 1.0
        cfg_f["smart_swap_min_hold_days"] = 30
        cfg_f["rank_elimination"] = True
        cfg_f["rank_elim_threshold"] = 2.0
        cfg_f["rank_elim_min_hold_days"] = 30
        cfg_f["rank_elim_margin"] = 0.5
        configs.append({
            "name": f"V2_{base_name}_swap_elim",
            "desc": f"swap+elim (原ret={base_ret:+.1f}%)",
            "config": cfg_f,
        })

        # G. smart_swap + dynamic_max_holdings
        cfg_g = copy.deepcopy(base_cfg)
        cfg_g["smart_swap"] = True
        cfg_g["smart_swap_margin"] = 1.0
        cfg_g["smart_swap_min_hold_days"] = 30
        cfg_g["dynamic_max_holdings"] = True
        cfg_g["max_holdings_bull_mult"] = 1.5
        cfg_g["max_holdings_bear_mult"] = 0.6
        configs.append({
            "name": f"V2_{base_name}_swap_dynmh",
            "desc": f"swap+dynmh (原ret={base_ret:+.1f}%)",
            "config": cfg_g,
        })

        # H. smart_swap + rank_elim + dynamic_max_holdings
        cfg_h = copy.deepcopy(base_cfg)
        cfg_h["smart_swap"] = True
        cfg_h["smart_swap_margin"] = 1.0
        cfg_h["smart_swap_min_hold_days"] = 30
        cfg_h["rank_elimination"] = True
        cfg_h["rank_elim_threshold"] = 2.0
        cfg_h["rank_elim_min_hold_days"] = 30
        cfg_h["rank_elim_margin"] = 0.5
        cfg_h["dynamic_max_holdings"] = True
        cfg_h["max_holdings_bull_mult"] = 1.5
        cfg_h["max_holdings_bear_mult"] = 0.6
        configs.append({
            "name": f"V2_{base_name}_swap_elim_dynmh",
            "desc": f"swap+elim+dynmh (原ret={base_ret:+.1f}%)",
            "config": cfg_h,
        })

        # I. 全部开启（含sector）
        cfg_i = copy.deepcopy(base_cfg)
        cfg_i["smart_swap"] = True
        cfg_i["smart_swap_margin"] = 1.0
        cfg_i["smart_swap_min_hold_days"] = 30
        cfg_i["rank_elimination"] = True
        cfg_i["rank_elim_threshold"] = 2.0
        cfg_i["rank_elim_min_hold_days"] = 30
        cfg_i["rank_elim_margin"] = 0.5
        cfg_i["dynamic_max_holdings"] = True
        cfg_i["max_holdings_bull_mult"] = 1.5
        cfg_i["max_holdings_bear_mult"] = 0.6
        cfg_i["max_sector_count"] = 3
        configs.append({
            "name": f"V2_{base_name}_all",
            "desc": f"全部开启 (原ret={base_ret:+.1f}%)",
            "config": cfg_i,
        })

        # J. 全部开启 + smart_swap_margin=0.5（更激进换仓）
        cfg_j = copy.deepcopy(cfg_i)
        cfg_j["smart_swap_margin"] = 0.5
        configs.append({
            "name": f"V2_{base_name}_all_aggr",
            "desc": f"全部开启+激进换仓 margin=0.5 (原ret={base_ret:+.1f}%)",
            "config": cfg_j,
        })

        # K. 全部开启 + smart_swap_margin=2.0（更保守换仓）
        cfg_k = copy.deepcopy(cfg_i)
        cfg_k["smart_swap_margin"] = 2.0
        cfg_k["rank_elim_threshold"] = 1.5  # 更低门槛，更多淘汰
        configs.append({
            "name": f"V2_{base_name}_all_cons",
            "desc": f"全部开启+保守换仓 margin=2.0 thresh=1.5 (原ret={base_ret:+.1f}%)",
            "config": cfg_k,
        })

        # L. 全部开启 + max_sector_count=2（更严格板块限制）
        cfg_l = copy.deepcopy(cfg_i)
        cfg_l["max_sector_count"] = 2
        configs.append({
            "name": f"V2_{base_name}_all_sec2",
            "desc": f"全部+sector=2 (原ret={base_ret:+.1f}%)",
            "config": cfg_l,
        })

    return configs

def main():
    strategies = load_passed_strategies()
    print(f"加载通过验证的策略: {len(strategies)} 个")

    unique = get_unique_base_configs(strategies)
    print(f"独立基础策略(按收益去重): {len(unique)} 个")
    for s in unique:
        print(f"  {s['name']:42s} ret={s['return']:+8.1f}% sharpe={s['sharpe']:5.2f} dd={s['dd']:6.2f}%")

    configs = generate_v2_configs(unique)
    print(f"\n生成 v2 策略: {len(configs)} 个")
    print(f"  {len(unique)} 策略 × 12 变体 = {len(configs)}")

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(configs, f, ensure_ascii=False, indent=2)
    print(f"保存到 {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
