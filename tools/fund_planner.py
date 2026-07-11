#!/usr/bin/env python3
"""Fund Allocation Planner — Kelly Criterion + Risk Parity + Position Sizing.

Reads scoring data from pipeline, computes recommended buy amounts
based on available cash, fund scores, daily limits, and risk constraints.

Usage:
    python tools/fund_planner.py --cash 10000
    python tools/fund_planner.py --cash 50000 --output
"""
import json, math, sys
from pathlib import Path
from datetime import date

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
CACHE_DIR = DATA_DIR / "fund_cache"

RISK_FREE_RATE = 0.025
MAX_SINGLE_PCT = 0.15   # max 15% of total capital per fund
MAX_QDII_PCT = 0.30     # max 30% total QDII exposure
CASH_RESERVE_PCT = 0.20 # keep 20% cash


def load_cache(name, default=None):
    p = Path(name)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else (default or {})


def get_limit(code):
    p = CACHE_DIR / f"trade_rules_{code}.json"
    if p.exists():
        try:
            d = json.loads(p.read_text("utf-8"))
            return d.get("day_limit") or d.get("dayLimit") or 0
        except: pass
    return 0


def kelly_allocation(total_cash: float) -> list[dict]:
    """Compute fund allocations using Kelly Criterion + constraints.

    Args:
        total_cash: total available cash the user has

    Returns:
        list of {code, name, score, suggested_amount, strategy, ...}
    """
    status = load_cache(DATA_DIR / "auto" / "status.json", {})
    fund_scores = status.get("fund_scores", {})
    trading = load_cache(DATA_DIR / "trading_records_cache.json", {})
    my_holdings = status.get("my_holdings", [])
    my_codes = {h["code"] for h in my_holdings if h.get("code")}

    available = total_cash * (1 - CASH_RESERVE_PCT)

    # Collect buy candidates (score >= 3.3 with buy signal)
    candidates = []
    for fname, fd in trading.get("funds", {}).items():
        code = fd.get("fund_code") or fd.get("code", "")
        bc = fd.get("buy_count", 0)
        sc = fd.get("buy_count", 0)
        si = fund_scores.get(code, {})
        total = si.get("total", 0)
        if total and total >= 3.3 and bc >= 2:
            limit = get_limit(code)
            candidates.append({
                "code": code,
                "name": fname[:24],
                "score": total,
                "buy_count": bc,
                "day_limit": float(limit) if limit and limit != float('inf') else 999999,
                "is_qdii": "QDII" in fname,
                "my_hold": code in my_codes,
            })

    if not candidates:
        return []

    # Kelly allocation
    for c in candidates:
        p = c["score"] / 5.0
        b = max(p * 2, 0.5)
        kelly = max(0, min((p * b - (1 - p)) / b, 0.2))
        suggested = available * kelly * c["score"] / 5.0
        if c["day_limit"] < 999999:
            suggested = min(suggested, c["day_limit"])
        suggested = min(suggested, total_cash * MAX_SINGLE_PCT)
        suggested = round(suggested / 100) * 100
        c["_suggested"] = suggested
        c["_kelly"] = kelly

    # Sort by score descending, allocate in order
    candidates.sort(key=lambda x: x["score"], reverse=True)
    allocated = 0
    results = []
    for c in candidates:
        if allocated >= available or c["_suggested"] < 100:
            continue
        if allocated + c["_suggested"] > available:
            c["_suggested"] = round((available - allocated) / 100) * 100
        if c["_suggested"] < 100:
            continue
        allocated += c["_suggested"]

        # DCA strategy: if daily limit exists and suggested > limit, suggest DCA
        dca = None
        if c["day_limit"] < 999999 and c["_suggested"] > c["day_limit"]:
            dca_daily = min(c["day_limit"], round(c["_suggested"] / 20 / 100) * 100)
            dca = f"日定投 ¥{dca_daily}/天"
            strategy = "定投"
        else:
            strategy = "一次性"

        results.append({
            "code": c["code"],
            "name": c["name"],
            "score": round(c["score"], 2),
            "kelly_coeff": round(c["_kelly"], 3),
            "suggested_amount": c["_suggested"],
            "strategy": strategy,
            "dca": dca,
            "day_limit": c["day_limit"] if c["day_limit"] < 999999 else None,
            "my_hold": c["my_hold"],
            "is_qdii": c["is_qdii"],
        })

    return results


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Fund Allocation Planner")
    parser.add_argument("--cash", type=float, default=10000, help="Available cash")
    parser.add_argument("--output", action="store_true", help="Write to status.json")
    args = parser.parse_args()

    # Fix Windows console encoding
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    results = kelly_allocation(args.cash)
    if not results:
        print("No qualifying funds available")
        return

    print(f"\nFund Allocation (Cash: {args.cash:.0f})")
    for r in results:
        ht = " (held)" if r["my_hold"] else ""
        print(f"  {r['name']:24s} {r['code']:8s} score={r['score']:.2f} kelly={r['kelly_coeff']:.3f} amt={r['suggested_amount']} {r['strategy']}{ht}")
    total = sum(r["suggested_amount"] for r in results)
    avail = args.cash * (1 - CASH_RESERVE_PCT)
    print(f"  Total: {total} / Available: {avail:.0f} (Reserve: {args.cash * CASH_RESERVE_PCT:.0f})")

    if args.output:
        status_path = DATA_DIR / "auto" / "status.json"
        status = load_cache(status_path, {})
        status["fund_plan"] = results
        with open(status_path, "w", encoding="utf-8") as f:
            json.dump(status, f, ensure_ascii=False, indent=2)
        print(f"\n已写入 status.json")


if __name__ == "__main__":
    main()