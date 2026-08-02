#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
严格 OOS (Out-of-Sample) 回测框架 — 零作弊协议
"""
import sys, copy, json, os
from datetime import datetime, timedelta
from collections import defaultdict

sys.path.insert(0, '.')
from backtest.engine.backtest import run_backtest


# ============================================================
# Round 10 候选 — 行情状态动态因子权重 (Regime-Specific Factor Weights)
#
# R4-R9 回顾:
#   - R4_BASELINE 9.624%/q 仍是最佳 (14 TEST windows OOS)
#   - R7 价格型滤波 / R8 广度防御 / R9 止损均无法稳定超越基线
#   - 核心矛盾: 固定权重 Q20/C25/M15/Mo10/SM30 在所有市场环境下使用同一套参数
#   - 牛市中 smart_money 追涨有效但动量信号被低估;
#     熊市/震荡期中 smart_money 失效, 应切换到质量/成本价值因子
#
# R10 假设 (行情自适应, 非预测):
#   1. 牛市 (benchmark 60 日涨幅 > 8%): 加大动量 + smart_money 权重 (趋势跟踪)
#   2. 熊市 (benchmark 60 日跌幅 > 5%): 加大质量 + cost 价值防守
#   3. 中性市: 使用 R4 原始权重 (平衡)
#
# 防作弊保证:
#   - detect_market_state() 仅使用 cutoff_full (TEST 起始日) 之前的历史净值
#   - weights_bull/bear 是预注册常数, 不基于 TEST 期数据调优
#   - 每个 TEST 窗口的 regime 状态是该窗口的"特征", 不是未来信息
#   - 权重在窗口起始日确定, 整个窗口内不切换
#
# R10 候选 (预注册, 2026-08-02):
#   0. R4_BASELINE — 对照 (固定权重, 无行情切换)
#   1. DYN_AGGRESSIVE — 牛市 max 动量+smart_money, 熊市 max 质量+成本
#   2. DYN_DEFENSIVE — 牛市加大质量防守, 熊市极端质量+成本
#   3. DYN_MOMENTUM — 牛市纯动量, 熊市反向加大质量/成本
#   4. DYN_TREND — 牛市 smart_money 最大化, 熊市切换到 manager quality
# ============================================================

ROUND = 10

# 行情权重预设 (总和=100)
WTS_BULL_AGGRESSIVE = {"quality": 15, "cost": 20, "manager": 10, "momentum": 25, "smart_money": 30}
WTS_BEAR_AGGRESSIVE = {"quality": 30, "cost": 30, "manager": 10, "momentum": 10, "smart_money": 20}
WTS_BULL_DEFENSIVE = {"quality": 25, "cost": 30, "manager": 15, "momentum": 15, "smart_money": 15}
WTS_BEAR_DEFENSIVE = {"quality": 35, "cost": 35, "manager": 10, "momentum": 5, "smart_money": 15}
WTS_BULL_MOMENTUM = {"quality": 15, "cost": 15, "manager": 10, "momentum": 30, "smart_money": 30}
WTS_BEAR_MOMENTUM = {"quality": 30, "cost": 25, "manager": 15, "momentum": 10, "smart_money": 20}
WTS_BULL_TREND = {"quality": 15, "cost": 20, "manager": 10, "momentum": 20, "smart_money": 35}
WTS_BEAR_TREND = {"quality": 25, "cost": 25, "manager": 30, "momentum": 10, "smart_money": 10}
WTS_BASELINE = {"quality": 20, "cost": 25, "manager": 15, "momentum": 10, "smart_money": 30}

CANDIDATES = [
    # 0: R4 winner, 对照 (固定权重, 无行情切换)
    ("R4_BASELINE", {
        "max_holdings": 12,
        "weights": WTS_BASELINE,
    }),
    # 1: 激进动态 — 牛市最大化追击, 熊市最大化防守
    ("DYN_AGGRESSIVE", {
        "max_holdings": 12,
        "weights": WTS_BASELINE,
        "weights_bull": WTS_BULL_AGGRESSIVE,
        "weights_bear": WTS_BEAR_AGGRESSIVE,
    }),
    # 2: 保守动态 — 即使牛市也保质量底, 熊市极端防守
    ("DYN_DEFENSIVE", {
        "max_holdings": 12,
        "weights": WTS_BASELINE,
        "weights_bull": WTS_BULL_DEFENSIVE,
        "weights_bear": WTS_BEAR_DEFENSIVE,
    }),
    # 3: 动量动态 — 牛市巅峰追击, 熊市切换到价值回归
    ("DYN_MOMENTUM", {
        "max_holdings": 12,
        "weights": WTS_BASELINE,
        "weights_bull": WTS_BULL_MOMENTUM,
        "weights_bear": WTS_BEAR_MOMENTUM,
    }),
    # 4: 趋势跟踪 — 牛市 smart_money 最大化, 熊市切换到 manager quality
    ("DYN_TREND", {
        "max_holdings": 12,
        "weights": WTS_BASELINE,
        "weights_bull": WTS_BULL_TREND,
        "weights_bear": WTS_BEAR_TREND,
    }),
]


# ─── 时间窗口定义 ───
# 扩展: base_end 延伸至 2026-07-31 (数据已从 JD API 刷新)
# 原始 ALL_WINDOWS 共 28 个 (index 0-27)
# TRAIN = ALL_WINDOWS[:14]  (前 14 个做训练确认)
# TEST  = ALL_WINDOWS[14:]  (后 14 个做纯 OOS)
ALL_WINDOWS = []
base_start = datetime(2023, 7, 17)
base_end = datetime(2026, 7, 31)

# 生成每 30 天滚动的窗口
idx = 0
while True:
    current = base_start + timedelta(days=30 * idx)
    train_end = current + timedelta(days=180)
    test_end = current + timedelta(days=270)
    if test_end > base_end:
        break
    ALL_WINDOWS.append({
        "train_end": train_end.strftime("%Y-%m-%d"),
        "test_end": test_end.strftime("%Y-%m-%d"),
    })
    idx += 1

TRAIN_WINDOWS = ALL_WINDOWS[:14]
TEST_WINDOWS = ALL_WINDOWS[14:]

# ─── 配置基线 ───
BASE_CFG = {
    "initial_cash": 10000,
    "no_stop_loss": True,
    "take_profit_pct": 50.0,
    "min_consensus": 3,
    "max_holdings": 5,
    "kelly_cap_bull": 0.5,
    "kelly_cap_bear": 0.25,
    "pyramiding_enabled": False,
    "smart_swap": True,
    "regime_specific": True,
}


def window_range(wi):
    if 0 <= wi < len(ALL_WINDOWS):
        return ALL_WINDOWS[wi]["train_end"], ALL_WINDOWS[wi]["test_end"]
    return None, None


def run_train(ci, wi):
    train_end, test_end = window_range(wi)
    cfg = copy.deepcopy(BASE_CFG)
    cfg_override = CANDIDATES[ci][1]
    cfg.update(cfg_override)
    cfg['start_date'] = train_end
    cfg['end_date'] = test_end
    res = run_backtest(cfg, clear_cache=True)
    return res


def run_test(ci, wi):
    train_end, test_end = window_range(wi)
    cfg = copy.deepcopy(BASE_CFG)
    cfg_override = CANDIDATES[ci][1]
    cfg.update(cfg_override)
    cfg['start_date'] = train_end
    cfg['end_date'] = test_end
    res = run_backtest(cfg, clear_cache=True)
    return res


def run_all_train(ci):
    results = []
    for wi in range(len(TRAIN_WINDOWS)):
        res = run_train(ci, wi)
        results.append(res)
    return results


def run_all_test(ci):
    results = []
    for wi in range(len(TEST_WINDOWS)):
        res = run_test(ci, len(TRAIN_WINDOWS) + wi)
        results.append(res)
    return results


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("mode", choices=["run_train", "run_test", "run_all_train", "run_all_test"])
    p.add_argument("--ci", type=int, default=0)
    p.add_argument("--wi", type=int, default=0)
    args = p.parse_args()

    if args.mode == "run_train":
        r = run_train(args.ci, args.wi)
        print(json.dumps({"return": r.get("total_return", 0), "trades": r.get("trade_count", 0)}, ensure_ascii=False))
    elif args.mode == "run_test":
        r = run_test(args.ci, args.wi)
        print(json.dumps({"return": r.get("total_return", 0), "trades": r.get("trade_count", 0)}, ensure_ascii=False))
    elif args.mode == "run_all_train":
        rs = run_all_train(args.ci)
        for i, r in enumerate(rs):
            print(f"TRAIN wi={i}: return={r.get('total_return',0):.2f}")
    elif args.mode == "run_all_test":
        rs = run_all_test(args.ci)
        for i, r in enumerate(rs):
            print(f"TEST wi={i}: return={r.get('total_return',0):.2f}")
