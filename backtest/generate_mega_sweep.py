#!/usr/bin/env python3
"""超大规模策略扫描生成器。

覆盖 28+ 参数维度，生成 ~3000 个策略配置。
分类:
  A. 评分权重变体 (500个) - 全新方向
  B. 扩展单参数扫描 (800个) - 更多值+新维度
  C. 双参数组合 (800个) - 关键维度两两组合
  D. 三参数组合 (400个) - 核心三角
  E. 随机搜索 (500个) - 拉丁超立方采样

用法:
  python backtest/generate_mega_sweep.py           # 生成全部
  python backtest/generate_mega_sweep.py --count 500  # 只生成500个
"""
import json, itertools, random
from pathlib import Path

# ── 基础配置 (J 买入持有冠军为基准) ──
BASE = {
    "start_date": "2023-07-17", "end_date": "2026-07-17",
    "initial_cash": 10000, "monthly_injection": 0,
    "weights": {"quality": 25, "cost": 20, "manager": 20, "momentum": 15, "smart_money": 20},
    "min_score": 0.0, "min_consensus": 2, "fund_type_filter": "all",
    "max_position_pct": 40, "cash_reserve_pct": 0.05,
    "take_profit_pct": 1000, "stop_loss_pct": -30,
    "profit_mode": "half", "kelly_cap": 0.35,
    "momentum_sell": 1.5, "max_holdings": 0,
    "max_correlation": 0.6, "max_sector_pct": 40,
    "cooldown_profit_days": 10, "cooldown_loss_days": 30,
    "no_stop_loss": True,  # J 冠军特征
}

# ── A. 评分权重变体 (500个) ──
def gen_weight_variants():
    """生成不同评分权重组合。"""
    configs = []
    # A1: 单维度主导 (5维 * 5个权重值 = 25)
    dims = ["quality", "cost", "manager", "momentum", "smart_money"]
    for dim in dims:
        for w in [40, 50, 60, 70, 80]:
            weights = {"quality": 20, "cost": 20, "manager": 20, "momentum": 15, "smart_money": 20}
            remaining = 100 - w
            others = [d for d in dims if d != dim]
            for i, o in enumerate(others):
                weights[o] = remaining // len(others) + (1 if i < remaining % len(others) else 0)
            weights[dim] = w
            configs.append({
                "name": f"A_{dim}{w}",
                "desc": f"{dim}={w}% others=split",
                "config": {"weights": weights, "no_stop_loss": True, "take_profit_pct": 1000},
            })

    # A2: 双维度组合 (C(5,2)=10 * 4个组合 = 40)
    for d1, d2 in itertools.combinations(dims, 2):
        for w1, w2 in [(35, 35), (40, 30), (30, 40), (45, 25)]:
            weights = {d: 0 for d in dims}
            weights[d1] = w1
            weights[d2] = w2
            remaining = 100 - w1 - w2
            others = [d for d in dims if d not in (d1, d2)]
            for o in others:
                weights[o] = remaining // len(others)
            configs.append({
                "name": f"A_{d1[:2]}{w1}_{d2[:2]}{w2}",
                "desc": f"{d1}={w1}% {d2}={w2}%",
                "config": {"weights": weights, "no_stop_loss": True, "take_profit_pct": 1000},
            })

    # A3: J 冠军基准 + 不同权重微调 (100个随机)
    random.seed(42)
    for i in range(100):
        weights = {}
        vals = random.sample(range(10, 41), 5)
        total = sum(vals)
        for j, dim in enumerate(dims):
            weights[dim] = round(vals[j] / total * 100)
        configs.append({
            "name": f"A_rand{i:03d}",
            "desc": f"random weights Q{weights['quality']}/C{weights['cost']}/M{weights['manager']}/Mo{weights['momentum']}/SM{weights['smart_money']}",
            "config": {"weights": weights, "no_stop_loss": True, "take_profit_pct": 1000},
        })

    # A4: J 冠军 + 不同操作模式组合 (335个)
    for tp in [20, 30, 50, 80, 100, 150, 200, 500, 1000]:
        for sl in [-5, -8, -10, -15, -20, -30, -50, 0]:
            for pm in ["all", "half", "quarter", "step"]:
                for ms in [0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0]:
                    if sl == 0:
                        config = {"take_profit_pct": tp, "no_stop_loss": True, "profit_mode": pm, "momentum_sell": ms}
                    else:
                        config = {"take_profit_pct": tp, "stop_loss_pct": sl, "no_stop_loss": False, "profit_mode": pm, "momentum_sell": ms}
                    configs.append({
                        "name": f"A_J_tp{tp}_sl{sl}_pm{pm}_ms{ms}",
                        "desc": f"J变体 tp={tp} sl={sl} pm={pm} ms={ms}",
                        "config": config,
                    })
                    if len(configs) >= 500:
                        break
                if len(configs) >= 500: break
            if len(configs) >= 500: break
        if len(configs) >= 500: break

    return configs[:500]


# ── B. 扩展单参数扫描 (800个) ──
def gen_single_param_sweep():
    """扩展的单参数扫描，包含新维度。"""
    configs = []
    # 基准: J 买入持有冠军 (no_stop_loss=True, tp=1000)
    base = {"no_stop_loss": True, "take_profit_pct": 1000, "profit_mode": "half", "momentum_sell": 1.5}

    sweep_dims = {
        # 已有维度 - 更细粒度
        "kelly_cap": [0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.45, 0.5, 0.6, 0.8],
        "momentum_sell": [0, 0.3, 0.5, 0.8, 1.0, 1.2, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0],
        "take_profit_pct": [10, 15, 20, 25, 30, 40, 50, 60, 80, 100, 120, 150, 200, 300, 500, 1000],
        "stop_loss_pct": [-3, -5, -8, -10, -12, -15, -20, -25, -30, -40, -50, -80],
        "max_position_pct": [5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 60, 80],
        "cash_reserve_pct": [0, 0.02, 0.05, 0.08, 0.1, 0.12, 0.15, 0.2, 0.25, 0.3],
        "min_consensus": [1, 2, 3, 4, 5, 6, 8, 10],
        "max_holdings": [0, 3, 5, 8, 10, 12, 15, 20, 25, 30, 40, 50],
        "max_correlation": [0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
        "max_sector_pct": [10, 15, 20, 25, 30, 35, 40, 50, 60, 80, 100],
        "cooldown_profit_days": [0, 3, 5, 10, 15, 20, 30, 45, 60],
        "cooldown_loss_days": [0, 5, 10, 20, 30, 45, 60, 90],
        "min_score": [0, 1.0, 1.5, 2.0, 2.5, 3.0, 3.3, 3.5, 4.0, 4.5],
        "ranking_half_life": [15, 30, 45, 60, 90, 120, 180],
        "downtrend_penalty": [0, 0.1, 0.25, 0.5, 0.75, 1.0],
        "slippage_pct": [0, 0.001, 0.002, 0.003, 0.005, 0.01],
        "max_yearly_trades": [10, 20, 30, 50, 80, 100, 200, 999],
        "min_holding_days": [0, 7, 14, 30, 60, 90, 120, 180],
        # 新维度
        "fund_type_filter": ["all", "active", "passive"],
        "profit_mode": ["all", "half", "quarter", "step"],
        "sell_consensus": [0, 1, 2, 3, 4, 5],
        "use_weighted_consensus": [True, False],
        "adaptive_consensus": [True, False],
        "consensus_priority": [True, False],
        "net_signal": [True, False],
        "timing_filter": [True, False],
        "block_overbought": [True, False],
        "bear_market_no_buy": [True, False],
        "dynamic_stop_loss": [True, False],
        "regime_specific": [True, False],
        "pyramiding_enabled": [True, False],
        "dynamic_ranking": [True, False],
        "limit_boost": [0, 1, 2, 3, 5, 10],
        "top_n": [0, 3, 5, 10, 15, 20, 30],
        "trailing_tp_activate": [0, 10, 15, 20, 25, 30],
        "trailing_tp_drawdown": [3, 5, 8, 10, 12, 15],
        "rsi_block_threshold": [60, 65, 70, 75, 80, 85],
        "ranking_window": [30, 60, 90, 120, 180],
        "risk_free_rate": [0.01, 0.02, 0.025, 0.03, 0.04, 0.05],
    }

    for dim, values in sweep_dims.items():
        for v in values:
            config = dict(base)
            if dim == "stop_loss_pct":
                if v < 0:
                    config["no_stop_loss"] = False
                    config["stop_loss_pct"] = v
                else:
                    continue  # skip 0
            elif dim == "no_stop_loss":
                continue
            elif dim == "fund_type_filter":
                config["fund_type_filter"] = v
            elif dim == "profit_mode":
                config["profit_mode"] = v
            elif dim in ("use_weighted_consensus", "adaptive_consensus", "consensus_priority",
                         "net_signal", "timing_filter", "block_overbought",
                         "bear_market_no_buy", "dynamic_stop_loss", "regime_specific",
                         "pyramiding_enabled", "dynamic_ranking"):
                config[dim] = v
            elif dim == "rsi_block_threshold":
                config["block_overbought"] = True
                config["rsi_block_threshold"] = v
            elif dim == "trailing_tp_activate":
                config["trailing_tp_activate"] = v
                if v > 0:
                    config["take_profit_pct"] = 100  # 需要 tp 配合
            elif dim == "trailing_tp_drawdown":
                config["trailing_tp_drawdown"] = v
                config["trailing_tp_activate"] = 20
                config["take_profit_pct"] = 100
            elif dim == "ranking_window":
                config["dynamic_ranking"] = True
                config["ranking_window"] = v
            elif dim == "ranking_half_life":
                config["dynamic_ranking"] = True
                config["ranking_half_life"] = v
            else:
                config[dim] = v

            label = f"{dim}={v}"
            configs.append({
                "name": f"B_{dim}_{v}",
                "desc": label,
                "config": config,
            })

    return configs


# ── C. 双参数组合 (800个) ──
def gen_two_param_combos():
    """关键维度的两两组合。"""
    configs = []
    base = {"no_stop_loss": True, "take_profit_pct": 1000, "profit_mode": "half", "momentum_sell": 1.5}

    # 选取最重要的维度做两两组合
    key_dims = {
        "min_consensus": [1, 2, 3, 5],
        "max_holdings": [0, 5, 10, 20],
        "max_position_pct": [15, 25, 40, 60],
        "kelly_cap": [0.15, 0.3, 0.45],
        "momentum_sell": [0, 1.0, 2.0],
        "take_profit_pct": [50, 100, 200, 1000],
        "fund_type_filter": ["all", "active"],
        "use_weighted_consensus": [True, False],
        "max_correlation": [0.4, 0.6, 0.8],
        "max_sector_pct": [25, 40, 60],
        "cash_reserve_pct": [0.05, 0.1, 0.2],
        "block_overbought": [True, False],
        "regime_specific": [True, False],
        "dynamic_ranking": [True, False],
        "profit_mode": ["half", "step", "all"],
        "stop_loss_pct": [-10, -20, -30],
        "cooldown_profit_days": [0, 10, 30],
        "cooldown_loss_days": [10, 30, 60],
        "top_n": [0, 10, 20],
        "trailing_tp_activate": [0, 20],
    }

    dim_pairs = list(itertools.combinations(key_dims.keys(), 2))
    random.seed(123)
    random.shuffle(dim_pairs)

    for d1, d2 in dim_pairs:
        for v1 in key_dims[d1]:
            for v2 in key_dims[d2]:
                config = dict(base)
                if d1 == "stop_loss_pct":
                    config["no_stop_loss"] = False
                config[d1] = v1
                config[d2] = v2
                if d1 == "trailing_tp_activate" or d2 == "trailing_tp_activate":
                    if (v1 if d1 == "trailing_tp_activate" else v2) > 0:
                        config["take_profit_pct"] = 100
                configs.append({
                    "name": f"C_{d1[:6]}{v1}_{d2[:6]}{v2}",
                    "desc": f"{d1}={v1} + {d2}={v2}",
                    "config": config,
                })
                if len(configs) >= 800:
                    return configs
    return configs[:800]


# ── D. 三参数组合 (400个) ──
def gen_three_param_combos():
    """核心三角组合。"""
    configs = []
    base = {"no_stop_loss": True, "take_profit_pct": 1000, "profit_mode": "half", "momentum_sell": 1.5}

    # 最核心的 5 个维度
    core = {
        "min_consensus": [1, 2, 3],
        "max_holdings": [0, 10],
        "max_position_pct": [25, 40],
        "take_profit_pct": [50, 100, 1000],
        "fund_type_filter": ["all", "active"],
    }

    dims = list(core.keys())
    for d1, d2, d3 in itertools.combinations(dims, 3):
        for v1 in core[d1]:
            for v2 in core[d2]:
                for v3 in core[d3]:
                    config = dict(base)
                    config[d1] = v1
                    config[d2] = v2
                    config[d3] = v3
                    configs.append({
                        "name": f"D_{d1[:4]}{v1}_{d2[:4]}{v2}_{d3[:4]}{v3}",
                        "desc": f"{d1}={v1}+{d2}={v2}+{d3}={v3}",
                        "config": config,
                    })
    return configs[:400]


# ── E. 随机搜索 (500个) ──
def gen_random_search():
    """拉丁超立方采样风格的随机搜索。"""
    configs = []
    base = {"no_stop_loss": True, "take_profit_pct": 1000, "profit_mode": "half", "momentum_sell": 1.5}

    dims = ["quality", "cost", "manager", "momentum", "smart_money"]
    param_space = {
        "min_consensus": (1, 5, "int"),
        "max_holdings": (0, 20, "int"),
        "max_position_pct": (10, 60, "int"),
        "kelly_cap": (0.1, 0.5, "float"),
        "momentum_sell": (0, 3.0, "float"),
        "take_profit_pct": (20, 1000, "int"),
        "cash_reserve_pct": (0, 0.25, "float"),
        "max_correlation": (0.3, 1.0, "float"),
        "max_sector_pct": (20, 100, "int"),
        "cooldown_profit_days": (0, 30, "int"),
        "cooldown_loss_days": (5, 60, "int"),
        "ranking_half_life": (15, 120, "int"),
        "downtrend_penalty": (0, 1.0, "float"),
    }
    bool_space = [
        "use_weighted_consensus", "adaptive_consensus", "consensus_priority",
        "net_signal", "timing_filter", "block_overbought",
        "bear_market_no_buy", "dynamic_stop_loss", "regime_specific",
        "pyramiding_enabled", "dynamic_ranking",
    ]
    choice_space = {
        "fund_type_filter": ["all", "active", "passive"],
        "profit_mode": ["all", "half", "quarter", "step"],
    }

    random.seed(777)
    for i in range(500):
        config = dict(base)
        # 随机选取 5-8 个参数维度来变化
        n_params = random.randint(5, 8)
        selected = random.sample(list(param_space.keys()), min(n_params, len(param_space)))
        for dim in selected:
            lo, hi, typ = param_space[dim]
            if typ == "int":
                val = random.randint(lo, hi)
            else:
                val = round(random.uniform(lo, hi), 3)
            if dim == "take_profit_pct":
                config["no_stop_loss"] = random.choice([True, False])
            config[dim] = val

        # 随机选 2-3 个 bool 参数
        n_bools = random.randint(2, 4)
        for dim in random.sample(bool_space, n_bools):
            config[dim] = random.choice([True, False])

        # 随机选 0-1 个 choice 参数
        for dim in random.sample(list(choice_space.keys()), random.randint(0, 1)):
            config[dim] = random.choice(choice_space[dim])

        # 随机评分权重
        if random.random() < 0.3:
            vals = [random.randint(10, 40) for _ in range(5)]
            total = sum(vals)
            config["weights"] = {dims[j]: round(vals[j] / total * 100) for j in range(5)}

        configs.append({
            "name": f"E_rnd{i:04d}",
            "desc": f"random({n_params}dims)",
            "config": config,
        })

    return configs


# ── F. 散户模拟变体 (200个) ──
def gen_retail_variants():
    """散户友好策略变体。

    核心区别于大佬策略:
    1. monthly_injection: 1000~5000 (月定投)
    2. initial_cash: 3000~10000 (小资金起步)
    3. max_holdings: 3~10 (限仓位防分散)
    4. pyramiding_enabled: True (金字塔补仓替代无限加仓)
    5. kelly_cap: 0.15~0.30 (保守仓位)
    """
    configs = []

    # F1: 月定投金额扫描 (8个)
    for inj in [1000, 1500, 2000, 2500, 3000, 4000, 5000, 8000]:
        config = dict(BASE)
        config.update({
            "monthly_injection": inj,
            "initial_cash": 5000,
            "max_holdings": 5,
            "kelly_cap": 0.25,
            "pyramiding_enabled": True,
            "stop_loss_pct": -15,
            "take_profit_pct": 30,
            "no_stop_loss": False,
            "momentum_sell": 1.5,
            "profit_mode": "half",
        })
        configs.append({
            "name": f"F_inj_{inj}",
            "desc": f"月投{inj}+限5仓+金字塔",
            "config": config,
        })

    # F2: 初始资金扫描 (6个)
    for cash in [1000, 2000, 3000, 5000, 8000, 10000]:
        config = dict(BASE)
        config.update({
            "monthly_injection": 2000,
            "initial_cash": cash,
            "max_holdings": 5,
            "kelly_cap": 0.25,
            "pyramiding_enabled": True,
            "stop_loss_pct": -15,
            "take_profit_pct": 30,
            "no_stop_loss": False,
            "momentum_sell": 1.5,
            "profit_mode": "half",
        })
        configs.append({
            "name": f"F_cash_{cash}",
            "desc": f"初始{cash}+月投2000+限5仓",
            "config": config,
        })

    # F3: 限仓位数扫描 (8个)
    for mh in [3, 4, 5, 6, 7, 8, 10, 15]:
        config = dict(BASE)
        config.update({
            "monthly_injection": 2000,
            "initial_cash": 5000,
            "max_holdings": mh,
            "kelly_cap": 0.25,
            "pyramiding_enabled": True,
            "stop_loss_pct": -15,
            "take_profit_pct": 30,
            "no_stop_loss": False,
            "momentum_sell": 1.5,
            "profit_mode": "half",
        })
        configs.append({
            "name": f"F_maxh_{mh}",
            "desc": f"限{mh}仓+月投2000+金字塔",
            "config": config,
        })

    # F4: kelly_cap扫描 (6个)
    for kc in [0.10, 0.15, 0.20, 0.25, 0.30, 0.35]:
        config = dict(BASE)
        config.update({
            "monthly_injection": 2000,
            "initial_cash": 5000,
            "max_holdings": 5,
            "kelly_cap": kc,
            "pyramiding_enabled": True,
            "stop_loss_pct": -15,
            "take_profit_pct": 30,
            "no_stop_loss": False,
            "momentum_sell": 1.5,
            "profit_mode": "half",
        })
        configs.append({
            "name": f"F_kelly_{kc}",
            "desc": f"kelly={kc}+月投2000+限5仓",
            "config": config,
        })

    # F5: 止损止盈组合 (12个)
    for sl, tp in [(-8, 15), (-8, 20), (-10, 20), (-10, 25), (-12, 25),
                   (-12, 30), (-15, 25), (-15, 30), (-15, 40),
                   (-20, 30), (-20, 40), (-25, 50)]:
        config = dict(BASE)
        config.update({
            "monthly_injection": 2000,
            "initial_cash": 5000,
            "max_holdings": 5,
            "kelly_cap": 0.25,
            "pyramiding_enabled": True,
            "stop_loss_pct": sl,
            "take_profit_pct": tp,
            "no_stop_loss": False,
            "momentum_sell": 1.5,
            "profit_mode": "half",
        })
        configs.append({
            "name": f"F_sl{sl}_tp{tp}",
            "desc": f"止损{sl}%+止盈{tp}%+月投2000",
            "config": config,
        })

    # F6: 散户加权共识变体 (20个)
    for kc in [0.15, 0.20, 0.25, 0.30]:
        for mh in [4, 5, 6, 8]:
            for inj in [2000, 3000]:
                config = dict(BASE)
                config.update({
                    "monthly_injection": inj,
                    "initial_cash": 5000,
                    "max_holdings": mh,
                    "kelly_cap": kc,
                    "pyramiding_enabled": True,
                    "stop_loss_pct": -15,
                    "take_profit_pct": 30,
                    "no_stop_loss": False,
                    "momentum_sell": 1.5,
                    "profit_mode": "step",
                    "use_weighted_consensus": True,
                    "adaptive_consensus": True,
                    "timing_filter": True,
                    "block_overbought": True,
                })
                configs.append({
                    "name": f"F_w_{kc}_{mh}_{inj}",
                    "desc": f"加权共识+kelly={kc}+限{mh}仓+月投{inj}",
                    "config": config,
                })

    # F7: 散户regime自适应 (30个)
    for sl_bull, sl_bear, tp_bull, tp_bear in [
        (-15, -10, 30, 15), (-20, -10, 40, 20), (-20, -15, 30, 15),
        (-25, -15, 40, 20), (-15, -8, 25, 12), (-20, -12, 35, 18),
        (-10, -8, 20, 10), (-25, -20, 50, 25), (-30, -20, 50, 30),
        (-15, -12, 30, 20),
    ]:
        for mh in [5, 6, 8]:
            config = dict(BASE)
            config.update({
                "monthly_injection": 2000,
                "initial_cash": 5000,
                "max_holdings": mh,
                "kelly_cap": 0.25,
                "pyramiding_enabled": True,
                "no_stop_loss": False,
                "momentum_sell": 1.5,
                "profit_mode": "step",
                "regime_specific": True,
                "dynamic_stop_loss": True,
                "stop_loss_pct_bull": sl_bull,
                "stop_loss_pct_neutral": sl_bull + 5,
                "stop_loss_pct_bear": sl_bear,
                "take_profit_pct_bull": tp_bull,
                "take_profit_pct_neutral": tp_bull - 10,
                "take_profit_pct_bear": tp_bear,
                "kelly_cap_bull": 0.30,
                "kelly_cap_neutral": 0.25,
                "kelly_cap_bear": 0.15,
            })
            configs.append({
                "name": f"F_reg_{sl_bull}_{sl_bear}_{tp_bull}_{tp_bear}_{mh}",
                "desc": f"regime+牛止损{sl_bull}/熊{sl_bear}+止盈{tp_bull}/{tp_bear}+限{mh}仓",
                "config": config,
            })

    # F8: 散户随机搜索 (110个) - 确保多样性和覆盖
    random.seed(42)
    retail_param_space = {
        "stop_loss_pct": (-25, -8, "int"),
        "take_profit_pct": (15, 50, "int"),
        "kelly_cap": (0.10, 0.35, "float"),
        "max_holdings": (3, 10, "int"),
        "min_consensus": (1, 4, "int"),
        "cooldown_profit_days": (3, 20, "int"),
        "cooldown_loss_days": (10, 40, "int"),
        "momentum_sell": (0.5, 3.0, "float"),
    }
    retail_choice_space = {
        "fund_type_filter": ["all", "active"],
        "profit_mode": ["half", "quarter", "step"],
    }
    retail_bool_space = [
        "use_weighted_consensus", "adaptive_consensus",
        "timing_filter", "block_overbought",
        "pyramiding_enabled", "regime_specific",
        "dynamic_stop_loss", "dynamic_ranking",
    ]
    for i in range(110):
        config = dict(BASE)
        config.update({
            "monthly_injection": random.choice([1000, 1500, 2000, 2500, 3000]),
            "initial_cash": random.choice([2000, 3000, 5000, 8000]),
            "no_stop_loss": False,
        })
        # 随机 4-6 个数值参数
        n_params = random.randint(4, 6)
        selected = random.sample(list(retail_param_space.keys()), min(n_params, len(retail_param_space)))
        for dim in selected:
            lo, hi, typ = retail_param_space[dim]
            if typ == "int":
                config[dim] = random.randint(lo, hi)
            else:
                config[dim] = round(random.uniform(lo, hi), 3)
        # 随机 2-3 个 bool 参数
        for dim in random.sample(retail_bool_space, random.randint(2, 3)):
            config[dim] = True
        # 随机 0-1 个 choice 参数
        for dim in random.sample(list(retail_choice_space.keys()), random.randint(0, 1)):
            config[dim] = random.choice(retail_choice_space[dim])
        configs.append({
            "name": f"F_rnd{i:03d}",
            "desc": f"散户随机({n_params}params)",
            "config": config,
        })

    return configs


def main():
    all_configs = []
    all_configs.extend(gen_weight_variants())
    all_configs.extend(gen_single_param_sweep())
    all_configs.extend(gen_two_param_combos())
    all_configs.extend(gen_three_param_combos())
    all_configs.extend(gen_random_search())
    all_configs.extend(gen_retail_variants())

    print(f"总策略数: {len(all_configs)}")

    # 保存为JSON (避免 true/false Python 语法问题)
    out = Path(__file__).resolve().parent / "mega_sweep_configs.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(all_configs, f, ensure_ascii=False, indent=2)
    print(f"保存到 {out}")


if __name__ == "__main__":
    main()
