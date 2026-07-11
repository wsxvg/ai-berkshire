#!/usr/bin/env python3
"""Fund rules engine — extracted from SKILL.md quantitative rules.
LLM 调用此模块获取结构化信号，再结合上下文做最终判断。

Usage:
    python tools/fund_rules.py --analyze       # 输出 JSON 供 LLM 读取
    python tools/fund_rules.py --test           # 自检
"""
import json, math
from pathlib import Path
from datetime import date
from collections import defaultdict

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
CACHE_DIR = DATA_DIR / "fund_cache"


def load_json(path, default=None):
    p = Path(path)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else (default or {})


# ═══════════════════════════════════════════════════════════════
# 加权清仓计算
# ═══════════════════════════════════════════════════════════════

def weighted_clear(fund_code: str, holdings_diff: dict = None) -> dict:
    """大佬集体清仓加权计算（fund-sell.md 步骤 A2 🔴）。

    权重规则：
      持有 > 2年 → 2.0
      6个月 ~ 2年 → 1.0
      < 6个月 → 0.5

    返回：
      { "weighted_clear": float, "weighted_reduce": float,
        "clear_users": [...], "verdict": str }
    """
    if holdings_diff is None:
        holdings_diff = load_json(DATA_DIR / "holdings_diff_cache.json")
    fd = holdings_diff.get("funds", {}).get(fund_code, {})
    clear_total = fd.get("clear_total", 0)
    reduce_pct_total = fd.get("reduce_30pct_total", 0)
    weighted = fd.get("weighted_clear", clear_total)
    verdict = "pass"
    if weighted >= 3:
        verdict = "red_clear"
    elif weighted >= 2:
        verdict = "yellow_watch"
    return {
        "weighted_clear": weighted,
        "weighted_reduce": reduce_pct_total,
        "verdict": verdict,
        "details": fd.get("clear_details", []),
        "conflict": fd.get("conflict", {}),
    }


# ═══════════════════════════════════════════════════════════════
# 买入护盾检测
# ═══════════════════════════════════════════════════════════════

def buy_shield(fund_code: str, my_holdings: list = None,
               trading_cache: dict = None) -> dict:
    """检测大佬买入信号是否保护了当前持仓（fund-sell.md 大佬交易抵消逻辑）。

    返回：
      { "shield_active": bool, "strength": str,
        "buy_count": int, "reason": str }
    """
    if trading_cache is None:
        trading_cache = load_json(DATA_DIR / "trading_records_cache.json")
    if my_holdings is None:
        status = load_json(DATA_DIR / "auto" / "status.json")
        my_holdings = status.get("my_holdings", [])

    # 我是否持有这只基金
    my_codes = {h["code"] for h in my_holdings if h.get("code")}
    if fund_code not in my_codes:
        return {"shield_active": False, "strength": "none", "buy_count": 0, "reason": "未持仓"}

    # 从 trading_records 查找买入信号
    for fname, fd in trading_cache.get("funds", {}).items():
        code = fd.get("fund_code") or fd.get("code", "")
        if code != fund_code:
            continue
        bc = fd.get("buy_count", 0)
        sc = fd.get("sell_count", 0)
        if bc >= 2:
            return {"shield_active": True, "strength": "strong",
                    "buy_count": bc, "sell_count": sc,
                    "reason": f"大佬{bc}人买入，获得买入护盾"}
        if bc == 1:
            return {"shield_active": True, "strength": "weak",
                    "buy_count": bc, "sell_count": sc,
                    "reason": "弱护盾，减仓比例减半"}
        return {"shield_active": False, "strength": "none",
                "buy_count": bc, "sell_count": sc, "reason": "无人买入"}
    return {"shield_active": False, "strength": "none", "buy_count": 0, "reason": "无交易记录"}


# ═══════════════════════════════════════════════════════════════
# 止盈阈值表
# ═══════════════════════════════════════════════════════════════

def take_profit_level(fund_type: str, hold_days: int = None) -> dict:
    """按基金类型获取止盈/止损阈值（fund-sell.md 步骤 C 🟢）。

    基金类型: active | index_enhanced | passive_index | qdii_active | qdii_passive

    返回：
      { "target_profit": float, "stop_loss": float or None,
        "suggested_reduce": str }
    """
    table = {
        "active":        {"profit": 50, "stop_loss": -20},
        "index_enhanced": {"profit": 30, "stop_loss": -15},
        "passive_index": {"profit": 20, "stop_loss": None},
        "qdii_active":   {"profit": 50, "stop_loss": -25},
        "qdii_passive":  {"profit": 30, "stop_loss": None},
    }
    ft = table.get(fund_type, table["active"])
    return {
        "target_profit_pct": ft["profit"],
        "stop_loss_pct": ft["stop_loss"],
        "take_profit_action": f"收益>{ft['profit']}%止盈1/2" if ft["profit"] else "不设止盈",
    }


# ═══════════════════════════════════════════════════════════════
# 调仓成本计算
# ═══════════════════════════════════════════════════════════════

def swap_cost(fund_code: str, expected_excess_return: float = 0.1) -> dict:
    """计算调仓成本是否合理（fund-sell.md 步骤 D 🔵）。

    调仓成本 = 赎回费 + 申购费
    如果 成本 > 预期超额收益 × 30% → 不调仓

    返回：
      { "swap_cost_pct": float, "excess_return": float,
        "threshold": float, "should_swap": bool }
    """
    rules = load_json(CACHE_DIR / f"trade_rules_{fund_code}.json")
    if not rules:
        return {"swap_cost_pct": 0, "excess_return": expected_excess_return,
                "threshold": 0, "should_swap": False, "reason": "无费率数据"}

    purchase_fee = float(rules.get("purchase_fee", 0))
    redeem_fees = rules.get("redeem_fees", [])
    # 取持有 ≥ 365 天的赎回费
    redeem_fee = 0
    for rf in redeem_fees:
        if isinstance(rf, dict):
            interval = str(rf.get("interval", ""))
            if "365" in interval or "730" in interval:
                redeem_fee = float(rf.get("rate", 0))
                break
    cost = purchase_fee + redeem_fee
    threshold = expected_excess_return * 0.3 * 100  # 转成百分比
    return {
        "swap_cost_pct": round(cost, 2),
        "expected_excess": expected_excess_return,
        "threshold_pct": round(threshold, 2),
        "should_swap": cost <= threshold,
        "reason": f"调仓成本{cost:.2f}% ≤ {threshold:.2f}%→可调仓" if cost <= threshold else f"成本{cost:.2f}% > {threshold:.2f}%→不调仓",
    }


# ═══════════════════════════════════════════════════════════════
# 统一分析入口
# ═══════════════════════════════════════════════════════════════

def analyze_all(fund_code: str = None, fund_type: str = "active") -> dict:
    """对所有规则做综合分析。供 LLM 读取 JSON 输出。"""
    result = {}

    # 加权清仓
    wc = weighted_clear(fund_code) if fund_code else {"weighted_clear": 0, "verdict": "no_data"}
    result["weighted_clear"] = wc

    # 买入护盾
    bs = buy_shield(fund_code) if fund_code else {"shield_active": False}
    result["buy_shield"] = bs

    # 止盈阈值
    tp = take_profit_level(fund_type)
    result["take_profit"] = tp

    # 调仓成本
    sc = swap_cost(fund_code) if fund_code else {"should_swap": False}
    result["swap_cost"] = sc

    # 综合建议
    suggestions = []
    if wc.get("verdict") == "red_clear":
        if bs.get("shield_active"):
            suggestions.append("⚠️ 清仓信号但买入护盾激活→分歧观察")
        else:
            suggestions.append("🔴 硬性清仓→执行")
    elif wc.get("verdict") == "yellow_watch":
        if bs.get("shield_active"):
            suggestions.append("🟡 减仓信号但买入护盾激活→跳过")
        else:
            suggestions.append("🟡 减仓观察")
    result["suggestions"] = suggestions
    return result


# ═══════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Fund Rules Engine")
    parser.add_argument("--analyze", type=str, help="分析指定基金代码")
    parser.add_argument("--fund-type", default="active",
                        help="基金类型: active/index_enhanced/passive_index/qdii_active/qdii_passive")
    parser.add_argument("--output", type=str, help="输出到文件")
    args = parser.parse_args()

    if args.analyze:
        result = analyze_all(args.analyze, args.fund_type)
        text = json.dumps(result, ensure_ascii=False, indent=2)
        if args.output:
            Path(args.output).write_text(text, encoding="utf-8")
            print(f"Saved to {args.output}")
        else:
            print(text)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()