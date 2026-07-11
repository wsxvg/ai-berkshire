# -*- coding: utf-8 -*-
"""月度预算跟踪器 — 自动从持仓检测当月买入"""
import json
from pathlib import Path
from datetime import date

_PATH = Path(__file__).resolve().parent.parent / "data" / "auto" / "monthly_budget.json"

def _key():
    t = date.today()
    return f"{t.year}-{t.month:02d}"

def _amount(h):
    """从持仓项提取金额"""
    return float(str(h.get("amount", 0) or h.get("market_value", 0) or h.get("cost_value", 0) or 0).replace(",", ""))

def load():
    """加载当月预算，自动从持仓数据估算已用金额"""
    today = date.today()
    key = _key()

    if _PATH.exists():
        try:
            data = json.loads(_PATH.read_text("utf-8"))
            if data.get("month") == key:
                return data
        except: pass

    data = {"month": key, "budget": 5000, "spent": 0, "baseline": {}}
    save(data)
    return data

def save(data):
    _PATH.parent.mkdir(parents=True, exist_ok=True)
    _PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def auto_detect_spent(current_holdings):
    """从当前持仓自动计算本月已用金额。

    原理：对比月初基线，新增基金+加仓金额 = 本月花费。
    月初基线在每月第一次调用时自动保存。
    """
    data = load()
    today = date.today()

    # 月初第一天重置基线
    # 旧数据兼容：没有baseline就初始化
    baseline = data.get("baseline", {})

    if today.day <= 3 and not baseline:
        data["spent"] = 0
        data["baseline"] = {h.get("code", ""): _amount(h) for h in (current_holdings or [])}
        save(data)
        return data

    # 用持仓估算已用金额
    if current_holdings and baseline:
        now_vals = {h.get("code", ""): _amount(h) for h in current_holdings}
        total_spent = 0

        # 新增基金 = 全款计入
        for code, amt in now_vals.items():
            if code not in baseline:
                total_spent += amt

        # 已有基金增值部分 = 差值
        for code, base_amt in baseline.items():
            now_amt = now_vals.get(code, 0)
            diff = now_amt - base_amt
            if diff > base_amt * 0.05:  # 涨幅>5%算加仓
                # 减去自然涨幅（按大盘平均估算），剩余算加仓
                natural_growth = base_amt * 0.03
                extra = min(diff - natural_growth, diff * 0.8)
                if extra > 100:
                    total_spent += extra

        data["spent"] = min(int(total_spent), data["budget"])
        save(data)

    return data

def get_remaining(current_holdings=None):
    """获取本月剩余资金"""
    data = auto_detect_spent(current_holdings) if current_holdings else load()
    return max(0, data["budget"] - data["spent"])

def mark_spent(amount):
    """手动记录本月已用资金"""
    data = load()
    data["spent"] += amount
    save(data)

def reset(budget=None):
    """手动重置"""
    data = load()
    if budget: data["budget"] = budget
    data["spent"] = 0
    data["baseline"] = {}
    save(data)