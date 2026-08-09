#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
R23 信号构建 v7 — 修复未来数据泄露 + 双线路 top3 + 逐基金 T+N
================================================================
修复致命 bug (R20-R22): 旧版用全期期末持仓算 top3 → 未来数据泄露。
本版修复三件事:
  1. top3 逐日滚动, 只基于"截至当日"持仓 (不含未来交易)。
  2. 逐基金 T+N 确认规则: 买入/卖出份额在 T+N 日才计入持仓,
     消除"信号日使用未确认持仓"的问题 (QDII T+2/T+4, 普通 T+1)。
  3. 双线路: A=持仓金额top3, B=持仓收益率top3。

T+N 来源: data/fund_cache/trade_rules_{code}.json 的 buy_date/confirm_date
  自然日差推断 (T+1:328, T+2:84, T+4:16, T+5:1; 缺失默认 T+1, QDII码段默认 T+2)。
交易日期为自然连续日(含周末), 故 T+N 自然日 = 外循环推进 N 天。

效率: 逐日维护每个玩家的 top3 集合(跨日缓存) + 每基金持仓者倒排索引。
输出: data/smart_money_signals_amount.json / smart_money_signals_ret.json
================================================================
"""
import json, sys, os, gzip, glob
from collections import defaultdict
from bisect import bisect_right

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
V5 = os.path.join(ROOT, "backtest", "data", "trading_by_date_real414_v7.json.gz")
CHARTS = os.path.join(ROOT, "backtest", "data", "fund_charts.json.gz")
RULES_GLOB = os.path.join(ROOT, "data", "fund_cache", "trade_rules_*.json")


# ═══════════════════════════════════════════════════════════════
# T+N 规则加载
# ═══════════════════════════════════════════════════════════════

def _parse_mmdd(s):
    s = s.replace(" 15:00前", "").replace("前", "").strip()
    try:
        mm, dd = s.split("-")
        return int(mm), int(dd)
    except Exception:
        return None


def _confirm_diff_n(buy_date, confirm_date):
    """从 buy_date/confirm_date 推断 T+N 的自然日差 N。"""
    try:
        import datetime
        b = _parse_mmdd(buy_date)
        c = _parse_mmdd(confirm_date)
        if not b or not c:
            return None
        d1 = datetime.date(2000, b[0], b[1])
        d2 = datetime.date(2000, c[0], c[1])
        diff = (d2 - d1).days
        return diff if diff >= 0 else None
    except Exception:
        return None


def _is_qdii(code):
    """QDII 基金码段: 一般以 0/1 开头 + 部分海外码。粗略按 486/539/968/001065 等。"""
    qdii_prefixes = ("486", "539", "968", "001065", "050015", "000834", "006479", "005698")
    return code.startswith(qdii_prefixes) if not code[:1].isdigit() else code.startswith(qdii_prefixes)


def load_tn_rules():
    """返回 {fund_code: {"buy_N": int|None, "redeem_N": int|None}}。
    数据来自接口抓取的 tn_by_fund.json (getFundTradeRulesPageInfo 全字段)。
    完全缺失时才回退: QDII→2, 否则→1。
    """
    tn_file = os.path.join(ROOT, "data", "tn_by_fund.json")
    rules = {}
    if os.path.exists(tn_file):
        try:
            raw = json.load(open(tn_file, encoding="utf-8"))
            for code, d in raw.items():
                rules[code] = {"buy_N": d.get("buy_N"), "redeem_N": d.get("redeem_N")}
        except Exception as e:
            print(f"WARN tn_by_fund.json 解析失败: {e}", flush=True)
    print(f"T+N 规则加载: {len(rules)} 只基金 (来自接口 tn_by_fund.json)", flush=True)
    return rules


def tn_for(rules, code, side="buy"):
    """side=buy 返回买入确认延迟N, side=redeem 返回赎回确认延迟N。
    缺失回退: QDII→2, 否则→1。"""
    r = rules.get(code)
    if r:
        n = r.get("buy_N" if side == "buy" else "redeem_N")
        if n is not None:
            return n
    return 2 if _is_qdii(code) else 1


# ═══════════════════════════════════════════════════════════════
# 数据加载
# ═══════════════════════════════════════════════════════════════

def parse_amount(s):
    if isinstance(s, (int, float)):
        return float(s)
    s = str(s).replace("元", "").replace(",", "").strip()
    try:
        return float(s)
    except ValueError:
        return 0


def load_tbd():
    with gzip.open(V5, "rt", encoding="utf-8") as f:
        return json.load(f)


def load_charts():
    with gzip.open(CHARTS, "rt", encoding="utf-8") as f:
        charts = json.load(f)
    nav_arr = {}
    for code, pts in charts.items():
        arr = [(p["xAxis"], float(p["yAxis"])) for p in pts if float(p.get("yAxis", 0)) > 0]
        if arr:
            nav_arr[code] = arr
    return nav_arr


def nav_on(arr, date):
    ds = [d for d, _ in arr]
    idx = bisect_right(ds, date)
    if idx == 0:
        return None
    return arr[idx - 1][1]


# ═══════════════════════════════════════════════════════════════
# top3 计算 (逐日)
# ═══════════════════════════════════════════════════════════════

def compute_top3(pos, pid, nav_arr, date, mode):
    """计算某玩家截至 date 的 top3 持仓集合 (只含已确认份额)。"""
    holdings = pos[pid]
    items = []
    for fc, h in holdings.items():
        if h["amount"] <= 0:
            continue
        if mode == "amount":
            key = (h["amount"], fc)
        else:
            ret = -1e18
            if h["shares"] > 0 and h["amount"] > 0:
                cost_nav = h["amount"] / h["shares"]
                nav_cur = nav_on(nav_arr.get(fc, []), date)
                if cost_nav > 0 and nav_cur:
                    ret = nav_cur / cost_nav - 1.0
            key = (ret, fc)
        items.append(key)
    items.sort(reverse=True)
    return {fc for _, fc in items[:3]}


# ═══════════════════════════════════════════════════════════════
# 信号构建
# ═══════════════════════════════════════════════════════════════

def build_signals(tbd, nav_arr, tn_rules, mode):
    dates = sorted(tbd.keys())
    date_index = {d: i for i, d in enumerate(dates)}
    print(f"构建线路 {mode} ...", flush=True)

    # pos[pid][fcode] = {"amount": 已确认累计金额, "shares": 已确认份额}
    pos = defaultdict(lambda: defaultdict(lambda: {"amount": 0.0, "shares": 0.0}))
    # pending[pid][fcode] = 待生效金额列表 [(confirm_day_index, signed_amount)]
    #   买入为正金额, 卖出为负金额; 确认日用当日净值折算份额。
    pending = defaultdict(lambda: defaultdict(list))
    # holders[fcode] = set(pid) 已确认且金额>0的持仓者 (倒排索引)
    holders = defaultdict(set)
    top3_cached = {}   # pid -> set(fcode)  截至上一交易日的 top3
    touched_players = set()
    signals = {}

    for day_i, date in enumerate(dates):
        signals[date] = {}
        day_funds = defaultdict(lambda: {"buy": set(), "sell": set()})

        # ── 0. 当日到期的待确认订单 → 计入持仓 (用确认日净值折算份额) ──
        for pid, fund_q in list(pending.items()):
            for fcode, qlist in list(fund_q.items()):
                still = []
                nav_conf = nav_on(nav_arr.get(fcode, []), date)
                for (due_i, amt) in qlist:
                    if due_i <= day_i:
                        h = pos[pid][fcode]
                        h["amount"] += amt
                        if nav_conf and nav_conf > 0:
                            h["shares"] += amt / nav_conf
                        if h["amount"] > 0:
                            holders[fcode].add(pid)
                        else:
                            holders[fcode].discard(pid)
                        touched_players.add(pid)
                    else:
                        still.append((due_i, amt))
                if still:
                    fund_q[fcode] = still
                else:
                    del fund_q[fcode]
            if not fund_q:
                del pending[pid]

        # ── 1. 当天新交易 → 排队待确认 (按该基金 T+N) ──
        for rec in tbd[date]:
            pid = rec.get("_uid")
            fcode = rec.get("fund_code", "")
            if not pid or not fcode:
                continue
            action = rec.get("action", "")
            amt = parse_amount(rec.get("amount", "0"))
            if "买入" in action or "申购" in action:
                n = tn_for(tn_rules, fcode, "buy")       # 买入确认延迟 buy_N
                pending[pid][fcode].append((day_i + n, amt))
                day_funds[fcode]["buy"].add(pid)
                touched_players.add(pid)
            elif "卖出" in action or "赎回" in action:
                n = tn_for(tn_rules, fcode, "redeem")    # 赎回确认延迟 redeem_N
                pending[pid][fcode].append((day_i + n, -amt))
                day_funds[fcode]["sell"].add(pid)
                touched_players.add(pid)

        # ── 2. 重算被触达玩家的 top3 (持仓可能因确认/卖出改变) ──
        for pid in touched_players:
            top3_cached[pid] = compute_top3(pos, pid, nav_arr, date, mode)

        # ── 3. 生成信号 (只用已确认持仓的 top3) ──
        for fcode, stats in day_funds.items():
            buy_pids = stats["buy"]
            sell_pids = stats["sell"]
            net_buy = len(buy_pids) - len(sell_pids)

            hold_count = len(holders[fcode])

            topgain_hold = 0
            for pid in holders[fcode]:
                top3 = top3_cached.get(pid)
                if top3 is not None and fcode in top3:
                    topgain_hold += 1

            # 回调
            callback_pct = 0.0
            arr = nav_arr.get(fcode, [])
            ds = [d for d, _ in arr]
            idx = bisect_right(ds, date)
            if idx > 0 and idx < len(arr):
                prev_nav = arr[idx - 1][1]
                cur_nav = arr[idx][1]
                if prev_nav and prev_nav > 0:
                    callback_pct = (cur_nav / prev_nav - 1) * 100

            if topgain_hold >= 1 and net_buy >= 0:
                signals[date][fcode] = {
                    "net_buy": net_buy,
                    "hold_count": hold_count,
                    "topgain_hold": topgain_hold,
                    "callback_pct": round(callback_pct, 2),
                }

        if day_i % 200 == 0:
            print(f"  {date}: {len(signals[date])} signals, pos_players={len(pos)}, holders={sum(len(v) for v in holders.values())}", flush=True)

    return signals


def main():
    print("加载数据...", flush=True)
    tbd = load_tbd()
    nav_arr = load_charts()
    tn_rules = load_tn_rules()
    print(f"交易天数: {len(tbd)}, 有净值基金: {len(nav_arr)}, T+N规则: {len(tn_rules)}", flush=True)

    sig_a = build_signals(tbd, nav_arr, tn_rules, "amount")
    out_a = os.path.join(ROOT, "data", "smart_money_signals_amount.json")
    with open(out_a, "w", encoding="utf-8") as f:
        json.dump(sig_a, f, ensure_ascii=False)
    print(f"线路A(金额top3) 信号总数: {sum(len(v) for v in sig_a.values())}, -> {out_a}", flush=True)

    sig_b = build_signals(tbd, nav_arr, tn_rules, "return")
    out_b = os.path.join(ROOT, "data", "smart_money_signals_ret.json")
    with open(out_b, "w", encoding="utf-8") as f:
        json.dump(sig_b, f, ensure_ascii=False)
    print(f"线路B(收益率top3) 信号总数: {sum(len(v) for v in sig_b.values())}, -> {out_b}", flush=True)


if __name__ == "__main__":
    main()