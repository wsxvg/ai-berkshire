#!/usr/bin/env python3
"""
防过拟合通过策略的止损止盈参数优化器 v2。
从44个通过验证的策略中提取真正独立的核心策略（按收益去重），
对每个策略叠加精选的止损止盈参数组合，生成新的策略集用于回测。
"""
import json
import copy
import os

INPUT_FILE = os.path.join(os.path.dirname(__file__), "..", "_tmp_final", "anti_overfit_passed.json")
OUTPUT_FILE = os.path.join(os.path.dirname(__file__), "optimize_sweep_configs.json")

# 精选止损止盈参数网格
# 止损: -10% ~ -25%（步长5%，-30太宽松跟没止损差不多）
# 止盈: 30% ~ 80%（步长10%，100以上太久等不到）
# 追踪止盈: 0(关闭), 10%, 15%
# 动态止损: False, True
STOP_LOSS_VALUES = [-10, -15, -20, -25]
TAKE_PROFIT_VALUES = [30, 40, 50, 60, 70, 80]
TRAILING_STOP_VALUES = [0, 10, 15]
DYNAMIC_STOP_VALUES = [False, True]

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
        # 如果收益+夏普+回撤完全相同，视为同一策略的不同变体
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

def generate_optimized_configs(unique_strategies):
    """对每个独立策略叠加止损止盈参数组合"""
    configs = []

    for s in unique_strategies:
        base_cfg = copy.deepcopy(s["config"])
        base_name = s["name"]
        base_ret = s["return"]

        # 移除原有止损止盈参数
        clean_cfg = copy.deepcopy(base_cfg)
        clean_cfg.pop("stop_loss_pct", None)
        clean_cfg.pop("take_profit_pct", None)
        clean_cfg.pop("no_stop_loss", None)
        clean_cfg.pop("trailing_stop_pct", None)
        clean_cfg.pop("dynamic_stop_loss", None)

        # 1. 保留原版作为对照
        orig_cfg = copy.deepcopy(base_cfg)
        orig_cfg["no_stop_loss"] = base_cfg.get("no_stop_loss", True)
        if not orig_cfg["no_stop_loss"]:
            orig_cfg["stop_loss_pct"] = base_cfg.get("stop_loss_pct", -20)
            orig_cfg["take_profit_pct"] = base_cfg.get("take_profit_pct", 80)
        else:
            orig_cfg["take_profit_pct"] = base_cfg.get("take_profit_pct", 1000)
        configs.append({
            "name": f"OPT_{base_name}_ORIG",
            "desc": f"原版 ret={base_ret:+.1f}%",
            "config": orig_cfg,
        })

        # 2. 叠加所有止损止盈参数组合
        for sl in STOP_LOSS_VALUES:
            for tp in TAKE_PROFIT_VALUES:
                for dyn in DYNAMIC_STOP_VALUES:
                    for trail in TRAILING_STOP_VALUES:
                        cfg = copy.deepcopy(clean_cfg)
                        cfg["no_stop_loss"] = False
                        cfg["stop_loss_pct"] = sl
                        cfg["take_profit_pct"] = tp
                        if dyn:
                            cfg["dynamic_stop_loss"] = True
                        if trail > 0:
                            cfg["trailing_stop_pct"] = trail

                        tags = [f"sl{sl}", f"tp{tp}"]
                        if dyn:
                            tags.append("dyn")
                        if trail > 0:
                            tags.append(f"tr{trail}")
                        tag_str = "_".join(tags)

                        configs.append({
                            "name": f"OPT_{base_name}_{tag_str}",
                            "desc": f"sl={sl}% tp={tp}%{' dyn' if dyn else ''}{' tr='+str(trail)+'%' if trail > 0 else ''} (原ret={base_ret:+.1f}%)",
                            "config": cfg,
                        })

    return configs

def main():
    strategies = load_passed_strategies()
    print(f"加载通过验证的策略: {len(strategies)} 个")

    unique = get_unique_base_configs(strategies)
    print(f"独立基础策略(按收益去重): {len(unique)} 个")
    for s in unique:
        print(f"  {s['name']:42s} ret={s['return']:+8.1f}% sharpe={s['sharpe']:5.2f} dd={s['dd']:6.2f}%")

    configs = generate_optimized_configs(unique)
    print(f"\n生成优化策略: {len(configs)} 个")

    # 保存
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(configs, f, ensure_ascii=False, indent=2)
    print(f"保存到 {OUTPUT_FILE}")

    # 参数空间统计
    combos_per_strategy = (len(STOP_LOSS_VALUES) * len(TAKE_PROFIT_VALUES) *
                           len(DYNAMIC_STOP_VALUES) * len(TRAILING_STOP_VALUES))
    print(f"\n参数空间: {len(STOP_LOSS_VALUES)} sl x {len(TAKE_PROFIT_VALUES)} tp x "
          f"{len(DYNAMIC_STOP_VALUES)} dyn x {len(TRAILING_STOP_VALUES)} trail = "
          f"{combos_per_strategy} 组合/策略")
    print(f"  + 1 原版 = {combos_per_strategy + 1} 变体/策略")
    print(f"  x {len(unique)} 独立策略 = {len(configs)} 总策略")

if __name__ == "__main__":
    main()
