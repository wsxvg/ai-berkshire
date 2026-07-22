#!/usr/bin/env python3
"""大佬精选策略扫描生成器。

利用引擎内置的 dynamic_ranking 功能（无未来函数），
生成~1000个大佬精选策略配置。

核心思路: 只跟最强的大佬，不跟韭菜。

参数维度:
  - ranking_window: 回看窗口 (30/60/90/180/365天)
  - ranking_half_life: 时间衰减半衰期 (15/30/45/90/180天)
  - ranking_min_buys: 最少交易次数 (3/5/10/15)
  - ranking_recalc_days: 重算间隔 (7/14/30/60天)
  - kelly_cap: 凯利系数 (0.05/0.1/0.15/0.2/0.3/0.35)
  - momentum_sell: 动量卖出 (0/0.5/1.0/1.5)
  - take_profit_pct: 止盈 (50/100/200/1000)
  - min_consensus: 共识人数 (1/2/3)
  - max_holdings: 持仓上限 (0/5/10/20)

输出: backtest/player_sweep_configs.json
"""
import json, itertools
from pathlib import Path

# J冠军基础参数
J_BASE = {
    "no_stop_loss": True,
    "take_profit_pct": 1000,
    "profit_mode": "half",
    "momentum_sell": 1.5,
    "dynamic_ranking": True,  # 核心开关
}

def gen_configs():
    configs = []

    # ── 1. 单参数扫描: ranking_window × J基础 ──
    for rw in [30, 60, 90, 180, 365]:
        for ms in [0, 0.5, 1.0, 1.5]:
            configs.append({
                "name": f"P_rw{rw}_ms{ms}",
                "desc": f"window={rw}d mom_sell={ms}",
                "config": {**J_BASE, "ranking_window": rw, "momentum_sell": ms},
            })

    # ── 2. 单参数扫描: half_life × min_buys ──
    for hl in [15, 30, 45, 90, 180]:
        for mb in [3, 5, 10, 15]:
            configs.append({
                "name": f"P_hl{hl}_mb{mb}",
                "desc": f"half_life={hl}d min_buys={mb}",
                "config": {**J_BASE, "ranking_half_life": hl, "ranking_min_buys": mb},
            })

    # ── 3. 双参数组合: window × half_life ──
    for rw in [30, 90, 180, 365]:
        for hl in [15, 45, 90, 180]:
            configs.append({
                "name": f"P_rw{rw}_hl{hl}",
                "desc": f"window={rw} half_life={hl}",
                "config": {**J_BASE, "ranking_window": rw, "ranking_half_life": hl},
            })

    # ── 4. recalc_days × min_buys ──
    for rd in [7, 14, 30, 60]:
        for mb in [3, 5, 10]:
            configs.append({
                "name": f"P_rd{rd}_mb{mb}",
                "desc": f"recalc={rd}d min_buys={mb}",
                "config": {**J_BASE, "ranking_recalc_days": rd, "ranking_min_buys": mb},
            })

    # ── 5. kelly_cap × momentum_sell (J冠军变体) ──
    for kc in [0.05, 0.1, 0.15, 0.2, 0.3, 0.35]:
        for ms in [0, 0.5, 1.0, 1.5]:
            configs.append({
                "name": f"P_kc{kc}_ms{ms}",
                "desc": f"kelly={kc} mom_sell={ms}",
                "config": {**J_BASE, "kelly_cap": kc, "momentum_sell": ms},
            })

    # ── 6. take_profit × min_consensus ──
    for tp in [50, 100, 200, 500, 1000]:
        for mc in [1, 2, 3]:
            configs.append({
                "name": f"P_tp{tp}_mc{mc}",
                "desc": f"tp={tp} consensus={mc}",
                "config": {**J_BASE, "take_profit_pct": tp, "min_consensus": mc},
            })

    # ── 7. 三参数核心组合: window × half_life × kelly ──
    for rw in [60, 180]:
        for hl in [30, 90]:
            for kc in [0.1, 0.2, 0.35]:
                configs.append({
                    "name": f"P_rw{rw}_hl{hl}_kc{kc}",
                    "desc": f"w={rw} hl={hl} kelly={kc}",
                    "config": {**J_BASE, "ranking_window": rw,
                              "ranking_half_life": hl, "kelly_cap": kc},
                })

    # ── 8. max_holdings 变体 ──
    for mh in [0, 5, 10, 15, 20]:
        for mc in [1, 2]:
            configs.append({
                "name": f"P_mh{mh}_mc{mc}",
                "desc": f"max_holdings={mh} consensus={mc}",
                "config": {**J_BASE, "max_holdings": mh, "min_consensus": mc},
            })

    # ── 9. fund_type_filter 变体 ──
    for ft in ["all", "active", "passive"]:
        for rw in [90, 365]:
            configs.append({
                "name": f"P_ft{ft}_rw{rw}",
                "desc": f"type={ft} window={rw}",
                "config": {**J_BASE, "fund_type_filter": ft, "ranking_window": rw},
            })

    # ── 10. 随机组合 (200个) ──
    import random
    random.seed(999)
    param_space = {
        "ranking_window": [30, 60, 90, 180, 365],
        "ranking_half_life": [15, 30, 45, 90, 180],
        "ranking_min_buys": [3, 5, 10, 15],
        "ranking_recalc_days": [7, 14, 30, 60],
        "kelly_cap": [0.05, 0.1, 0.15, 0.2, 0.3, 0.35],
        "momentum_sell": [0, 0.5, 1.0, 1.5],
        "take_profit_pct": [50, 100, 200, 500, 1000],
        "min_consensus": [1, 2, 3],
        "max_holdings": [0, 5, 10, 20],
    }
    for i in range(200):
        config = dict(J_BASE)
        n_params = random.randint(3, 6)
        selected = random.sample(list(param_space.keys()), n_params)
        for dim in selected:
            config[dim] = random.choice(param_space[dim])
        configs.append({
            "name": f"P_rnd{i:03d}",
            "desc": f"random({n_params}dims)",
            "config": config,
        })

    return configs


def main():
    configs = gen_configs()
    print(f"Total: {len(configs)} player selection strategies")

    out = Path(__file__).resolve().parent / "player_sweep_configs.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(configs, f, ensure_ascii=False, indent=2)
    print(f"Saved to {out}")


if __name__ == "__main__":
    main()
