#!/usr/bin/env python3
"""
动态大佬评分引擎 — 自动识别好大佬/差大佬

用法：
  python tools/big_player_ranker.py --history data/trading_history_fixed.json

输出：
  - 每位大佬的当前分数和权重
  - 建议排除的UID列表
"""

import json, re, sys
from pathlib import Path
from collections import defaultdict
from datetime import datetime, timedelta

# ── 配置 ──
LOOKBACK_DAYS = 365       # 观察窗口：看过去365天（初始化用）
FWD_RETURN_DAYS = 30     # 买入后看30天收益
MIN_BUYS = 10            # 最少需要10笔买入才算分
WEIGHT_THRESHOLDS = [
    (10.0, 2.0),   # 平均30天收益 >= 10% → 权重2.0
    (7.0,  1.5),   # >= 7% → 1.5
    (4.0,  1.0),   # >= 4% → 1.0
    (2.0,  0.5),   # >= 2% → 0.5
    (-999, 0.0),   # < 2% → 排除(权重0)
]

def calculate_scores(records, charts, name_to_code, cutoff_date=None):
    """
    计算每位大佬的评分。

    records: trading_history_fixed.json
    charts: fund_charts.json
    name_to_code: {基金名: 代码}
    cutoff_date: 只计算截止到该日期的数据（回测用）
    """
    from collections import defaultdict

    def _float(v):
        try: return float(v)
        except: return 0.0

    # 确保是datetime
    if cutoff_date and isinstance(cutoff_date, str):
        cutoff_dt = datetime.strptime(cutoff_date[:10], '%Y-%m-%d') if len(cutoff_date) >= 10 else None
    else:
        cutoff_dt = None

    # 收集每位大佬的买入及后续表现
    player_data = defaultdict(lambda: {"buys": 0, "returns": [], "funds": set()})

    for r in records:
        act = r.get("action", "")
        if "买入" not in act:
            continue

        # 日期过滤
        date = r.get("_full_date", "")
        if not date or len(date) < 10:
            continue
        record_dt = datetime.strptime(date[:10], '%Y-%m-%d')

        # 如果设定了截止日期，只算截止前的数据
        if cutoff_dt and record_dt > cutoff_dt:
            continue
        # 只算LOOKBACK_DAYS内的
        if cutoff_dt and (cutoff_dt - record_dt).days > LOOKBACK_DAYS:
            continue
        # 如果没有cutoff_date，用当前时间
        if not cutoff_dt and (datetime.now() - record_dt).days > LOOKBACK_DAYS:
            continue

        uid = r.get("_uid", "")
        user = r.get("_user", "")
        fn = r.get("fund_name", "")
        code = name_to_code.get(fn, "")
        if not uid or not code:
            continue

        # 找买入后FWD_RETURN_DA天的收益
        pts = charts.get(code, [])
        if not pts:
            continue

        for i, p in enumerate(pts):
            if p.get("xAxis", "") >= date:
                if i + FWD_RETURN_DAYS >= len(pts):
                    break
                bv = _float(pts[i].get("yAxis", 0))
                sv = _float(pts[i + FWD_RETURN_DAYS].get("yAxis", 0))
                ret = sv - bv
                player_data[uid]["returns"].append(ret)
                player_data[uid]["buys"] += 1
                player_data[uid]["funds"].add(code)
                player_data[uid]["user"] = user
                break

    # 计算最终分数和权重
    scores = {}
    for uid, data in player_data.items():
        if len(data["returns"]) < MIN_BUYS:
            continue
        avg_ret = sum(data["returns"]) / len(data["returns"])
        win_rate = sum(1 for r in data["returns"] if r > 0) / len(data["returns"]) * 100

        # 计算权重
        weight = 0.0
        for threshold, w in WEIGHT_THRESHOLDS:
            if avg_ret >= threshold:
                weight = w
                break

        scores[uid] = {
            "uid": uid,
            "user": data["user"],
            "avg_30d_return": round(avg_ret, 2),
            "win_rate": round(win_rate, 1),
            "total_buys": data["buys"],
            "unique_funds": len(data["funds"]),
            "weight": weight,
            "status": "active" if weight > 0 else "excluded",
        }

    return scores


def get_player_weights(scores):
    """从分数生成player_weights字典（供回测引擎使用）"""
    return {uid: s["weight"] for uid, s in scores.items() if s["weight"] > 0}


def get_excluded_uids(scores):
    """获取需要排除的UID列表（权重为0的）"""
    return [uid for uid, s in scores.items() if s["weight"] == 0]


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="动态大佬评分引擎")
    parser.add_argument("--history", default="data/trading_history_fixed.json", help="历史交易数据")
    parser.add_argument("--charts", default="backtest/data/fund_charts.json", help="基金净值数据")
    parser.add_argument("--cutoff", default=None, help="截止日期（YYYY-MM-DD），默认今天")
    parser.add_argument("--output", default=None, help="输出文件路径")
    args = parser.parse_args()

    # 加载数据
    records = json.load(open(args.history, "r", encoding="utf-8"))
    charts = json.load(open(args.charts, "r", encoding="utf-8"))
    snap = json.load(open("data/holdings_snapshot.json", "r", encoding="utf-8"))

    # 构建基金名→代码映射
    name_to_code = {}
    for user, funds in snap.get("holdings", {}).items():
        for f in funds if isinstance(funds, list) else []:
            if isinstance(f, dict) and f.get("code") and f.get("name"):
                name_to_code[f["name"]] = f["code"]

    # 计算分数
    scores = calculate_scores(records, charts, name_to_code, args.cutoff)

    # 输出
    print(f"\n动态大佬评分 ({'全部历史' if not args.cutoff else '截至'+args.cutoff})")
    print(f"观察窗口: {LOOKBACK_DAYS}天, 最少买入: {MIN_BUYS}次")
    print(f"{'UID':>12s} {'名字':>10s} {'30天收益':>10s} {'胜率':>8s} {'买入':>6s} {'基金':>6s} {'权重':>6s} {'状态':>10s}")
    print("-" * 72)

    active = []
    excluded = []
    for uid in sorted(scores, key=lambda u: scores[u]["avg_30d_return"], reverse=True):
        s = scores[uid]
        line = f"{uid:>12s} {s['user'][:10]:>10s} {s['avg_30d_return']:>+9.2f}% {s['win_rate']:>7.1f}% "
        line += f"{s['total_buys']:>5d}  {s['unique_funds']:>4d}  {s['weight']:>4.1f}  {s['status']:>10s}"
        print(line)
        if s["weight"] > 0:
            active.append(uid)
        else:
            excluded.append(uid)

    print(f"\n活跃大佬: {len(active)}人")
    print(f"排除大佬: {len(excluded)}人 (权重为0)")
    print(f"\nplayer_weights = {json.dumps(get_player_weights(scores), indent=2)}")
    print(f"\nexclude_uids = {json.dumps(get_excluded_uids(scores))}")

    if args.output:
        json.dump(scores, open(args.output, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print(f"\n保存到 {args.output}")
