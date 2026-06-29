#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Auto Pipeline: Daily JD Finance data crawler + signal computation + report generation.

Runs in two environments:
  - GitHub Actions (daily cron): cookie from JD_COOKIES env var (base64)
  - Local: cookie from data/jd_auth/cookies.json

Usage:
    python scripts/auto-pipeline.py              # normal run
    python scripts/auto-pipeline.py --offline     # skip API fetch, regenerate report from cache

Outputs:
    data/holdings_snapshot.json                  # tracked, overwritten
    data/holdings_diff_cache.json                 # tracked, overwritten
    data/trading_records_cache.json               # tracked, overwritten
    data/holdings_snapshot_YYYY-MM-DD.json        # tracked, archive
    data/trading_records_YYYY-MM-DD.json          # tracked, archive
    data/auto/status.json                         # tracked, run metadata
    reports/auto/daily-YYYY-MM-DD.md              # tracked, daily report
    reports/auto/latest.md                        # tracked, latest report (overwritten)
"""

import base64
import json
import os
import re
import sys
import time
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

# --- Ensure project root is in sys.path for tools.jd_finance_api imports ---
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from tools.jd_finance_api import (
    FOLLOWED_USERS,
    _load_cookies,
    _save_cookies,
    _verify_cookies,
    _ensure_cookies,
    get_user_holdings,
    get_trading_records,
)

# ── Paths ──────────────────────────────────────────────────────────────────
DATA_DIR = _PROJECT_ROOT / "data"
AUTO_DIR = DATA_DIR / "auto"
REPORTS_DIR = _PROJECT_ROOT / "reports" / "auto"
COOKIES_PATH = DATA_DIR / "jd_auth" / "cookies.json"

SNAPSHOT_PATH = DATA_DIR / "holdings_snapshot.json"
DIFF_PATH = DATA_DIR / "holdings_diff_cache.json"
TRADING_PATH = DATA_DIR / "trading_records_cache.json"
STATUS_PATH = DATA_DIR / "auto" / "status.json"

# ── Helpers ────────────────────────────────────────────────────────────────


def _ensure_dirs():
    for d in (AUTO_DIR, REPORTS_DIR, DATA_DIR / "jd_auth"):
        d.mkdir(parents=True, exist_ok=True)


def _load_json(path, default=None):
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return default if default is not None else {}


def _write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    tmp.replace(path)


def _today_str():
    return date.today().isoformat()


def _now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _parse_amount(amt_str):
    """Parse '¥12,345.67' or '+5,000' → float. Returns 0 on failure."""
    if not amt_str:
        return 0.0
    s = str(amt_str).replace(",", "").replace("¥", "").replace("￥", "").replace("+", "").strip()
    try:
        return float(s)
    except (ValueError, TypeError):
        return 0.0


# ── Step 0: Cookie Bootstrap ───────────────────────────────────────────────


def _bootstrap_cookie():
    """Load cookie from env (CI) or local file.
    
    Returns: (cookies_dict, ok_bool, message_str)
    """
    # CI mode: JD_COOKIES env var (base64 encoded cookies.json)
    env_cookie = os.environ.get("JD_COOKIES", "")
    if env_cookie:
        try:
            decoded = base64.b64decode(env_cookie).decode("utf-8")
            cookie_data = json.loads(decoded)
            COOKIES_PATH.parent.mkdir(parents=True, exist_ok=True)
            with open(COOKIES_PATH, "w", encoding="utf-8") as f:
                json.dump(cookie_data, f, ensure_ascii=False, indent=2)
            print("  [OK] Cookie decoded from JD_COOKIES env")
        except Exception as e:
            print(f"  [ERR] Failed to decode JD_COOKIES: {e}")

    # Load from file
    cookies = _load_cookies()
    if not cookies:
        return {}, False, "No cookie found"

    valid, user_info = _verify_cookies(cookies)
    if valid:
        name = user_info.get("nickName", user_info.get("userName", ""))
        return cookies, True, f"Valid (user: {name})"

    return cookies, False, "Cookie expired/invalid"


# ── Step 1: Fetch Holdings ─────────────────────────────────────────────────


def _fetch_all_holdings(cookies):
    """Fetch holdings for all followed users.
    
    Returns: {user_name: [holdings_list]} or None on failure
    """
    print("\n── Phase 1: Fetching holdings ──")
    all_holdings = {}
    ok_count = 0

    for numeric_id, name in FOLLOWED_USERS.items():
        uid = f"jimu_user_info-{numeric_id}"
        try:
            result = get_user_holdings(uid, cookies=cookies)
            items = result.get("holdings", [])
            all_holdings[name] = items
            ok_count += 1
            print(f"  [{name}] {len(items)} funds")
        except Exception as e:
            print(f"  [{name}] FAILED: {e}")
            all_holdings[name] = []
        time.sleep(0.3)

    print(f"  → {ok_count}/{len(FOLLOWED_USERS)} users OK")
    return all_holdings


def _compute_holdings_diff(previous, current):
    """Compare previous vs current holdings and generate diff signals.
    
    Returns: {
        "date": "...",
        "timestamp": "...",
        "new_funds": [{"fund_name", "fund_code", "users": [...]}, ...],
        "removed_funds": [{"fund_name", "fund_code", "users": [...]}, ...],
        "increased": [...],
        "decreased": [...],
        "all_signals": [{"fund_name", "fund_code", "signal", "users", "detail"}, ...]
    }
    """
    # Build inverted index: (code) → {users: [name], previous_amounts: {name: amt}, current_amounts: {name: amt}}
    fund_map = defaultdict(lambda: {
        "fund_name": "", "fund_code": "",
        "prev_users": [], "curr_users": [],
        "prev_amounts": {}, "curr_amounts": {},
    })

    for name, items in previous.items():
        for item in items:
            code = item.get("code", "")
            fname = item.get("name", "")
            amt = _parse_amount(item.get("amount", "0"))
            fund_map[code]["fund_name"] = fname
            fund_map[code]["fund_code"] = code
            fund_map[code]["prev_users"].append(name)
            fund_map[code]["prev_amounts"][name] = amt

    for name, items in current.items():
        for item in items:
            code = item.get("code", "")
            fname = item.get("name", "")
            amt = _parse_amount(item.get("amount", "0"))
            fund_map[code]["fund_name"] = fname
            fund_map[code]["fund_code"] = code
            fund_map[code]["curr_users"].append(name)
            fund_map[code]["curr_amounts"][name] = amt

    new_funds = []
    removed_funds = []
    increased = []
    decreased = []

    total_signals = []

    for code, info in fund_map.items():
        prev_set = set(info["prev_users"])
        curr_set = set(info["curr_users"])
        added = curr_set - prev_set
        removed = prev_set - curr_set

        if added:
            new_funds.append({
                "fund_name": info["fund_name"],
                "fund_code": code,
                "users": sorted(added),
            })
            total_signals.append({
                "fund_name": info["fund_name"],
                "fund_code": code,
                "signal": "new",
                "users": sorted(added),
                "detail": f"新增持仓: {', '.join(sorted(added))}",
            })

        if removed:
            removed_funds.append({
                "fund_name": info["fund_name"],
                "fund_code": code,
                "users": sorted(removed),
            })
            total_signals.append({
                "fund_name": info["fund_name"],
                "fund_code": code,
                "signal": "removed",
                "users": sorted(removed),
                "detail": f"清仓: {', '.join(sorted(removed))}",
            })

        # Amount changes (users in both snapshots)
        for name in curr_set & prev_set:
            prev_amt = info["prev_amounts"].get(name, 0)
            curr_amt = info["curr_amounts"].get(name, 0)
            if prev_amt > 0 and curr_amt > prev_amt * 1.02:
                increased.append({
                    "fund_name": info["fund_name"],
                    "fund_code": code,
                    "user": name,
                    "from": prev_amt,
                    "to": curr_amt,
                })
            elif prev_amt > 0 and curr_amt < prev_amt * 0.98:
                decreased.append({
                    "fund_name": info["fund_name"],
                    "fund_code": code,
                    "user": name,
                    "from": prev_amt,
                    "to": curr_amt,
                })

    diff_data = {
        "date": _today_str(),
        "timestamp": _now_str(),
        "new_funds": new_funds,
        "removed_funds": removed_funds,
        "increased": increased,
        "decreased": decreased,
        "all_signals": total_signals,
    }
    return diff_data


# ── Step 2: Fetch Trading Records ──────────────────────────────────────────


def _fetch_all_trading_records(cookies):
    """Fetch trading records for all followed users.
    
    Returns: {
        "date": "...",
        "timestamp": "...",
        "records": [{"user", "action", "fund_name", "amount", ...}]
    }
    """
    print("\n── Phase 2: Fetching trading records ──")
    all_records = []
    ok_count = 0

    for name, numeric_id in FOLLOWED_USERS.items():
        uid = f"jimu_user_info-{numeric_id}"
        try:
            result = get_trading_records(uid, cookies=cookies)
            records = result.get("records", [])
            for r in records:
                r["_user"] = name
                r["_uid"] = numeric_id
            all_records.extend(records)
            ok_count += 1
            print(f"  [{name}] {len(records)} records")
        except Exception as e:
            print(f"  [{name}] FAILED: {e}")
        time.sleep(0.3)

    print(f"  → {ok_count}/{len(FOLLOWED_USERS)} users OK, {len(all_records)} total records")
    return all_records


def _aggregate_trading_signals(records):
    """Aggregate trading records into per-fund buy/sell counts.
    
    交易流水信号规则:
      - action 包含 "买入" or "加仓" → buy
      - action 包含 "卖出" or "减仓" or "止盈" → sell
      - 其他 → skip (调仓等)

    Returns: {
        "date": "...",
        "funds": {
            "fund_code": {
                "fund_name": "...",
                "buy_count": N,
                "sell_count": N,
                "buy_users": ["user1", ...],
                "sell_users": ["user2", ...],
                "records": [...],
            }
        }
    }
    """
    fund_data = defaultdict(lambda: {
        "fund_name": "",
        "fund_code": "",
        "buy_count": 0,
        "sell_count": 0,
        "buy_users": set(),
        "sell_users": set(),
        "records": [],
    })

    for r in records:
        action = (r.get("action") or "").strip()
        fund_name = (r.get("fund_name") or "").strip()
        user = r.get("_user", "")
        detail = r.get("detail", "")
        amount = r.get("amount", "")

        # Skip records without fund name or action
        if not fund_name or not action:
            continue

        # Classify action
        is_buy = any(kw in action for kw in ["买入", "加仓", "定投"])
        is_sell = any(kw in action for kw in ["卖出", "减仓", "止盈"])

        if not is_buy and not is_sell:
            continue

        # Use fund_name as key (no code available in records)
        key = fund_name
        fi = fund_data[key]
        fi["fund_name"] = fund_name

        if is_buy:
            fi["buy_count"] += 1
            if user:
                fi["buy_users"].add(user)
        if is_sell:
            fi["sell_count"] += 1
            if user:
                fi["sell_users"].add(user)

        fi["records"].append({
            "user": user,
            "action": action,
            "amount": amount,
            "detail": detail,
        })

    # Convert sets to sorted lists for JSON serialization
    result = {"date": _today_str(), "funds": {}}
    for key, fi in fund_data.items():
        result["funds"][key] = {
            "fund_name": fi["fund_name"],
            "buy_count": fi["buy_count"],
            "sell_count": fi["sell_count"],
            "buy_users": sorted(fi["buy_users"]),
            "sell_users": sorted(fi["sell_users"]),
            "records": fi["records"],
        }

    return result


# ── Step 3: Merge Signals ──────────────────────────────────────────────────


def _compute_merged_signals(trading_signals, holdings_diff):
    """Merge trading records signals + holdings diff signals.
    
    交易流水权重大于持仓快照，因为持仓可能买于很久之前（成本未知），
    而交易流水反映当下的判断。

    Net Signal Logic:
      strong_buy:  buy_count >= 3
      buy:         buy_count >= 2 AND sell_count = 0
      weak_buy:    buy_count >= 2 AND sell_count > 0
      strong_sell: sell_count >= 3
      sell:        sell_count >= 2 AND sell_count > buy_count + 1
      weak_sell:   sell_count >= 1 AND buy_count = 0
      neutral:     everything else

    Returns: {
        "date": "...",
        "signals": [
            {
                "fund_name": "...",
                "net_signal": "strong_buy|buy|weak_buy|strong_sell|sell|weak_sell|neutral",
                "buy_count": N,
                "sell_count": N,
                "buy_users": [...],
                "sell_users": [...],
                "holdings_new": [...],
                "holdings_removed": [...],
                "total_score": N,  # -5 (strong sell) to +5 (strong buy)
            }
        ]
    }
    """
    signal_map = {}
    trading_funds = trading_signals.get("funds", {})

    # Index holdings diff signals by fund_name
    holdings_new_map = defaultdict(list)
    holdings_removed_map = defaultdict(list)
    for item in holdings_diff.get("new_funds", []):
        holdings_new_map[item["fund_name"]].extend(item["users"])
    for item in holdings_diff.get("removed_funds", []):
        holdings_removed_map[item["fund_name"]].extend(item["users"])

    # Process all funds that appear in either trading records or holdings diff
    all_fund_names = set(trading_funds.keys()) | set(holdings_new_map.keys()) | set(holdings_removed_map.keys())

    for fname in sorted(all_fund_names):
        tf = trading_funds.get(fname, {})
        bc = tf.get("buy_count", 0)
        sc = tf.get("sell_count", 0)
        bu = tf.get("buy_users", [])
        su = tf.get("sell_users", [])
        hn = holdings_new_map.get(fname, [])
        hr = holdings_removed_map.get(fname, [])

        # Net signal logic
        if bc >= 3:
            net = "strong_buy"
            score = 5
        elif bc >= 2 and sc == 0:
            net = "buy"
            score = 3
        elif bc >= 2 and sc > 0:
            net = "weak_buy"
            score = 2
        elif sc >= 3:
            net = "strong_sell"
            score = -5
        elif sc >= 2 and sc > bc + 1:
            net = "sell"
            score = -3
        elif sc >= 1 and bc == 0:
            net = "weak_sell"
            score = -2
        elif bc == 0 and sc == 0:
            # Only in holdings diff, no trading records
            if hn and not hr:
                net = "weak_buy"
                score = 1
            elif hr and not hn:
                net = "weak_sell"
                score = -1
            else:
                net = "neutral"
                score = 0
        else:
            net = "neutral"
            score = 0

        signal_map[fname] = {
            "fund_name": fname,
            "net_signal": net,
            "score": score,
            "buy_count": bc,
            "sell_count": sc,
            "buy_users": bu,
            "sell_users": su,
            "holdings_new_users": hn,
            "holdings_removed_users": hr,
        }

    # Sort by score ascending (sells first, then neutral, then buys)
    sorted_signals = sorted(signal_map.values(), key=lambda x: x["score"])

    return {
        "date": _today_str(),
        "timestamp": _now_str(),
        "signals": sorted_signals,
    }


# ── Step 4: Generate Report ─────────────────────────────────────────────────


def _signal_label(signal_type):
    labels = {
        "strong_sell": "🔴 多人卖出",
        "sell": "🔴 卖出确认",
        "weak_sell": "🟡 减仓观察",
        "neutral": "⚪ 无信号",
        "weak_buy": "🟢 关注",
        "buy": "🟢 买入信号",
        "strong_buy": "🟢 多人买入",
    }
    return labels.get(signal_type, signal_type)


def _generate_report(merged_signals, status):
    today = _today_str()
    signals = merged_signals.get("signals", [])

    # Categorize
    sells = [s for s in signals if s["score"] <= -2]
    watches = [s for s in signals if s["score"] == -1]
    neutrals = [s for s in signals if s["score"] == 0]
    watches_b = [s for s in signals if s["score"] == 1]
    buys = [s for s in signals if s["score"] >= 2]

    # User activity summary
    user_buy_count = defaultdict(int)
    user_sell_count = defaultdict(int)
    for s in signals:
        for u in s.get("buy_users", []):
            user_buy_count[u] += 1
        for u in s.get("sell_users", []):
            user_sell_count[u] += 1
    user_buy_count = dict(user_buy_count)
    user_sell_count = dict(user_sell_count)

    # Build report
    lines = []
    lines.append(f"# 每日基金监控报告 — {today}")
    lines.append("")

    # ── Freshness banner ──
    cookie_ok = status.get("cookie_ok", False)
    crawl_ok = status.get("crawl_ok", False)
    status_msg = status.get("message", "")
    if crawl_ok:
        lines.append("> ✅ 数据已更新 · " + _now_str())
    else:
        lines.append(f"> ⚠️ **数据可能不是最新的** — {status_msg}")
    lines.append("")

    # ── Sell signals ──
    lines.append("## 🔴 卖出信号")
    lines.append("")
    if sells:
        lines.append("| 基金 | 信号 | 卖出人数 | 买入人数 | 详情 |")
        lines.append("|------|------|:--------:|:--------:|------|")
        for s in sells:
            detail_parts = []
            if s["sell_users"]:
                detail_parts.append(f"卖出: {', '.join(s['sell_users'])}")
            if s["holdings_removed_users"]:
                detail_parts.append(f"清仓: {', '.join(s['holdings_removed_users'])}")
            detail = "; ".join(detail_parts)
            lines.append(f"| {s['fund_name']} | {_signal_label(s['net_signal'])} | {s['sell_count']} | {s['buy_count']} | {detail} |")
    else:
        lines.append("(无)")
    lines.append("")

    # ── Buy signals ──
    lines.append("## 🟢 买入信号")
    lines.append("")
    if buys:
        lines.append("| 基金 | 信号 | 买入人数 | 卖出人数 | 详情 |")
        lines.append("|------|------|:--------:|:--------:|------|")
        for s in buys:
            detail_parts = []
            if s["buy_users"]:
                detail_parts.append(f"买入: {', '.join(s['buy_users'])}")
            if s["holdings_new_users"]:
                detail_parts.append(f"新增: {', '.join(s['holdings_new_users'])}")
            detail = "; ".join(detail_parts)
            lines.append(f"| {s['fund_name']} | {_signal_label(s['net_signal'])} | {s['buy_count']} | {s['sell_count']} | {detail} |")
    else:
        lines.append("(无)")
    lines.append("")

    # ── Watch list ──
    if watches or watches_b:
        lines.append("## 🟡 观察列表")
        lines.append("")
        lines.append("| 基金 | 信号 | 说明 |")
        lines.append("|------|------|------|")
        for s in watches + watches_b:
            if s["score"] == -1:
                note = f"仅{len(s['holdings_removed_users'])}人被清仓，无交易流水确认"
            else:
                note = f"新增持仓: {', '.join(s['holdings_new_users'])}"
            lines.append(f"| {s['fund_name']} | {_signal_label(s['net_signal'])} | {note} |")
        lines.append("")

    # ── Activity summary ──
    lines.append("## 📊 大佬操作总览")
    lines.append("")
    lines.append("| 大佬 | 买入 | 卖出 | 活跃度 |")
    lines.append("|------|:----:|:----:|:------:|")
    all_users = set(list(user_buy_count.keys()) + list(user_sell_count.keys()))
    for name in FOLLOWED_USERS.values():
        bc = user_buy_count.get(name, 0)
        sc = user_sell_count.get(name, 0)
        if bc >= 3:
            act = "🔥"
        elif bc >= 1 or sc >= 1:
            act = "✅"
        else:
            act = "—"
        lines.append(f"| {name} | {bc} | {sc} | {act} |")
    lines.append("")

    # ── System status ──
    lines.append("## ⚠️ 系统状态")
    lines.append("")
    lines.append(f"| 项目 | 状态 |")
    lines.append(f"|------|------|")
    cookie_label = "✅ 有效" if cookie_ok else "❌ 过期/缺失"
    lines.append(f"| Cookie | {cookie_label} |")
    data_label = "✅ 今日已更新" if crawl_ok else "⚠️ 基于缓存"
    lines.append(f"| 数据 | {data_label} |")
    lines.append(f"| 报告生成 | {_now_str()} |")
    lines.append(f"| 覆盖大佬 | {len(FOLLOWED_USERS)} 人 |")
    lines.append(f"| 管道版本 | v1.0 |")
    lines.append("")

    # ── Disclaimer ──
    lines.append("---")
    lines.append("")
    lines.append("> ⚠️ 本报告基于公开数据自动生成，不构成投资建议。所有信号仅供参考。")
    lines.append("")

    return "\n".join(lines)


# ── Step 5: Write Cache Files ──────────────────────────────────────────────


def _write_caches(holdings_snapshot, holdings_diff, trading_signals, merged_signals, report_text):
    """Dual-write: fixed-name files (skills consume) + dated archives."""
    today = _today_str()

    # Fixed-name files (consumed by skills: fund-monitor, fund-sell, etc.)
    _write_json(SNAPSHOT_PATH, holdings_snapshot)
    _write_json(DIFF_PATH, holdings_diff)
    _write_json(TRADING_PATH, trading_signals)

    # Dated archives
    _write_json(DATA_DIR / f"holdings_snapshot_{today}.json", holdings_snapshot)
    _write_json(DATA_DIR / f"trading_records_{today}.json", trading_signals)

    # Reports
    daily_path = REPORTS_DIR / f"daily-{today}.md"
    latest_path = REPORTS_DIR / "latest.md"
    daily_path.parent.mkdir(parents=True, exist_ok=True)
    with open(daily_path, "w", encoding="utf-8") as f:
        f.write(report_text)
    with open(latest_path, "w", encoding="utf-8") as f:
        f.write(report_text)

    return daily_path


# ── Main ────────────────────────────────────────────────────────────────────


def main():
    offline = "--offline" in sys.argv
    _ensure_dirs()
    today = _today_str()

    print(f"╔═══ AI Berkshire Auto Pipeline ═══╗")
    print(f"  Date: {today}")
    print(f"  Mode: {'OFFLINE' if offline else 'NORMAL'}")
    print(f"  Users: {len(FOLLOWED_USERS)} followed")
    print(f"╚═══════════════════════════════════╝")

    # ── Step 0: Cookie ──
    print("\n── Step 0: Auth ──")
    if offline:
        print("  [SKIP] Offline mode, skipping auth")
        cookie_ok = False
        cookie_msg = "offline mode"
        cookies = None
    else:
        cookies, cookie_ok, cookie_msg = _bootstrap_cookie()
        check = "[OK]" if cookie_ok else "[--]"
        print(f"  {check} {cookie_msg}")

    # ── Step 1: Holdings ──
    previous = _load_json(SNAPSHOT_PATH, {})
    if cookies and cookie_ok:
        current_holdings = _fetch_all_holdings(cookies)
        holdings_ok = current_holdings is not None
    else:
        print("\n── Phase 1: Holdings (skipped, no cookie) ──")
        current_holdings = {}
        holdings_ok = False

    # Compute diff (even if fetch was skipped, to show previous state)
    prev_holdings = previous.get("holdings", previous) if isinstance(previous, dict) else {}
    holdings_diff = _compute_holdings_diff(prev_holdings, current_holdings)
    print(f"  Diff: {len(holdings_diff['new_funds'])} new, {len(holdings_diff['removed_funds'])} removed")

    # ── Step 2: Trading Records ──
    if cookies and cookie_ok:
        all_records = _fetch_all_trading_records(cookies)
        trading_ok = True
    else:
        print("\n── Phase 2: Trading records (skipped, no cookie) ──")
        all_records = []
        trading_ok = False

    trading_signals = _aggregate_trading_signals(all_records)
    print(f"  Aggregated: {len(trading_signals['funds'])} funds with signals")
    crawl_ok = holdings_ok and trading_ok

    # ── Step 3: Merge Signals ──
    print("\n── Step 3: Merging signals ──")
    merged = _compute_merged_signals(trading_signals, holdings_diff)
    signal_counts = defaultdict(int)
    for s in merged["signals"]:
        signal_counts[s["net_signal"]] += 1
    for k, v in sorted(signal_counts.items()):
        print(f"  {k}: {v}")
    print(f"  Total: {len(merged['signals'])} funds")

    # ── Step 4: Generate Report ──
    print("\n── Step 4: Generating report ──")
    status = {
        "date": today,
        "timestamp": _now_str(),
        "cookie_ok": cookie_ok,
        "crawl_ok": crawl_ok,
        "holdings_ok": holdings_ok,
        "trading_ok": trading_ok,
        "message": cookie_msg,
    }
    report = _generate_report(merged, status)

    # ── Step 5: Write Caches ──
    print("\n── Step 5: Writing caches ──")
    holdings_snapshot = {
        "date": today,
        "timestamp": _now_str(),
        "holdings": current_holdings,
    }
    report_path = _write_caches(holdings_snapshot, holdings_diff, trading_signals, merged, report)
    _write_json(STATUS_PATH, status)
    print(f"  Report: {report_path}")
    print(f"  Status: {STATUS_PATH}\n")

    # ── Summary ──
    check = "[OK]" if cookie_ok else "[--]"
    hk = "[OK]" if holdings_ok else "[--]"
    tk = "[OK]" if trading_ok else "[--]"
    print(f"--- Pipeline Complete ---")
    print(f"  Cookie:      {check}")
    print(f"  Holdings:    {hk}")
    print(f"  Trading:     {tk}")
    print(f"  Signals:     {len(merged['signals'])} funds")
    print(f"  Report:      {report_path.name}")

    # Exit code: 0 if data was fetched, 0 also if offline but report still generated
    # Only non-zero if something truly broken
    if not crawl_ok and not offline and cookies:
        # Had cookie but crawl failed partially
        print("\n⚠️  Pipeline completed with partial failures (data may be incomplete)")
    elif not cookies and not offline:
        print("\n❌ No cookie available. Set JD_COOKIES env or place cookies.json in data/jd_auth/")
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()
