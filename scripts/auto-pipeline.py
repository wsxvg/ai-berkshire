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

# 统一日志入口（stderr + logs/auto_pipeline.log 轮转）；诊断输出不再走 stdout，
# GitHub Actions 仍可见 stderr，且不会污染任何对 stdout 的读取。
try:
    from tools.logutil import get_logger
except Exception:
    from logutil import get_logger

_logger = get_logger("auto_pipeline")
logger = _logger  # 兼容旧代码中的 logger 引用

from chinese_calendar import is_workday

from tools.technical_indicators import compute_entry_timing_score
from tools.jd_finance_api import (
    FOLLOWED_USERS,
    _load_cookies,
    _verify_cookies,
    _ensure_cookies,
    get_user_holdings,
    get_trading_records,
    get_fund_performance,
    get_fund_detail,
    get_fund_chart_data,
    get_daily_news,
    get_fund_ranking,
    _JD_BASE,
    _USER_AGENT,
)

# ── Paths ──────────────────────────────────────────────────────────────────
DATA_DIR = _PROJECT_ROOT / "data"
AUTO_DIR = DATA_DIR / "auto"
REPORTS_DIR = _PROJECT_ROOT / "reports" / "auto"
_DYNAMIC_USERS_PATH = DATA_DIR / "dynamic_users.json"
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
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"  [WARN] Failed to load {path.name}: {e}")
    return default if default is not None else {}


def _write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ── Dynamic User Pool ────────────────────────────────────────────────────
# Stores ranking users discovered from platform, with scoring and status.
# Pool: {uid: {name, added_date, last_active, score, weight, status}}

_DYNAMIC_USERS_PATH = _PROJECT_ROOT / "data" / "dynamic_users.json"

def _load_dynamic_pool():
    pool = _load_json(_DYNAMIC_USERS_PATH, {})
    # Clean up: remove old excluded users (>90 days)
    today = _today_str()
    to_remove = []
    for uid, info in pool.items():
        if info.get("status") == "excluded":
            excluded_date = info.get("excluded_date", "")
            if excluded_date and (datetime.strptime(today[:10], "%Y-%m-%d") - datetime.strptime(excluded_date[:10], "%Y-%m-%d")).days > 90:
                to_remove.append(uid)
    for uid in to_remove:
        del pool[uid]
    return pool


def _save_dynamic_pool(pool):
    _write_json(_DYNAMIC_USERS_PATH, pool)


def _merge_dynamic_users(pool, new_users):
    """Merge newly discovered ranking users into the dynamic pool."""
    today = _today_str()
    added = 0
    for uid, name in new_users.items():
        if uid not in pool:
            pool[uid] = {
                "name": name,
                "added_date": today,
                "last_active": today,
                "status": "probation",  # probation → active → excluded
                "score": 0,
                "weight": 0.5,  # start with 0.5 weight
            }
            added += 1
    if added:
        _save_dynamic_pool(pool)
    return added


def _get_all_tracked_users(pool):
    """Get all active users to track (FOLLOWED_USERS + dynamic pool active/probation)."""
    users = dict(FOLLOWED_USERS)
    for uid, info in pool.items():
        if info.get("status") in ("active", "probation"):
            users[uid] = info["name"]
    return users


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
            logger.info("  [OK] Cookie decoded from JD_COOKIES env")
        except Exception as e:
            logger.error(f"  [ERR] Failed to decode JD_COOKIES: {e}")

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


def _fetch_all_holdings(cookies, extra_users=None):
    """Fetch holdings for all followed users concurrently.
    extra_users: optional dict of {uid: name} to track alongside FOLLOWED_USERS
    Returns: {user_name: [holdings_list]} or None on failure"""
    tracked = dict(FOLLOWED_USERS)
    if extra_users:
        tracked.update(extra_users)

    logger.info(f"\n── Phase 1: Fetching holdings (concurrent, {len(tracked)} users) ──")
    from concurrent.futures import ThreadPoolExecutor, as_completed
    all_holdings = {}

    def fetch_one(numeric_id, name):
        try:
            uid = f"jimu_user_info-{numeric_id}"
            result = get_user_holdings(uid, cookies=cookies)
            items = result.get("holdings", [])
            logger.info(f"  [{name}] {len(items)} funds")
            return name, items
        except Exception as e:
            logger.error(f"  [{name}] FAILED: {e}")
            return name, []

    with ThreadPoolExecutor(max_workers=15) as pool:
        futs = {pool.submit(fetch_one, nid, nm): nm for nid, nm in tracked.items()}
        for fut in as_completed(futs):
            name, items = fut.result()
            all_holdings[name] = items

    ok_count = sum(1 for v in all_holdings.values() if v)
    logger.info(f"  → {ok_count}/{len(tracked)} users OK")
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


def _load_user_last_date():
    """Load existing trading data to find each user's last trade date and record count.
    Returns: {numeric_id: (last_date, total_records)} or {} if no cached data."""
    trading_by_date_path = _PROJECT_ROOT / "backtest" / "data" / "trading_by_date_fixed.json"
    if not trading_by_date_path.exists():
        return {}
    try:
        by_date = json.loads(trading_by_date_path.read_text("utf-8"))
        user_info = {}
        for d, day_records in sorted(by_date.items()):
            for r in day_records:
                uid = str(r.get("_uid", r.get("uid", "")))
                if uid:
                    if uid in user_info:
                        user_info[uid] = (max(user_info[uid][0], d), user_info[uid][1] + 1)
                    else:
                        user_info[uid] = (d, 1)
        return user_info
    except Exception:
        return {}


def _fetch_all_trading_records(cookies, extra_users=None):
    """Fetch trading records for all followed users concurrently.

    智能增量策略:
    - 新用户（无历史数据）→ today_only=False，全量拉取
    - 老用户（有历史数据，但最后交易日期 ≥ 1天前）→ today_only=False，补缺口
    - 老用户（今天已有数据）→ today_only=True，快速增量
    extra_users: optional dict of {uid: name} to track alongside FOLLOWED_USERS
    Returns: [record_dict, ...]"""
    tracked = dict(FOLLOWED_USERS)
    if extra_users:
        tracked.update(extra_users)

    # 智能判断每个用户是否需要全量拉取
    from datetime import date as dt_date
    user_last = _load_user_last_date()
    today = dt_date.today().isoformat()
    new_count = 0
    catchup_count = 0
    fresh_count = 0

    logger.info(f"\n── Phase 2: Fetching trading records (concurrent, {len(tracked)} users) ──")
    from concurrent.futures import ThreadPoolExecutor, as_completed
    all_records = []

    # 截断检测阈值：之前 max_pages=5 时最多 100 条，够到此数说明可能被截断
    OLD_TRUNCATE_CAP = 100
    # TODO: 下次跑完切换为 False，恢复智能增量
    FORCE_FULL_ALL = True

    def fetch_one(numeric_id, name):
        nonlocal new_count, catchup_count, fresh_count
        try:
            uid = f"jimu_user_info-{numeric_id}"
            info = user_last.get(str(numeric_id))
            last_date = info[0] if info else ""
            total_before = info[1] if info else 0

            # 判断是否需要全量
            need_full = (
                FORCE_FULL_ALL  # 临时强制全量
                or not last_date
                or last_date < today
                or total_before >= OLD_TRUNCATE_CAP
            )

            if not last_date:
                new_count += 1
                need_full_msg = "FULL(nobase)"
            elif total_before >= OLD_TRUNCATE_CAP:
                catchup_count += 1
                need_full_msg = f"FULL(trunc:{total_before}recs)"
            elif last_date < today:
                catchup_count += 1
                need_full_msg = f"FULL(catchup,{last_date})"
            else:
                need_full = True  # FORCE_FULL_ALL 强制
                catchup_count += 1
                need_full_msg = "FULL(force)"

            if need_full:
                result = get_trading_records(uid, cookies=cookies, today_only=False, max_pages=200)
                mode = need_full_msg
            else:
                fresh_count += 1
                result = get_trading_records(uid, cookies=cookies, today_only=True)
                mode = "INCR"

            records = result.get("records", [])
            for r in records:
                r["_user"] = name
                r["_uid"] = numeric_id

            # 去重交给 _merge_trading_to_backtest（按日期+用户+基金名+操作去重）
            logger.info(f"  [{name}] {len(records)} records [{mode}]")
            return records
        except Exception as e:
            logger.error(f"  [{name}] FAILED: {e}")
            return []

    with ThreadPoolExecutor(max_workers=15) as pool:
        futs = {pool.submit(fetch_one, nid, nm): nm for nid, nm in tracked.items()}
        for fut in as_completed(futs):
            all_records.extend(fut.result())

    logger.info("  → %d users OK, %d total records (new:%d catchup:%d fresh:%d)"
                % (len(tracked), len(all_records), new_count, catchup_count, fresh_count))
    return all_records


def _merge_trading_to_backtest(records):
    """将新抓取的交易记录合并到 backtest/data/trading_by_date_fixed.json。

    JD API 返回的字段: _date_prefix(MM-DD), fund_name, action, amount
    按日期 + 用户 ID + 基金名 + 操作 去重，新人入驻后下次自动识别为老用户。
    """
    from datetime import date as dt_date
    trading_by_date_path = _PROJECT_ROOT / "backtest" / "data" / "trading_by_date_fixed.json"

    # 加载现有数据
    existing = {}
    if trading_by_date_path.exists():
        try:
            existing = json.loads(trading_by_date_path.read_text("utf-8"))
        except Exception:
            existing = {}

    # 构建已有数据 key set 用于去重
    existing_keys = set()
    for date_str, day_records in existing.items():
        for r in day_records:
            uid = str(r.get("_uid", ""))
            fname = r.get("fund_name", "")
            action = r.get("action", "")
            existing_keys.add((date_str, uid, fname, action))

    today = dt_date.today()
    current_month = today.month
    added = 0
    skipped = 0
    for r in records:
        # 日期: JD API 的 summary 字段才是完整日期源
        #  今年记录: summary="07-06 11:49:23" (MM-DD HH:MM:SS)
        #  往年记录: summary="2025-06-03 00:33:08" (YYYY-MM-DD HH:MM:SS)
        summary = str(r.get("summary", ""))
        date_str = ""
        if summary and "-" in summary:
            time_part = summary.split(" ")[0]  # 拿日期部分
            parts = time_part.split("-")
            if len(parts) >= 3:
                try:
                    d = dt_date(int(parts[0]), int(parts[1]), int(parts[2]))
                    date_str = d.isoformat()
                except ValueError:
                    pass
            elif len(parts) >= 2:
                try:
                    mm, dd = int(parts[0]), int(parts[1])
                    year = today.year
                    if mm > current_month + 1:  # 月份超前 → 去年
                        year -= 1
                    d = dt_date(year, mm, dd)
                    date_str = d.isoformat()
                except ValueError:
                    pass
        if not date_str:
            continue

        uid = str(r.get("_uid", ""))
        fname = r.get("fund_name", "")
        action = r.get("action", "")
        amount = r.get("amount", "")

        if not uid or not fname or not action:
            continue

        key = (date_str, uid, fname, action)
        if key in existing_keys:
            skipped += 1
            continue

        fund_id = r.get("_fund_id", "")
        clean = {
            "_user": r.get("_user", ""),
            "_uid": uid,
            "fund_name": fname,
            "action": action,
            "amount": amount,
            "_fund_id": fund_id,
        }
        if fund_id:
            clean["fund_code"] = fund_id.lstrip("1").zfill(6) if len(fund_id) >= 6 else ""
        if date_str not in existing:
            existing[date_str] = []
        existing[date_str].append(clean)
        existing_keys.add(key)
        added += 1

    if added == 0:
        logger.info("  [MERGE] no new records to add")
        return

    # 写回
    trading_by_date_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = trading_by_date_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(trading_by_date_path)

    logger.info("  [MERGE] %d added, %d skipped, total dates: %d, total records: %d"
                % (added, skipped, len(existing),
                   sum(len(v) for v in existing.values())))


def _aggregate_trading_signals(records):
    """Aggregate trading records into per-fund buy/sell counts.

    交易流水信号规则（增强版，区分建仓/加仓/定投）:
      - "买入" → 首次买入计2分，非首次计1.5分（通过用户历史判断）
      - "加仓" → 1分
      - "定投" → 0.5分（信号最弱，系统自动行为）
      - "卖出" or "减仓" or "止盈" → sell
      - 其他 → skip (调仓等)

    Returns: {
        "date": "...",
        "funds": {
            "fund_name": {
                "fund_name": "...",
                "buy_count": N,
                "weighted_buy_count": M,
                "sell_count": N,
                "buy_users": [...],
                "sell_users": [...],
                "first_buy_users": [...],
                "repeat_buy_users": [...],
                "ad_suspicion": bool,
                "records": [...],
            }
        }
    }
    """
    # 用户可信度权重（单吊0.5 / 集中1.5 / V大3.0）
    try:
        from tools.jd_finance_api import USER_WEIGHT as _UW
    except Exception:
        _UW = {}

    # 追踪每个用户对每只基金的操作历史
    user_fund_history = defaultdict(set)  # {user: {fund_name, ...}}
    fund_data = defaultdict(lambda: {
        "fund_name": "",
        "fund_code": "",
        "_fund_ids": set(),
        "buy_count": 0,
        "weighted_buy_count": 0.0,
        "sell_count": 0,
        "buy_users": set(),
        "sell_users": set(),
        "first_buy_users": set(),
        "repeat_buy_users": set(),
        "records": [],
    })

    for r in records:
        action = (r.get("action") or "").strip()
        fund_name = (r.get("fund_name") or "").strip()
        user = r.get("_user", "")
        detail = r.get("detail", "")
        amount = r.get("amount", "")
        fund_id = r.get("_fund_id", "")

        # Skip records without fund name or action
        if not fund_name or not action:
            continue

        # Classify action
        is_buy = any(kw in action for kw in ["买入", "加仓", "定投", "转换入"])
        is_sell = any(kw in action for kw in ["卖出", "减仓", "止盈", "转换出", "转换"])

        if not is_buy and not is_sell:
            continue

        key = fund_name
        fi = fund_data[key]
        fi["fund_name"] = fund_name
        if fund_id:
            fi["_fund_ids"].add(fund_id)

        if is_buy:
            fi["buy_count"] += 1
            if user:
                fi["buy_users"].add(user)

            # 判断建仓/加仓/定投，给予不同权重
            is_first_buy = user not in user_fund_history or fund_name not in user_fund_history[user]
            if "定投" in action:
                weight = 0.5
            elif "加仓" in action:
                weight = 1.0
                if user:
                    fi["repeat_buy_users"].add(user)
            elif "买入" in action:
                if is_first_buy:
                    weight = 2.0
                    if user:
                        fi["first_buy_users"].add(user)
                else:
                    weight = 1.5
                    if user:
                        fi["repeat_buy_users"].add(user)
            elif "转换入" in action:
                weight = 1.0
                if user:
                    fi["repeat_buy_users"].add(user)
            else:
                weight = 1.0

            # 用户可信度修正：单吊大佬(0.5)/集中(1.5)/V大(3.0)
            _uid = str(r.get("_uid", ""))
            user_w = _UW.get(_uid, 1.0)
            fi["weighted_buy_count"] += weight * user_w
            if user:
                user_fund_history[user].add(fund_name)

        if is_sell:
            fi["sell_count"] += 1
            if user:
                fi["sell_users"].add(user)

        fi["records"].append({
            "user": user,
            "action": action,
            "amount": amount,
            "detail": detail,
            "_fund_id": fund_id,
        })

    # 广告基嫌疑检测：多人同时首次买入同一基金
    result = {"date": _today_str(), "funds": {}}
    for key, fi in fund_data.items():
        total_buyers = len(fi["buy_users"])
        first_buyers = len(fi["first_buy_users"])
        ad_suspicion = False
        if total_buyers >= 4 and first_buyers >= max(2, total_buyers * 0.7):
            ad_suspicion = True

        result["funds"][key] = {
            "fund_name": fi["fund_name"],
            "fund_code": fi["fund_code"],
            "_fund_ids": sorted(fi["_fund_ids"]),
            "buy_count": fi["buy_count"],
            "weighted_buy_count": round(fi["weighted_buy_count"], 1),
            "sell_count": fi["sell_count"],
            "buy_users": sorted(fi["buy_users"]),
            "sell_users": sorted(fi["sell_users"]),
            "first_buy_users": sorted(fi["first_buy_users"]),
            "repeat_buy_users": sorted(fi["repeat_buy_users"]),
            "ad_suspicion": ad_suspicion,
            "records": fi["records"],
        }

    return result


# ── Step 3: Merge Signals ──────────────────────────────────────────────────


def _compute_merged_signals(trading_signals, holdings_diff):
    """Merge trading records signals + holdings diff signals.
    
    交易流水权重大于持仓快照，因为持仓可能买于很久之前（成本未知），
    而交易流水反映当下的判断。

    Net Signal Logic:
      strong_buy:  buy_count >= 3 AND sell_count == 0
      buy:         (buy_count >= 3 AND sell_count > 0) OR (buy_count >= 2 AND sell_count == 0)
      weak_buy:    buy_count >= 2 AND sell_count > 0
      strong_sell: sell_count >= 3 AND buy_count == 0
      sell:        sell_count >= 2 AND sell_count > buy_count + 1
      weak_sell:   sell_count >= 1 AND buy_count == 0
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

    # Index holdings diff signals by fund_name (primary) and fund_code (fallback)
    holdings_new_map = defaultdict(list)
    holdings_removed_map = defaultdict(list)
    # name → code cross-reference from holdings diff (code is available there)
    name_to_code = {}
    for item in holdings_diff.get("new_funds", []):
        holdings_new_map[item["fund_name"]].extend(item["users"])
        if item.get("fund_code"):
            name_to_code[item["fund_name"]] = item["fund_code"]
    for item in holdings_diff.get("removed_funds", []):
        holdings_removed_map[item["fund_name"]].extend(item["users"])
        if item.get("fund_code"):
            name_to_code[item["fund_name"]] = item["fund_code"]

    # Also build code→name reverse map from trading funds for cross-referencing
    code_to_name = {}
    for fname, tfi in trading_funds.items():
        code = tfi.get("fund_code", "")
        if code:
            code_to_name[code] = fname

    # Process all funds that appear in either trading records or holdings diff
    all_fund_names = set(trading_funds.keys()) | set(holdings_new_map.keys()) | set(holdings_removed_map.keys())

    for fname in sorted(all_fund_names):
        tf = trading_funds.get(fname, {})
        bc = tf.get("weighted_buy_count", tf.get("buy_count", 0))
        sc = tf.get("sell_count", 0)
        bu = tf.get("buy_users", [])
        su = tf.get("sell_users", [])
        hn = holdings_new_map.get(fname, [])
        hr = holdings_removed_map.get(fname, [])
        fund_code = name_to_code.get(fname, tf.get("fund_code", ""))

        # Net signal logic
        if bc >= 3 and sc == 0:
            net = "strong_buy"
            score = 5
        elif (bc >= 3 and sc > 0) or (bc >= 2 and sc == 0):
            net = "buy"
            score = 3
        elif bc >= 2 and sc > 0:
            net = "weak_buy"
            score = 2
        elif sc >= 3 and bc == 0:
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
            "fund_code": fund_code,
            "net_signal": net,
            "score": score,
            "buy_count": bc,
            "sell_count": sc,
            "buy_users": bu,
            "sell_users": su,
            "first_buy_users": tf.get("first_buy_users", []),
            "repeat_buy_users": tf.get("repeat_buy_users", []),
            "ad_suspicion": tf.get("ad_suspicion", False),
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


def _build_signal_report(merged_signals, status):
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

    # ── User profit rankings ──
    user_ranks = status.get("user_rankings", [])
    if user_ranks:
        lines.append("## 🏆 大佬持仓收益率排名")
        lines.append("")
        lines.append("| 排名 | 用户 | 加权收益率 | 信号权重 |")
        lines.append("|------|------|:---------:|:--------:|")
        weights = status.get("user_weights", {})
        for i, (name, rate) in enumerate(user_ranks, 1):
            w = weights.get(name, 1.0)
            w_str = "🔥×1.5" if w >= 1.5 else "×1.0" if w >= 1.0 else "⚠️×0.5"
            b = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else ""
            tag = f"{b}" if b else f"{i}"
            lines.append(f"| {tag} | {name} | {rate:+.1f}% | {w_str} |")
        lines.append("")
        lines.append("> *加权收益率=持仓金额加权平均。前3名信号权重×1.5，后3名×0.5。*")
        lines.append("")

    # ── Portfolio period returns ──
    port_returns = status.get("portfolio_returns", {})
    if port_returns:
        lines.append("## 📈 组合近期收益率")
        lines.append("")
        lines.append("| 用户 | 近1周 | 近1月 | 近3月 |")
        lines.append("|------|:-----:|:-----:|:-----:|")
        for name, rets in sorted(port_returns.items(), key=lambda x: x[1].get("近1月") or 0, reverse=True):
            w1 = f"{rets.get('近1周', '-')}%" if rets.get("近1周") is not None else "-"
            m1 = f"{rets.get('近1月', '-')}%" if rets.get("近1月") is not None else "-"
            m3 = f"{rets.get('近3月', '-')}%" if rets.get("近3月") is not None else "-"
            lines.append(f"| {name} | {w1} | {m1} | {m3} |")
        lines.append("")

    # ── Platform ranking ──
    fund_rank = status.get("fund_ranking", [])
    if fund_rank:
        lines.append("## 🌐 全平台收益率榜 Top 10")
        lines.append("")
        lines.append("| 排名 | 用户 | 收益率 | 总收益 |")
        lines.append("|------|------|:------:|-------:|")
        for u in fund_rank:
            lines.append(f"| #{u.get('rank', '')} | {u.get('name', '')} | {u.get('return_rate', '')} | {u.get('total_return', '')} |")
        lines.append("")

    # ── Cross-validation signals ──
    cross = status.get("cross_signals", [])
    if cross:
        lines.append("## 🔗 交叉验证信号（关注大佬 vs 全平台排名大佬）")
        lines.append("")
        lines.append("| 基金 | 关注大佬 | 排名大佬 | 信号 |")
        lines.append("|------|---------|---------|------|")
        for s in cross[:15]:  # Top 15
            f_users = ", ".join(s.get("followed_users", []))
            r_users = ", ".join(s.get("ranking_users", s.get("ranking_buyers", [])))
            sig = "持仓共识" if s.get("signal") == "cross_consensus" else "买入共识"
            lines.append(f"| {s.get('fund_name', '')[:30]} | {f_users} | {r_users} | {sig} |")
        if len(cross) > 15:
            lines.append(f"| ... | 共 {len(cross)} 个信号 | | |")
        lines.append("")

    # ── Daily news ──
    news = status.get("daily_news", [])
    if news:
        lines.append("## 📰 每日资讯")
        lines.append("")
        for n in news[:5]:
            lines.append(f"- **{n.get('author', '')}** {n.get('headline', '')[:60]}")
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


def _inject_fund_codes(trading_signals, all_holdings):
    """Inject 6-digit fund codes into aggregated trading signals from holdings data.

    Holdings have the real 6-digit fund codes; trading records only have 7-digit internal IDs.
    This builds a fund_name → fund_code cross-reference and injects it.
    """
    name_to_code = {}
    for user_name, items in all_holdings.items():
        for item in items:
            name = item.get("name", "")
            code = item.get("code", "")
            if name and code:
                name_to_code[name] = code

    # Also try 7-digit→6-digit conversion as fallback
    def _7to6(fid):
        return fid[1:] if len(fid) == 7 and fid.startswith("1") else ""

    injected = 0
    for fname, fdata in trading_signals.get("funds", {}).items():
        if fdata.get("fund_code"):
            continue  # already set
        code = name_to_code.get(fname, "")
        if not code:
            # Try _fund_ids: 7-digit → 6-digit
            for fid in fdata.get("_fund_ids", []):
                code = _7to6(fid)
                if code:
                    break
        if code:
            fdata["fund_code"] = code
            injected += 1

    if injected:
        logger.info(f"  [code] Injected {injected} fund codes")
    return trading_signals


# ── Bonus: User Profit Rate Rankings ───────────────────────────────────


def _compute_user_rankings(holdings_data):
    """Real return per user: total_profit / principal.
    principal = total_amount - total_profit."""
    rankings = []
    for name, items in holdings_data.items():
        total_amt = 0.0
        total_profit = 0.0
        for item in items:
            amt_str = item.get("amount", "0")
            profit_str = item.get("profit", "0")
            try:
                amt = float(amt_str.replace(",", "").replace("¥", "").replace("元", ""))
            except (ValueError, TypeError):
                amt = 0
            try:
                profit = float(profit_str.replace(",", "").replace("+", "").replace("¥", "").replace("元", ""))
            except (ValueError, TypeError):
                profit = 0
            total_amt += amt
            total_profit += profit
        principal = total_amt - total_profit
        rate = (total_profit / principal) * 100 if principal > 0 else 0.0
        rankings.append((rate, name))
    rankings.sort(reverse=True)
    return rankings


def _compute_portfolio_period_returns(holdings_data, periods=("近1周", "近1月", "近3月")):
    """Compute per-user portfolio-level period returns using weighted average.

    For each user, fetches fund performance data (近1周/近1月/近3月),
    then computes a weighted average based on holding amounts.

    Returns: {user_name: {"近1周": pct, "近1月": pct, "近3月": pct}, ...}
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed
    import tools.jd_finance_api as api

    # Step 1: Collect all unique fund codes with their user→amount mapping
    fund_amounts = {}  # code → {user: amount}
    user_totals = {}   # user → total_amount
    for name, items in holdings_data.items():
        total = 0.0
        for item in items:
            code = item.get("code", "")
            if not code:
                continue
            amt_str = item.get("amount", "0")
            try:
                amt = float(str(amt_str).replace(",", "").replace("¥", "").replace("元", ""))
            except (ValueError, TypeError):
                amt = 0
            if code not in fund_amounts:
                fund_amounts[code] = {}
            fund_amounts[code][name] = amt
            total += amt
        user_totals[name] = total

    unique_codes = list(fund_amounts.keys())
    logger.info(f"  Fetching performance for {len(unique_codes)} unique funds...")

    # Step 2: Fetch fund performance concurrently (thread-safe throttle active)
    fund_perf = {}  # code → {period: return_pct}

    def fetch_perf(code):
        try:
            result = get_fund_performance(code)
            if not result:
                return code, {}
            perf_map = {}
            for p in result.get("performance", []):
                period = p.get("period", "")
                ret = p.get("return")
                if period and ret is not None:
                    perf_map[period] = float(ret)
            return code, perf_map
        except Exception:
            return code, {}

    with ThreadPoolExecutor(max_workers=10) as pool:
        futs = {pool.submit(fetch_perf, c): c for c in unique_codes}
        done_count = 0
        for fut in as_completed(futs):
            code, perf = fut.result()
            fund_perf[code] = perf
            done_count += 1
            if done_count % 50 == 0:
                logger.info(f"    {done_count}/{len(unique_codes)} done")

    logger.info(f"  Performance data fetched for {len(fund_perf)} funds")

    # Step 3: Compute weighted average per user per period
    user_returns = {}
    for name, items in holdings_data.items():
        total_amt = user_totals.get(name, 0)
        if total_amt <= 0:
            continue
        period_sums = defaultdict(float)  # period → weighted_sum
        period_weights = defaultdict(float)  # period → total_weighted_amount

        for item in items:
            code = item.get("code", "")
            if not code or code not in fund_perf:
                continue
            amt_str = item.get("amount", "0")
            try:
                amt = float(str(amt_str).replace(",", "").replace("¥", "").replace("元", ""))
            except (ValueError, TypeError):
                amt = 0
            if amt <= 0:
                continue

            perf = fund_perf[code]
            for period in periods:
                ret = perf.get(period)
                if ret is not None:
                    period_sums[period] += ret * amt
                    period_weights[period] += amt

        user_returns[name] = {}
        for period in periods:
            if period_weights[period] > 0:
                user_returns[name][period] = round(period_sums[period] / period_weights[period], 2)
            else:
                user_returns[name][period] = None

    return user_returns


def _weight_signal_by_rank(user_rankings):
    """Top 3 users ×1.5, bottom 3 ×0.5, rest ×1.0"""
    weights = {}
    n = len(user_rankings)
    for i, (_, name) in enumerate(user_rankings):
        if i < min(3, n):
            weights[name] = 1.5
        elif i >= max(0, n - 3):
            weights[name] = 0.5
        else:
            weights[name] = 1.0
    return weights


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


# ── Ranking User Discovery ──


def _discover_ranking_users(cookies, max_count=10):
    """Fetch fund ranking top users across ALL sort types and time cycles.
    Returns: {numeric_uid: name} for new users to track this run"""
    import re as _re, urllib.request, urllib.parse
    from tools.jd_finance_api import _JD_BASE, _USER_AGENT

    # All combinations: 3 sort types × 5 time cycles = 15 API calls
    # rs=1(总收益) rs=2(收益率%) rs=3(年化)
    # tc=401(近1月) 402(近3月) 403(近6月) 404(近1年) 406(全部)
    time_cycles = ["401", "402", "403", "404", "406"]
    sort_types = ["1", "2", "3"]

    extra = {}
    known_uids = {str(k) for k in FOLLOWED_USERS.keys()}

    for tc in time_cycles:
        for rs in sort_types:
            body = {"lastId": None, "rankSortBy": rs, "timeCycle": tc}
            req_data = f"reqData={urllib.parse.quote(json.dumps(body))}".encode("utf-8")
            url = f"{_JD_BASE}/gw2/generic/redEnv001/h5/m/queryFundFirmOfferMultiRank"
            req = urllib.request.Request(url, data=req_data, headers={
                "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
                "User-Agent": _USER_AGENT,
            })
            req.add_header("Cookie", "; ".join(f"{k}={v}" for k, v in cookies.items()))
            try:
                resp = urllib.request.urlopen(req, timeout=10)
                raw_users = json.loads(resp.read()).get(
                    "resultData", {}).get("data", {}).get("fundRankList", [])
            except Exception:
                continue

            for u in raw_users:
                info = u.get("userInfo", {})
                jump = info.get("jumpData", {}).get("schemeUrl", "") or ""
                m = _re.search(r"jimu_user_info-(\d+)", jump)
                if m:
                    uid = m.group(1)
                    name = info.get("userName", f"排名_{uid}")
                    if uid not in known_uids and uid not in extra:
                        extra[uid] = name
                        logger.info(f"  [NEW] {name} (UID={uid})")
                if len(extra) >= max_count:
                    break
            if len(extra) >= max_count:
                break
        if len(extra) >= max_count:
            break

    if extra:
        logger.info(f"  → {len(extra)} new ranking users found")
    return extra


# ── Main ────────────────────────────────────────────────────────────────────


def main():
    offline = "--offline" in sys.argv
    _ensure_dirs()
    today = _today_str()

    logger.info(f"╔═══ AI Berkshire Auto Pipeline ═══╗")
    logger.info(f"  Date: {today}")
    is_td = is_workday(date.today())
    td_label = "[TradingDay]" if is_td else "[NonTradingDay]"
    logger.info(f"  Status: {td_label}")
    logger.info(f"  Mode: {'OFFLINE' if offline else 'NORMAL'}")
    logger.info(f"  Users: {len(FOLLOWED_USERS)} followed")
    logger.info(f"╚═══════════════════════════════════╝")

    # ── Step 0: Cookie ──
    logger.info("\n── Step 0: Auth ──")
    if offline:
        logger.info("  [SKIP] Offline mode, skipping auth")
        cookie_ok = False
        cookie_msg = "offline mode"
        cookies = None
    else:
        cookies, cookie_ok, cookie_msg = _bootstrap_cookie()
        check = "[OK]" if cookie_ok else "[--]"
        logger.info(f"  {check} {cookie_msg}")

    # ── Step 0b: Discover ranking users + dynamic pool ──
    _extra_users = {}
    _dynamic_pool = _load_dynamic_pool()
    if cookies and cookie_ok:
        logger.info("\n── Step 0b: Discovering ranking users ──")
        _extra_users = _discover_ranking_users(cookies)
        _added = _merge_dynamic_users(_dynamic_pool, _extra_users)
        if _added:
            logger.info(f"  → {_added} new ranking users added to dynamic pool")
        _all_tracked = _get_all_tracked_users(_dynamic_pool)
        logger.info(f"  Total tracked users: {len(_all_tracked)} ({len(FOLLOWED_USERS)} fixed + {len(_dynamic_pool)} dynamic)")
    else:
        _all_tracked = dict(FOLLOWED_USERS)

    # ── Step 1: Holdings ──
    previous = _load_json(SNAPSHOT_PATH, {})
    portfolio_returns = {}
    if cookies and cookie_ok:
        current_holdings = _fetch_all_holdings(cookies, _all_tracked)
        holdings_ok = current_holdings is not None
        user_rankings = _compute_user_rankings(current_holdings)
        user_weights = _weight_signal_by_rank(user_rankings)
        logger.info(f"  User rankings: {[(f'{n}: {r:.1f}%') for r,n in user_rankings[:5]]}...")
    else:
        logger.info("\n── Phase 1: Holdings (skipped, no cookie) ──")
        current_holdings = {}
        holdings_ok = False
        user_rankings = []
        user_weights = {}

    # ── My Holdings ──
    _my_holdings = []
    if cookies and cookie_ok:
        try:
            logger.info("\n── My holdings ──")
            result = get_user_holdings(cookies=cookies)
            my_raw = result.get("holdings", [])
            for h in my_raw:
                if isinstance(h, dict) and h.get("code"):
                    _my_holdings.append({"code": h["code"], "name": h.get("name", ""),
                                         "amount": h.get("amount", "0"), "profit_rate": h.get("profit_rate", "0")})
            logger.info(f"  [OK] {len(_my_holdings)} funds")
        except Exception as e:
            logger.warning(f"  [WARN] My holdings failed: {e}")

    # Compute diff
    prev_holdings = previous.get("holdings", previous) if isinstance(previous, dict) else {}
    holdings_diff = _compute_holdings_diff(prev_holdings, current_holdings)
    logger.info(f"  Diff: {len(holdings_diff['new_funds'])} new, {len(holdings_diff['removed_funds'])} removed")

    # ── Phase 1b + Phase 2: PARALLEL ──
    from concurrent.futures import ThreadPoolExecutor, as_completed

    def _compute_returns():
        if not (cookies and cookie_ok):
            return {}
        try:
            logger.info("\n── Phase 1b: Portfolio period returns (parallel) ──")
            ret = _compute_portfolio_period_returns(current_holdings)
            for name, rets in list(ret.items())[:3]:
                parts = [f"{p}={v}%" for p, v in rets.items() if v is not None]
                logger.info(f"  [{name}] {', '.join(parts)}")
            return ret
        except Exception as e:
            logger.warning(f"  [WARN] Portfolio returns failed: {e}")
            return {}

    def _fetch_trading():
        if not (cookies and cookie_ok):
            logger.info("\n── Phase 2: Trading records (skipped, no cookie) ──")
            return []
        logger.info("\n── Phase 2: Trading records (parallel) ──")
        return _fetch_all_trading_records(cookies, _all_tracked)

    with ThreadPoolExecutor(max_workers=2) as pool:
        f_returns = pool.submit(_compute_returns)
        f_trading = pool.submit(_fetch_trading)
        portfolio_returns = f_returns.result()
        all_records = f_trading.result()
        trading_ok = bool(all_records) or not (cookies and cookie_ok)

    # ── Merge new records into backtest data (for smart incremental tracking) ──
    if all_records:
        _merge_trading_to_backtest(all_records)

    trading_signals = _aggregate_trading_signals(all_records)
    logger.info(f"  Aggregated: {len(trading_signals['funds'])} funds with signals")
    crawl_ok = holdings_ok and trading_ok

    if current_holdings:
        trading_signals = _inject_fund_codes(trading_signals, current_holdings)

    # ── Phase 2b: Daily News ──
    daily_news = {"items": []}
    if cookies and cookie_ok:
        try:
            daily_news = get_daily_news(cookies=cookies)
            logger.info(f"  Daily news: {len(daily_news.get('items', []))} items")
        except Exception as e:
            logger.warning(f"  [WARN] Daily news failed: {e}")

    # ── Phase 2c: Fund Ranking + Cross-Validation ──
    fund_ranking = {"users": []}
    ranking_details = {}
    cross_signals = []
    if cookies and cookie_ok:
        try:
            # 1. Fetch ranking (get processed data for status.json)
            fund_ranking = get_fund_ranking(cookies=cookies)
            logger.info(f"  Fund ranking: {len(fund_ranking.get('users', []))} users")

            # 2. Fetch raw ranking to extract UIDs from jumpData
            import re as _re
            import urllib.request, urllib.parse
            from concurrent.futures import ThreadPoolExecutor, as_completed

            body = f"reqData={urllib.parse.quote(json.dumps({'lastId': None}))}".encode("utf-8")
            url = f"{_JD_BASE}/gw2/generic/redEnv001/h5/m/queryFundFirmOfferMultiRank"
            req = urllib.request.Request(url, data=body, headers={
                "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
                "User-Agent": _USER_AGENT,
            })
            req.add_header("Cookie", "; ".join(f"{k}={v}" for k, v in cookies.items()))
            resp = urllib.request.urlopen(req, timeout=15)
            raw_users = json.loads(resp.read()).get("resultData", {}).get("data", {}).get("fundRankList", [])

            # Extract UIDs
            def _extract_uid(user_info):
                jump = user_info.get("jumpData", {}).get("schemeUrl", "")
                match = _re.search(r"jimu_user_info-(\d+)", jump)
                return f"jimu_user_info-{match.group(1)}" if match else None

            # 3. Fetch holdings + records for all ranked users
            def _fetch_detail(name, uid):
                try:
                    h = get_user_holdings(target_uid=uid, cookies=cookies)
                    r = get_trading_records(target_uid=uid, cookies=cookies, today_only=False)
                    return name, uid, h.get("holdings", []), r.get("records", [])
                except Exception:
                    return name, uid, [], []

            fetch_jobs = []
            for u in raw_users:
                info = u.get("userInfo", {})
                uid = _extract_uid(info)
                if uid:
                    fetch_jobs.append((info.get("userName", ""), uid))

            logger.info(f"  Fetching details for {len(fetch_jobs)} ranked users...")
            with ThreadPoolExecutor(max_workers=10) as pool:
                futures = {pool.submit(_fetch_detail, name, uid): name for name, uid in fetch_jobs}
                for fut in as_completed(futures):
                    name, uid, holdings, records = fut.result()
                    ranking_details[uid] = {
                        "name": name,
                        "holdings_count": len(holdings),
                        "holdings": holdings,
                        "records_count": len(records),
                        "records": records,
                    }
                    logger.info(f"    [{name}] {len(holdings)} holdings, {len(records)} records")

            # 2b. Merge ranking records into backtest data (tag with _user and numeric _uid)
            _extra_records = []
            for uid_str, detail in ranking_details.items():
                numeric_id = uid_str.replace("jimu_user_info-", "")
                uname = detail["name"]
                for rec in detail.get("records", []):
                    rec["_user"] = uname
                    rec["_uid"] = numeric_id
                    _extra_records.append(rec)
            if _extra_records:
                _merge_trading_to_backtest(_extra_records)

            # 3. Cross-validation: find funds bought by both ranking users and followed users
            # Build fund code sets
            followed_funds = {}  # fund_code -> [user_names]
            for name, items in current_holdings.items():
                for item in items:
                    code = item.get("code", "")
                    if code:
                        if code not in followed_funds:
                            followed_funds[code] = []
                        followed_funds[code].append(name)

            ranking_funds = {}  # fund_code -> [user_names]
            for uid, detail in ranking_details.items():
                for item in detail.get("holdings", []):
                    code = item.get("code", "")
                    if code:
                        if code not in ranking_funds:
                            ranking_funds[code] = []
                        ranking_funds[code].append(detail["name"])

            # Find overlapping funds
            overlap_codes = set(followed_funds.keys()) & set(ranking_funds.keys())
            for code in overlap_codes:
                f_users = followed_funds[code]
                r_users = ranking_funds[code]
                fund_name = ""
                # Get fund name from holdings
                for item in current_holdings.get(f_users[0], []):
                    if item.get("code") == code:
                        fund_name = item.get("name", "")
                        break
                if len(r_users) >= 2:  # At least 2 ranking users hold this fund
                    cross_signals.append({
                        "fund_code": code,
                        "fund_name": fund_name,
                        "followed_users": f_users,
                        "ranking_users": r_users,
                        "signal": "cross_consensus",
                    })

            # 4. Find today's trades by ranking users that overlap with followed users' funds
            ranking_today_buys = {}  # fund_code -> [user_names]
            for uid, detail in ranking_details.items():
                for rec in detail.get("records", []):
                    action = rec.get("action", "")
                    if "买入" in action:
                        fname = rec.get("fund_name", "")
                        # Find fund code by name
                        for item in detail.get("holdings", []):
                            if item.get("name", "") == fname:
                                code = item.get("code", "")
                                if code:
                                    if code not in ranking_today_buys:
                                        ranking_today_buys[code] = []
                                    ranking_today_buys[code].append(detail["name"])
                                break

            # Cross-check today's buys with followed users' holdings
            for code, r_buyers in ranking_today_buys.items():
                if code in followed_funds and len(r_buyers) >= 2:
                    fund_name = ""
                    for item in current_holdings.get(followed_funds[code][0], []):
                        if item.get("code") == code:
                            fund_name = item.get("name", "")
                            break
                    cross_signals.append({
                        "fund_code": code,
                        "fund_name": fund_name,
                        "followed_users": followed_funds[code],
                        "ranking_buyers": r_buyers,
                        "signal": "ranking_buy_consensus",
                    })

            if cross_signals:
                logger.info(f"  Cross-validation: {len(cross_signals)} consensus signals")

        except Exception as e:
            logger.warning(f"  [WARN] Fund ranking failed: {e}")

    # ── Step 3: Merge Signals ──
    logger.info("\n── Step 3: Merging signals ──")
    merged = _compute_merged_signals(trading_signals, holdings_diff)
    signal_counts = defaultdict(int)
    for s in merged["signals"]:
        signal_counts[s["net_signal"]] += 1
    for k, v in sorted(signal_counts.items()):
        logger.info(f"  {k}: {v}")
    logger.info(f"  Total: {len(merged['signals'])} funds")

    # ── Step 3b: Five-Dimension Scoring ──
    logger.info("\n── Step 3b: Five-dimension scoring ──")
    _fund_scores = {}
    try:
        from tools.fund_scorer import score_fund, batch_score, _read_json as _fs_read_json
        from tools.fund_scorer import _get_index_valuation, _valuation_modifier

        # Load pipeline caches for smart money scoring
        _fs_trading = _fs_read_json(TRADING_PATH)
        _fs_snapshot = _fs_read_json(SNAPSHOT_PATH)
        _fs_diff = _fs_read_json(DIFF_PATH)

        # Load market valuation context
        _val_modifier = 0.0
        try:
            _val_data = _get_index_valuation()
            if _val_data:
                _val_modifier = _valuation_modifier(_val_data)
                logger.info(f"  估值修正: {_val_modifier:+.2f}")
        except Exception as e:
            logger.warning(f"  [WARN] Valuation fetch failed: {e}")

        # Get fund codes from merged signals + holdings
        _score_codes = set()
        for s in merged["signals"]:
            c = s.get("fund_code", "")
            if c:
                _score_codes.add(c)
        if current_holdings:
            for user_name, funds in current_holdings.items():
                if isinstance(funds, list):
                    for f in funds:
                        if isinstance(f, dict) and f.get("code"):
                            _score_codes.add(f["code"])

        _score_codes = sorted(_score_codes)
        logger.info(f"  Scoring {len(_score_codes)} funds...")

        _high_priority = [s["fund_code"] for s in merged["signals"]
                         if s.get("net_signal") in ("strong_buy", "buy", "strong_sell")
                         and s.get("fund_code")]
        _normal = [c for c in _score_codes if c not in _high_priority]

        def _score_one(code):
            try:
                _detail = get_fund_detail(code)
                _chart = get_fund_chart_data(code)
                _pts = _chart.get("chart_points", []) if _chart else []
                _fs = score_fund(
                    code, detail_data=_detail, chart_data=_pts,
                    trading_cache=_fs_trading, holdings_snapshot=_fs_snapshot,
                    holdings_diff=_fs_diff)
                if _fs is not None and _val_modifier != 0.0:
                    _fs.compute(valuation_modifier=_val_modifier)
                return code, _fs
            except Exception as e:
                logger.warning(f"  [WARN] Scoring {code} failed: {e}")
                return code, None

        with ThreadPoolExecutor(max_workers=10) as _pool:
            _futs = {_pool.submit(_score_one, _c): _c for _c in _high_priority}
            for _fut in as_completed(_futs):
                _c, _fs = _fut.result()
                if _fs is not None:
                    _fund_scores[_c] = _fs

        for _code in _normal:
            try:
                _fs = score_fund(
                    _code,
                    trading_cache=_fs_trading, holdings_snapshot=_fs_snapshot,
                    holdings_diff=_fs_diff)
                if _fs is not None and _val_modifier != 0.0:
                    _fs.compute(valuation_modifier=_val_modifier)
                _fund_scores[_code] = _fs
            except Exception:
                pass

        logger.info(f"  Scored: {len(_fund_scores)} funds")
        _verdicts = {}
        for _fs in _fund_scores.values():
            _verdicts[_fs.verdict] = _verdicts.get(_fs.verdict, 0) + 1
        for _k in ("buy", "watch", "pass"):
            logger.info(f"    {_k}: {_verdicts.get(_k, 0)}")

        # Attach fund_score to merged signals (use fund_score key, not score)
        for _s in merged["signals"]:
            _c = _s.get("fund_code", "")
            if _c in _fund_scores and _fund_scores[_c] is not None:
                _fs = _fund_scores[_c]
                _s["fund_score"] = {
                    "total": round(_fs.total, 2),
                    "verdict": _fs.verdict,
                    "quality": round(_fs.quality.score, 1) if _fs.quality else 0,
                    "cost": round(_fs.cost.score, 1) if _fs.cost else 0,
                    "manager": round(_fs.manager.score, 1) if _fs.manager else 0,
                    "momentum": round(_fs.momentum.score, 1) if _fs.momentum else 0,
                    "smart_money": round(_fs.smart_money.score, 1) if _fs.smart_money else 0,
                    "falsify": _fs.falsify_conditions,
                }

    except ImportError as e:
        logger.info(f"  [SKIP] fund_scorer not available: {e}")
    except Exception as e:
        logger.warning(f"  [WARN] Scoring step failed: {e}")

    # ── Step 3c: 持仓穿透风险分析 ──
    logger.info("\n── Step 3c: Penetration risk analysis ──")
    try:
        from tools.penetration_report import generate_penetration_report
        _pen_codes = list(_fund_scores.keys()) if _fund_scores else _score_codes
        _pen_report = generate_penetration_report(_pen_codes)
        if _pen_report:
            _sec = _pen_report.get("sector_concentration", {})
            logger.info(f"  行业分布: {', '.join([f'{s}={p}%' for s,p in sorted(_sec.items(), key=lambda x:-x[1])[:5]])}")
            _overlap = _pen_report.get("overlap_funds", {})
            logger.info(f"  重叠持股: {len(_overlap)}只股票被多只基金持有")
            # 附加到 merged signals
            merged["penetration"] = {
                "sector_concentration": _sec,
                "overlap_count": len(_overlap),
            }
    except Exception as e:
        logger.info(f"  [SKIP] Penetration analysis: {e}")

    # ── Step 3d: 行业分散检查 + 大佬排除 ──
    logger.info("\n── Step 3d: Portfolio constraints check ──")
    _sector_limit = 24  # 单行业上限%
    _sector_alerts = []

    # 检测每只信号的行业
    def _fsec(name):
        n = name or ""
        if "半导体" in n or "芯片" in n: return "半导体"
        if "科技" in n or "信息" in n or "互联网" in n: return "科技"
        if "医疗" in n or "医药" in n: return "医疗"
        if "消费" in n: return "消费"
        if "新能源" in n or "能源" in n: return "新能源"
        if "金融" in n or "银行" in n: return "金融"
        if "债券" in n or "债" in n: return "债券"
        if "混合" in n or "成长" in n or "价值" in n or "精选" in n: return "混合"
        if "指数" in n or "ETF" in n or "联接" in n: return "指数"
        return "其他"

    for _s in merged.get("signals", []):
        _s["sector"] = _fsec(_s.get("fund_name", ""))

    # 计算当前持仓行业占比
    _sector_alloc = {}
    if current_holdings:
        for _u, _fs in current_holdings.items():
            if isinstance(_fs, list):
                for _f in _fs:
                    if isinstance(_f, dict):
                        _sec = _fsec(_f.get("name", ""))
                        _val = _f.get("market_value", 0) or _f.get("cost_value", 0) or _f.get("amount", 0) or 0
                        if isinstance(_val, str):
                            _val = _parse_amount(_val)
                        _sector_alloc[_sec] = _sector_alloc.get(_sec, 0) + float(_val)

    _total = sum(_sector_alloc.values()) or 1
    _sector_pct = {s: v / _total * 100 for s, v in _sector_alloc.items()}

    logger.info(f"  当前行业分布: {', '.join([f'{s}={p:.0f}%' for s,p in sorted(_sector_pct.items(), key=lambda x:-x[1])[:6]])}")

    # 标记超出限制的信号
    for _s in merged.get("signals", []):
        _sec = _s.get("sector", "")
        _cur = _sector_pct.get(_sec, 0)
        if _cur >= _sector_limit and "买入" in _s.get("action", ""):
            _s["constraint_note"] = f"行业{_sec}已达{_cur:.0f}%, 超过{_sector_limit}%上限"
            _sector_alerts.append(_s)
            logger.info(f"  ⚠ {_s.get('fund_name','')} ({_sec}): {_s['constraint_note']}")

    # 执行大佬排分（如有持仓数据）
    try:
        from tools.big_player_ranker import calculate_scores, get_excluded_uids
        _bscores = calculate_scores(all_records.tolist() if hasattr(all_records,'tolist') else _fs_trading.get("records",[]),
                                     {}, {}, cutoff_date=today)
        _bexcluded = get_excluded_uids(_bscores)
        if _bexcluded:
            logger.info(f"  建议排除的大佬: {_bexcluded}")
    except Exception as e:
        logger.info(f"  [SKIP] Player ranking: {e}")

    # ── Step 4: Generate Report ──
    logger.info("\n── Step 4: Generating report ──")
    status = {
        "date": today,
        "timestamp": _now_str(),
        "cookie_ok": cookie_ok,
        "crawl_ok": crawl_ok,
        "holdings_ok": holdings_ok,
        "trading_ok": trading_ok,
        "message": cookie_msg,
        "user_rankings": [(n, round(r, 1)) for r, n in user_rankings],
        "user_weights": user_weights,
        "portfolio_returns": portfolio_returns,
        "daily_news": daily_news.get("items", []),
        "fund_ranking": fund_ranking.get("users", []),
        "ranking_details": ranking_details,
        "cross_signals": cross_signals,
        "ranking_note": "累计收益率（自跟踪以来）= 总收益 / 总成本 × 100%。portfolio_returns 为按持仓金额加权的近1周/近1月/近3月收益率。fund_ranking 为京东金融全平台收益率榜。",
        "is_trading_day": is_td,
        "penetration": merged.get("penetration", {}),
        "sector_alerts": _sector_alerts if _sector_alerts else [],
        "user_count": len(FOLLOWED_USERS) + len(_dynamic_pool),
        "my_holdings": _my_holdings if _my_holdings else [],
        "fund_scores": {
            _c: {
                "total": round(_fs.total, 2),
                "verdict": _fs.verdict,
                "quality": round(_fs.quality.score, 1) if _fs.quality else 0,
                "cost": round(_fs.cost.score, 1) if _fs.cost else 0,
                "manager": round(_fs.manager.score, 1) if _fs.manager else 0,
                "momentum": round(_fs.momentum.score, 1) if _fs.momentum else 0,
                "smart_money": round(_fs.smart_money.score, 1) if _fs.smart_money else 0,
            }
            for _c, _fs in _fund_scores.items()
        } if _fund_scores else {},
    }
    report = _build_signal_report(merged, status)

def _auto_expand_fund_data(cookies):
    """Step 6: 自动补齐基金净值数据 + 基金名映射。

    扫描 trading_by_date_fixed.json 中所有基金名，对新出现的基金：
    1. 尝试 fund_name_map.json 映射到代码
    2. 若代码不在 fund_charts.json 中 → 下载净值曲线
    """
    if not cookies:
        return

    trading_by_date_path = _PROJECT_ROOT / "backtest" / "data" / "trading_by_date_fixed.json"
    name_map_path = _PROJECT_ROOT / "data" / "fund_name_map.json"
    charts_path = _PROJECT_ROOT / "backtest" / "data" / "fund_charts.json"

    # 1. 加载现有数据
    name_map = _load_json(name_map_path, {})
    charts = _load_json(charts_path, {})

    # 2. 扫描所有基金名
    trading_data = _load_json(trading_by_date_path, {})
    all_names = set()
    for date_str, day_records in trading_data.items():
        for r in day_records:
            fn = r.get("fund_name", "")
            if fn:
                all_names.add(fn)

    # 3. 找未映射的基金名 → 用 API 搜索映射
    unmapped = all_names - set(name_map.keys())
    if unmapped:
        logger.info(f"\n── Step 6a: Mapping {len(unmapped)} new fund names ──")
        _auto_expand_name_map(list(unmapped), name_map, name_map_path)

    # 4. 找缺少净值数据的基金代码
    all_codes = set()
    for fn in all_names:
        code = name_map.get(fn, "")
        if code:
            all_codes.add(code)

    missing_charts = all_codes - set(charts.keys())
    if missing_charts:
        logger.info(f"\n── Step 6b: Downloading charts for {len(missing_charts)} new funds ──")
        new_charts = 0
        for code in sorted(missing_charts):
            try:
                chart = get_fund_chart_data(code, full_history=True, page_size=2000)
                if chart and chart.get("chartPoints"):
                    charts[code] = chart["chartPoints"]
                    new_charts += 1
            except Exception as e:
                logger.warning(f"    [{code}] chart failed: {e}")
        if new_charts:
            charts_path.write_text(json.dumps(charts, ensure_ascii=False), encoding="utf-8")
            logger.info(f"  → {new_charts} new fund charts saved (total: {len(charts)})")
    else:
        logger.info(f"\n── Step 6: Fund charts up to date ({len(charts)} funds) ──")


def _auto_expand_name_map(names_to_map, name_map, name_map_path):
    """通过基金搜索 API 自动补齐基金名→代码映射。"""
    added = 0
    for fn in sorted(names_to_map):
        try:
            # 使用京东基金搜索接口
            import urllib.request, urllib.parse
            keyword = urllib.parse.quote(fn[:20])
            url = f"https://ms.jr.jd.com/gw/generic/jj/h5/m/searchFund?keyword={keyword}&pageIndex=1&pageSize=5"
            req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
            resp = urllib.request.urlopen(req, timeout=10)
            data = json.loads(resp.read())
            results = data.get("resultData", {}).get("data", {}).get("fundList", [])
            if results:
                # 取第一个匹配
                name_map[fn] = results[0].get("fundCode", "")
                added += 1
        except Exception:
            pass
    if added:
        name_map_path.parent.mkdir(parents=True, exist_ok=True)
        name_map_path.write_text(json.dumps(name_map, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info(f"  → {added} new fund name→code mappings saved (total: {len(name_map)})")
    else:
        logger.info(f"  → No auto-mappings found for {len(names_to_map)} names")


    logger.info("\n── Step 5: Writing caches ──")
    holdings_snapshot = {
        "date": today,
        "timestamp": _now_str(),
        "holdings": current_holdings,
    }
    report_path = _write_caches(holdings_snapshot, holdings_diff, trading_signals, merged, report)
    _write_json(STATUS_PATH, status)

    # ── Score History ──
    if _fund_scores:
        _history_path = DATA_DIR / "fund_scores_history.jsonl"
        _history_entry = {
            "date": today,
            "scores": {
                _c: {"total": round(_fs.total, 2), "verdict": _fs.verdict}
                for _c, _fs in _fund_scores.items()
            }
        }
        with open(_history_path, "a", encoding="utf-8") as _fh:
            _fh.write(json.dumps(_history_entry, ensure_ascii=False) + "\n")
        logger.info(f"  History: {_history_path} ({len(_fund_scores)} funds)")
    logger.info(f"  Report: {report_path}")
    logger.info(f"  Status: {STATUS_PATH}\n")

    # ── Daily Snapshot (for LLM commentary) ──
    _snap = {
        "date": today,
        "summary": {
            "total_scored": len(_fund_scores),
            "buy_verdict": sum(1 for f in _fund_scores.values() if f.verdict == "buy"),
            "watch_verdict": sum(1 for f in _fund_scores.values() if f.verdict == "watch"),
            "strong_buy_signals": len([s for s in merged["signals"] if s.get("net_signal") == "strong_buy"]),
            "total_signals": len(merged["signals"]),
        },
        "top_scores": sorted(
            [{"code": c, "total": round(f.total, 2), "verdict": f.verdict}
             for c, f in _fund_scores.items()],
            key=lambda x: x["total"], reverse=True
        )[:10],
        "buy_signals": [
            {"code": s.get("fund_code", ""), "name": s.get("fund_name", ""),
             "buy_count": s.get("buy_count", 0), "score": s.get("fund_score", {}).get("total", 0)}
            for s in merged["signals"]
            if s.get("net_signal") in ("strong_buy", "buy") and s.get("fund_code")
        ][:10],
        "trending": [
            {"code": s.get("fund_code", ""), "delta": s.get("fund_score", {}).get("total", 0)}
            for s in merged["signals"]
            if s.get("fund_score", {}).get("falsify")
        ],
    }
    if _fund_scores:
        # Read previous scores from history
        _hist_file = DATA_DIR / "fund_scores_history.jsonl"
        if _hist_file.exists():
            try:
                _hist_lines = _hist_file.read_text("utf-8").strip().split("\n")
                if len(_hist_lines) >= 2:
                    _prev_snap = json.loads(_hist_lines[-2])
                    _snap["changes"] = {}
                    for code, fs in list(_fund_scores.items())[:5]:
                        prev_total = _prev_snap.get("scores", {}).get(code, {}).get("total")
                        if prev_total is not None:
                            _snap["changes"][code] = round(fs.total - prev_total, 2)
            except: pass
    _write_json(DATA_DIR / "auto" / "daily_snapshot.json", _snap)
    logger.info(f"  Snapshot: daily_snapshot.json")

    # ── Step 6: Auto-expand fund charts & fund_name_map ──
    _auto_expand_fund_data(cookies)

    # ── Summary ──
    check = "[OK]" if cookie_ok else "[--]"
    hk = "[OK]" if holdings_ok else "[--]"
    tk = "[OK]" if trading_ok else "[--]"
    logger.info(f"--- Pipeline Complete ---")
    logger.info(f"  Cookie:      {check}")
    logger.info(f"  Holdings:    {hk}")
    logger.info(f"  Trading:     {tk}")
    logger.info(f"  Signals:     {len(merged['signals'])} funds")
    logger.info(f"  Report:      {report_path}")

    # Exit code: 0 if data was fetched, 0 also if offline but report still generated
    # Only non-zero if something truly broken
    if not crawl_ok and not offline and cookies:
        # Had cookie but crawl failed partially
        logger.info("\n⚠️  Pipeline completed with partial failures (data may be incomplete)")
    elif not cookies and not offline:
        logger.info("\n❌ No cookie available. Set JD_COOKIES env or place cookies.json in data/jd_auth/")
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()
