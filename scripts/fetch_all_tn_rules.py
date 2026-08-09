#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
用接口 getFundTradeRulesPageInfo 批量补全全量基金的 T+N 交易规则缓存。
================================================================
背景:
  交易数据涉及 5985 只基金, 但旧缓存只抓了 508 只, 且缺赎回 T+N
  (redeem_date/redeem_confirm_date/redeem_arrive_date) 字段。
  用户要求: 用接口抓取真实 T+N, 不做硬编码兜底。

本脚本:
  1. 从 trading_by_date_real414_v7.json.gz 取全部交易基金码。
  2. 并发调 get_fund_trade_rules (免 cookie, ~0.17s/只), 写入 trade_rules_{code}.json 缓存。
  3. 对已有缓存但缺 redeem_arrive_date 的基金也补抓(字段补齐)。
  4. 产出 T+N 汇总 data/tn_by_fund.json, 供信号构建直接读取。

T+N 推导:
  buy_N    = confirm_date 相对 buy_date 的自然日差   (买入确认延迟)
  redeem_N = redeem_confirm_date 相对 redeem_date 的自然日差 (赎回确认延迟)
  arrive_N = redeem_arrive_date 相对 redeem_date 的自然日差   (赎回到账延迟)
================================================================
"""
import sys, os, json, gzip, glob, time
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tools.jd_finance_api import get_fund_trade_rules

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
V5 = os.path.join(ROOT, "backtest", "data", "trading_by_date_real414_v7.json.gz")
CACHE_DIR = os.path.join(ROOT, "data", "fund_cache")
OUT_TN = os.path.join(ROOT, "data", "tn_by_fund.json")


def load_trading_codes():
    with gzip.open(V5, "rt", encoding="utf-8") as f:
        tbd = json.load(f)
    codes = set()
    for date, recs in tbd.items():
        for r in recs:
            if r.get("fund_code"):
                codes.add(r["fund_code"])
    return codes


def existing_cache_ok():
    """已有缓存且含 redeem_arrive_date 的基金, 视为字段完整。"""
    ok = set()
    incomplete = set()
    for fp in glob.glob(os.path.join(CACHE_DIR, "trade_rules_*.json")):
        code = os.path.basename(fp).replace("trade_rules_", "").replace(".json", "")
        try:
            d = json.load(open(fp, encoding="utf-8"))
        except Exception:
            incomplete.add(code)
            continue
        if d.get("redeem_arrive_date"):
            ok.add(code)
        else:
            incomplete.add(code)
    return ok, incomplete


def parse_mmdd(s):
    s = str(s).replace(" 15:00前", "").replace("前", "").strip()
    try:
        mm, dd = s.split("-")
        return int(mm), int(dd)
    except Exception:
        return None


def day_diff(a, b):
    """a/b 是 'MM-DD' 或 'MM-DD 15:00前', 返回 b 相对 a 的自然日差, 失败返回 None。"""
    import datetime
    pa, pb = parse_mmdd(a), parse_mmdd(b)
    if not pa or not pb:
        return None
    d1 = datetime.date(2000, pa[0], pa[1])
    d2 = datetime.date(2000, pb[0], pb[1])
    diff = (d2 - d1).days
    return diff if diff >= 0 else None


def fetch_all(codes, workers=15):
    results = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        fut_map = {pool.submit(get_fund_trade_rules, c, True): c for c in codes}
        for fut in as_completed(fut_map):
            c = fut_map[fut]
            try:
                r = fut.result()
                results[c] = r if r else None
            except Exception as e:
                results[c] = None
    return results


def main():
    codes = load_trading_codes()
    ok_cache, incomplete_cache = existing_cache_ok()
    # 需要抓取: 全部交易基金 - 字段完整的缓存
    need = codes - ok_cache
    print(f"交易基金 {len(codes)}; 已有完整缓存 {len(ok_cache)}; 需抓取 {len(need)} (含 {len(incomplete_cache)} 字段不全)", flush=True)

    t0 = time.time()
    results = fetch_all(need)
    dt = time.time() - t0
    got = sum(1 for v in results.values() if v)
    print(f"抓取完成 {got}/{len(need)}, 耗时 {dt:.1f}s", flush=True)

    # 汇总 T+N
    tn = {}
    n_buy = {}
    for code, r in results.items():
        if not r:
            continue
        bn = day_diff(r.get("buy_date"), r.get("confirm_date"))
        rn = day_diff(r.get("redeem_date"), r.get("redeem_confirm_date"))
        an = day_diff(r.get("redeem_date"), r.get("redeem_arrive_date"))
        tn[code] = {
            "buy_N": bn,
            "redeem_N": rn,
            "arrive_N": an,
            "buy_date": r.get("buy_date"),
            "confirm_date": r.get("confirm_date"),
            "redeem_date": r.get("redeem_date"),
            "redeem_confirm_date": r.get("redeem_confirm_date"),
            "redeem_arrive_date": r.get("redeem_arrive_date"),
        }
        if bn is not None:
            n_buy[bn] = n_buy.get(bn, 0) + 1

    with open(OUT_TN, "w", encoding="utf-8") as f:
        json.dump(tn, f, ensure_ascii=False, indent=1)
    print(f"T+N 汇总已写入 {OUT_TN}, 共 {len(tn)} 只", flush=True)
    print(f"买入确认 N 分布: {dict(sorted(n_buy.items()))}", flush=True)

    # 缓存统计
    total_cache = len(glob.glob(os.path.join(CACHE_DIR, "trade_rules_*.json")))
    with_redeem = sum(1 for v in tn.values() if v.get("redeem_arrive_date"))
    print(f"trade_rules 缓存总数: {total_cache}; 含赎回到账 T+N: {with_redeem}", flush=True)


if __name__ == "__main__":
    main()