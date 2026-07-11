#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
JD Finance Fund API Tool (zero external dependencies)

Features:
  - Cookie authentication (cookies.json + auto Playwright refresh)
  - 27 core API wrappers (holdings/trade/fund detail/rules/distribution/manager
    + NEW: index_block_info/fund_detail_pin/watchlist/player_trading_feed/index_detail)
  - Local cache (trade rules 30d / fund detail 7d / holdings 1d)
  - Rate limiting (0.15s interval, bypass in batch mode)
  - --offline fallback mode (cache only)

Dependencies: Python stdlib only (urllib/json/os/time/datetime/pathlib)
Auth: data/jd_auth/cookies.json (Playwright auto-capture or manual paste)

Usage:
  python tools/jd_finance_api.py --test
  python tools/jd_finance_api.py --holdings jimu_user_info-14345330
  python tools/jd_finance_api.py --fund-data 006105
  python tools/jd_finance_api.py --list-followed
  python tools/jd_finance_api.py --batch-fund 002891 018147 008253

  # NEW: industry-level valuation + investment signals
  python tools/jd_finance_api.py --index-block-info BK0447
  python tools/jd_finance_api.py --index-detail BK0447

  # NEW: logged-in fund detail (includes diagnosis: Sharpe/drawdown/volatility)
  python tools/jd_finance_api.py --fund-detail-pin 006105

  # NEW: watchlist + player trading feed
  python tools/jd_finance_api.py --watchlist
  python tools/jd_finance_api.py --player-trading-feed
"""

import argparse
import asyncio
import concurrent.futures
import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.request
import urllib.parse
from datetime import datetime, timedelta
from pathlib import Path

# ============================================================
# Path constants
# ============================================================
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DATA_DIR = _PROJECT_ROOT / "data"
_AUTH_DIR = _DATA_DIR / "jd_auth"
_COOKIES_PATH = _AUTH_DIR / "cookies.json"
_CACHE_DIR = _DATA_DIR / "fund_cache"
_SNAPSHOTS_DIR = _DATA_DIR / "fund_snapshots"
_JD_BASE = "https://ms.jr.jd.com"
_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# Known followed users (numeric_id -> name)
FOLLOWED_USERS = {
    "3546208": "\u84dd\u9cb8\u8dc3\u8d22",
    "14345330": "Z\u5148\u751f\u517b\u57fa",
    "16020895": "\u738b\u6674\u9633\u7684\u6d3b\u8d22\u4e4b\u8def",
    "2690580": "\u9ed1\u591c\u94f6\u7ffc",
    "4063754": "\u5357\u5c71\u9690\u58eb",
    "3642504": "\u8d5a\u81ea\u5df1\u8ba4\u77e5\u5185\u7684\u94b1",
    "3748946": "\u6674\u7a7a\u4e07\u91cc\u7406\u8d22",
    "10458335": "\u5c0f\u732b\u54aa\u7231\u9ec4\u91d1",
    "11979538": "\u5bb6\u5ead\u7684\u6e29\u6696",
    "4968958": "\u897f\u897f\u7684\u91d1\u7b97\u76d8",
    "11953905": "\u62db\u8d22\u5c0f\u732b",
}


# ============================================================
# Cookie / Auth Management
# ============================================================
def _load_cookies():
    if not _COOKIES_PATH.exists():
        return {}
    try:
        with open(_COOKIES_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if "cookies" in data:
            return {
                c["name"]: c["value"]
                for c in data["cookies"]
                if ".jd.com" in c.get("domain", "")
            }
        return data
    except (json.JSONDecodeError, OSError):
        return {}


def _save_cookies(cookies_dict):
    _AUTH_DIR.mkdir(parents=True, exist_ok=True)
    with open(_COOKIES_PATH, "w", encoding="utf-8") as f:
        json.dump(cookies_dict, f, ensure_ascii=False, indent=2)


def _verify_cookies(cookies):
    """Verify cookie by calling a real API that requires auth.
    If this API succeeds, cookie is good — period."""
    if not cookies:
        return False, None
    try:
        # Use the user holdings query as verification (it's a real auth-required endpoint)
        body = {
            "firmOfferType": "fund",
            "searchType": 2,
            "extParams": {"requestFrom": "pc"},
            "clientVersion": "9.9.9",
            "clientType": "android",
        }
        data = _api_form("gw2/generic/CreatorSer/h5/m/queryUserFundHoldingInfo", body, cookies)
        rd = data.get("resultData", {})
        items = rd.get("data", {}).get("fundHoldItemInfo", {}).get("itemList", [])
        if rd.get("code") == "0" and items is not None:
            return True, {"holdings_count": len(items)}
        # If we get no error and items is empty list (not None), cookie is still valid
        if items == []:
            return True, {"holdings_count": 0}
        return False, None
    except Exception:
        return False, None


async def _auto_login_with_playwright():
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        print("[ERROR] playwright not installed. Run: pip install playwright && playwright install chromium")
        return None

    print("\n=== JD Finance Auto Login ===")
    print("Opening browser. Please complete login (QR code or password).")

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=False,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = await browser.new_context(
            user_agent=_USER_AGENT, locale="zh-CN",
            viewport={"width": 1280, "height": 800},
        )
        await context.add_init_script(
            "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"
        )
        page = await context.new_page()
        await page.goto("https://jr.jd.com/", wait_until="domcontentloaded")
        print(">>> Waiting for login (checking every 5s, max 10 min)...")

        ok = False
        cookies = {}
        for i in range(120):
            await asyncio.sleep(5)
            try:
                all_cookies = await context.cookies("https://jd.com")
                jd_cookies = {
                    c["name"]: c["value"]
                    for c in all_cookies
                    if ".jd.com" in c.get("domain", "")
                }
                if jd_cookies.get("pt_key") and jd_cookies.get("pt_pin"):
                    valid, user_info = _verify_cookies(jd_cookies)
                    if valid:
                        cookies = jd_cookies
                        ok = True
                        print(f"  [OK] Login success (check #{i+1})")
                        break
            except Exception:
                pass
            if (i + 1) % 6 == 0:
                print(f"  ...still waiting ({(i+1)*5}s elapsed)")

        await browser.close()

        if ok:
            _save_cookies(cookies)
            print(f"Cookie saved to {_COOKIES_PATH}")
            return cookies
        else:
            print("Login timeout (10 min), exiting")
            return None


def _ensure_cookies(offline=False):
    cookies = _load_cookies()
    if offline:
        if cookies:
            return cookies
        print("[WARN] offline mode but no local cookie. Some features unavailable.")
        return {}
    if cookies:
        valid, _ = _verify_cookies(cookies)
        if valid:
            return cookies
        print("[INFO] Cookie expired, attempting auto-refresh...")
    try:
        cookies = asyncio.run(_auto_login_with_playwright())
    except Exception as e:
        print(f"[ERROR] Auto-login failed: {e}")
        cookies = None
    return cookies or {}


# ============================================================
# Cache Management
# ============================================================
def _cache_path(cache_type, key):
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    safe_key = key.replace("/", "_").replace("\\", "_")
    return _CACHE_DIR / f"{cache_type}_{safe_key}.json"


def _read_cache(cache_type, key, max_age_days):
    p = _cache_path(cache_type, key)
    if not p.exists():
        return None
    try:
        mtime = datetime.fromtimestamp(p.stat().st_mtime)
        if datetime.now() - mtime > timedelta(days=max_age_days):
            return None
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _write_cache(cache_type, key, data):
    p = _cache_path(cache_type, key)
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ============================================================
# API Request Core
# ============================================================
_last_request_time = 0
_BATCH_MODE = False  # set True to skip throttle for concurrent batch operations


def _throttle(delay=0.15):
    global _last_request_time
    if _BATCH_MODE:
        return  # skip throttle in concurrent batch mode
    elapsed = time.time() - _last_request_time
    if elapsed < delay:
        time.sleep(delay - elapsed)
    _last_request_time = time.time()


def _api_post(path, body, cookies=None, base_url=None):
    _throttle()
    url = f"{base_url or _JD_BASE}/{path}"
    payload = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=payload, headers={
        "Content-Type": "application/json",
        "User-Agent": _USER_AGENT,
        "Accept": "application/json",
    })
    if cookies:
        cookie_str = "; ".join(f"{k}={v}" for k, v in cookies.items())
        req.add_header("Cookie", cookie_str)
    try:
        resp = urllib.request.urlopen(req, timeout=15)
        return json.loads(resp.read())
    except Exception as e:
        return {"error": str(e)}


def _api_form(path, body_dict, cookies=None, base_url=None):
    _throttle()
    url = f"{base_url or _JD_BASE}/{path}"
    req_data = json.dumps(body_dict)
    payload = f"reqData={urllib.parse.quote(req_data)}".encode("utf-8")
    req = urllib.request.Request(url, data=payload, headers={
        "Content-Type": "application/x-www-form-urlencoded",
        "User-Agent": _USER_AGENT,
        "Accept": "application/json",
    })
    if cookies:
        cookie_str = "; ".join(f"{k}={v}" for k, v in cookies.items())
        req.add_header("Cookie", cookie_str)
    try:
        resp = urllib.request.urlopen(req, timeout=30)
        return json.loads(resp.read())
    except Exception as e:
        return {"error": str(e)}


# ============================================================
# Batch / Concurrent Operations (ThreadPoolExecutor)
# ============================================================
# Thread-safe versions that skip the global throttle for parallel use


def _api_post_batch(path, body):
    """No-throttle _api_post for concurrent use (throttle per-call in batch runner instead)."""
    url = f"{_JD_BASE}/{path}"
    payload = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=payload, headers={
        "Content-Type": "application/json",
        "User-Agent": _USER_AGENT,
        "Accept": "application/json",
    })
    try:
        resp = urllib.request.urlopen(req, timeout=15)
        return json.loads(resp.read())
    except Exception as e:
        return {"error": str(e)}


def _api_form_batch(path, body_dict):
    """No-throttle _api_form for concurrent use."""
    url = f"{_JD_BASE}/{path}"
    req_data = json.dumps(body_dict)
    payload = f"reqData={urllib.parse.quote(req_data)}".encode("utf-8")
    req = urllib.request.Request(url, data=payload, headers={
        "Content-Type": "application/x-www-form-urlencoded",
        "User-Agent": _USER_AGENT,
        "Accept": "application/json",
    })
    try:
        resp = urllib.request.urlopen(req, timeout=30)
        return json.loads(resp.read())
    except Exception as e:
        return {"error": str(e)}


def batch_get_fund_data(fund_codes, include=("profile", "perf", "trade_rules", "holdings", "manager"),
                        use_cache=False, max_workers=10, cookies=None):
    """Fetch ALL data endpoints for MULTIPLE funds concurrently.

    Uses getFundDetailPageInfo (one call per fund) instead of 3+ separate calls,
    reducing API requests by ~60%.

    Args:
        fund_codes: list of fund code strings
        include: which endpoints to fetch (subset of profile/perf/trade_rules/holdings/manager)
        use_cache: use cached data when available
        max_workers: concurrent thread count (default 10, safe up to ~40)
        cookies: JD auth cookies (loaded automatically if not provided)

    Returns:
        dict: {fund_code: {endpoint_name: result_or_None, ...}, ...}
    """
    # Enable batch mode to skip global throttle (threads manage their own timing)
    global _BATCH_MODE
    _BATCH_MODE = True

    def fetch_one(code):
        row = {"code": code}
        try:
            # Single API call replaces get_fund_profile + get_fund_performance + get_fund_holdings_distribution
            detail = get_fund_detail(code, use_cache=use_cache, cookies=cookies)
            if detail:
                if "profile" in include:
                    row["fund_profile"] = detail.get("profile")
                if "perf" in include:
                    row["fund_perf"] = detail.get("performance")
                if "holdings" in include:
                    row["holdings"] = detail.get("holdings_distribution")
                if "manager" in include:
                    row["manager"] = detail.get("manager")
            # trade_rules still needs a separate call (not in getFundDetailPageInfo)
            if "trade_rules" in include:
                row["trade_rules"] = get_fund_trade_rules(code, use_cache=use_cache)
        except Exception as e:
            row["error"] = str(e)
        return row

    results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
        fut_map = {pool.submit(fetch_one, code): code for code in fund_codes}
        for future in concurrent.futures.as_completed(fut_map):
            code = fut_map[future]
            try:
                row = future.result()
                results[code] = row
            except Exception as e:
                results[code] = {"code": code, "error": str(e)}

    _BATCH_MODE = False
    return results


# ============================================================
# API Methods: User Holdings & Trading
# ============================================================
def _text(v):
    """Extract text from JD API field (supports both old {'text':'x'} and new 'x' formats)."""
    if isinstance(v, dict):
        return v.get("text", "")
    return str(v) if v else ""


def get_user_holdings(target_uid=None, cookies=None, use_cache=False):
    cache_key = target_uid or "self"
    if use_cache:
        cached = _read_cache("holdings", cache_key, max_age_days=1)
        if cached:
            return cached

    if cookies is None:
        cookies = _ensure_cookies()
    body = {
        "firmOfferType": "fund",
        "searchType": 3 if not target_uid else 2,
        "extParams": {"requestFrom": "pc"},
        "clientVersion": "9.9.9",
        "clientType": "android",
    }
    if target_uid:
        body["targetUid"] = target_uid

    data = _api_form("gw2/generic/CreatorSer/h5/m/queryUserFundHoldingInfo", body, cookies)
    rd = data.get("resultData", {})
    items = []
    fund_info = rd.get("data", {}).get("fundHoldItemInfo", {}).get("itemList", [])
    for item in fund_info:
        items.append({
            "name": _text(item.get("fundName")),
            "code": _text(item.get("fundCode")),
            "amount": _text(item.get("amount", {}).get("text", "")),
            "profit_rate": _text(item.get("holdingProfitRate", {}).get("text", "")),
            "profit": _text(item.get("holdingProfit", {}).get("text", "")),
        })

    result = {"holdings": items, "raw": data}
    if use_cache and items:
        _write_cache("holdings", cache_key, result)
    return result


def get_user_fund_holding_info(target_uid, cookies=None):
    """获取大佬的基金持仓明细（含收益率、行业标签等）。

    Args:
        target_uid: "jimu_user_info-{numeric_id}"

    Returns: {fund_code: {name, amount, profit, profit_rate, yesterday_profit, sector}}
    """
    if cookies is None:
        cookies = _ensure_cookies()
    data = _api_form(
        "gw2/generic/CreatorSer/h5/m/queryUserFundHoldingInfo",
        {
            "targetUid": target_uid,
            "firmOfferType": "fund",
            "channel": "null",
            "channelfrom": "grouppc",
            "searchType": 2,
            "extParams": {"requestFrom": "pc", "inAppName": ""},
            "clientVersion": "9.9.9",
            "clientType": "android",
        },
        cookies=cookies,
    )
    rd = data.get("resultData", {})
    d = rd.get("data", {})
    items = d.get("fundHoldItemInfo", {}).get("itemList", [])
    result = {}
    for item in items:
        code = item.get("fundCode", "")
        if not code:
            continue
        result[code] = {
            "name": item.get("fundName", {}).get("text", ""),
            "amount": float(str(item.get("amount", {}).get("text", "0")).replace(",", "")),
            "profit": float(str(item.get("holdingProfit", {}).get("text", "0")).replace(",", "").replace("+", "")),
            "profit_rate": float(str(item.get("holdingProfitRate", {}).get("text", "0%")).replace("%", "").replace("+", "")),
            "yesterday_profit": float(str(item.get("yesterdayProfit", {}).get("text", "0")).replace(",", "").replace("+", "")),
            "sector": item.get("sectorTag", {}).get("text", ""),
        }

    # 提取期间收益率（近1周/近1月/近1年）
    pp = d.get("fundHoldInfo", {}).get("periodicProfit", {})
    period_returns = {}
    for period_key, period_label in [("weekly", "近1周"), ("monthly", "近1月"), ("yearly", "近1年")]:
        if period_key in pp:
            pct_text = pp[period_key].get("percentage", {}).get("text", "0%")
            try:
                period_returns[period_label] = float(pct_text.replace("%", "").replace("+", ""))
            except ValueError:
                period_returns[period_label] = 0.0

    return {"holdings": result, "period_returns": period_returns}


def get_trading_records(target_uid=None, size=20, cookies=None, max_pages=5, today_only=False):
    """Fetch trading records with pagination support.

    Iterates pages until end=True or max_pages reached.
    When today_only=True, filters records to only include today's trades.
    """
    if cookies is None:
        cookies = _ensure_cookies()
    all_records = []
    last_id = ""
    is_end = False
    page = 1

    # Precompute today's MM-DD prefix for filtering
    _today_prefix = ""
    if today_only:
        from datetime import date
        _today_prefix = date.today().strftime("%m-%d")

    while not is_end and page <= max_pages:
        body = {
            "pageId": "11568",
            "pageType": "11568",
            "buildCodes": ["common", "feeds", "errorConfig", "topData"],
            "pageSize": size,
            "busData": {
                "isFirstFeed": page == 1,
                "pageSize": str(size),
                "lastId": last_id,
                "end": False,
            },
            "extParams": {"requestFrom": "pc"},
            "pageNum": page,
            "clientVersion": "9.9.9",
            "clientType": "android",
        }
        if target_uid:
            body["extParams"]["targetUid"] = target_uid

        data = _api_form("gw2/generic/aladdin/h5/m/getPageMutilData?pageId=11568", body, cookies)
        rd = data.get("resultData", {})

        # Try new format (resultList) first, fallback to old format (data.data)
        feed_list = rd.get("resultList", [])
        new_format = bool(feed_list)
        if not new_format:
            feed_list = rd.get("data", {}).get("data", [])

        # Update pagination state
        if new_format:
            resp_bus = rd.get("busData", {})
        else:
            resp_bus = rd.get("data", {}).get("busData", {})
        last_id = resp_bus.get("lastId", "")
        is_end = resp_bus.get("end", True)

        # Track if any records on this page are from today
        page_has_today = False

        for feed in feed_list:
            template = feed.get("templateData", {})
            if new_format:
                # New format: transactionData
                trans = template.get("transactionData", {})
                card = trans.get("cardHead", {})
                fund1 = trans.get("fundData", {}).get("fund1", {})
                time_str = _text(card.get("tradeTime"))
                amount_str = _text(card.get("tradeAmount"))
                fund_name = _text(fund1.get("fundName"))
                fund_id = fund1.get("fundId", "")
                # tradeType: 1=buy, 2=sell, 3=conversion, etc.
                ttype = trans.get("tradeType", "")
                action = "买入" if ttype == "1" else "卖出" if ttype == "2" else "转换" if ttype == "3" else f"类型{ttype}"
                rec_date = time_str[:5] if time_str and len(time_str) >= 5 else ""
                if today_only and rec_date != _today_prefix:
                    continue  # skip old records
                if rec_date == _today_prefix:
                    page_has_today = True
                all_records.append({
                    "user": "",
                    "summary": time_str,
                    "action": action,
                    "detail": f"基金{fund_id}",
                    "fund_name": fund_name,
                    "amount": amount_str,
                    "_fund_id": fund_id,
                    "_date_prefix": rec_date,
                })
            else:
                # Old format: tradeRecordData
                trade = template.get("contentData", {}).get("tradeRecordData", [])
                user_name = template.get("titleData", {}).get("title1", {}).get("text", "")
                summary = template.get("contentData", {}).get("contentTitle2", {}).get("text", "")
                for t in trade:
                    all_records.append({
                        "user": user_name,
                        "summary": summary,
                        "action": t.get("title1", {}).get("text", ""),
                        "detail": t.get("title2", {}).get("text", ""),
                        "fund_name": t.get("title3", {}).get("text", ""),
                        "amount": t.get("title4", {}).get("text", ""),
                        "_fund_id": "",
                        "_date_prefix": "",
                    })

        # Stop early if today_only and this page had no today records (all older)
        if today_only and not page_has_today:
            break

        page += 1

    # If today_only, final filter pass to ensure no stray old records
    if today_only:
        all_records = [r for r in all_records if r.get("_date_prefix", "") == _today_prefix]

    return {"records": all_records}


# ============================================================
# API Methods: Fund Details (no login required)
# ============================================================
def _pct(s):
    if not s:
        return 0.0
    return float(str(s).replace("%", "").replace("\uff08\u6bcf\u5e74\uff09", "").replace("(每年)", "").strip() or 0)


def _amt(s):
    if not s or "\u65e0\u9650\u989d" in str(s):
        return float("inf")
    s = str(s)
    if "\u4e07" in s:
        return float(s.replace("\u4e07", "").replace("\u5143", "").strip()) * 10000
    if "\u4ebf" in s:
        return float(s.replace("\u4ebf", "").replace("\u5143", "").strip()) * 100000000
    return float(s.replace("\u5143", "").strip() or 0)


def get_fund_trade_rules(fund_code, use_cache=False):
    if use_cache:
        cached = _read_cache("trade_rules", fund_code, max_age_days=30)
        if cached:
            return cached

    data = _api_post("gw/generic/jj/h5/m/getFundTradeRulesPageInfo", {"fundCode": fund_code})
    rd = data.get("resultData", {})
    datas = rd.get("datas", {})
    if not datas:
        return None

    pr = datas.get("purchaseRule", {})
    rr = datas.get("redeemRule", {})

    purchase_fees = pr.get("purchaseFeeRatio", [])
    purchase_fee = _pct(purchase_fees[0].get("discountedRate", "0")) if purchase_fees else 0
    purchase_fee_orig = _pct(purchase_fees[0].get("rate", "0")) if purchase_fees else 0

    redeem_fees = []
    for item in rr.get("redeemFeeRatio", []):
        redeem_fees.append({
            "rate": _pct(item.get("rate", "0")),
            "interval": item.get("divideIntervalDesc", ""),
        })

    process = pr.get("purchaseProcess", [])
    buy_date = ""
    confirm_date = ""
    for step in process:
        if step.get("title") == "\u4e70\u5165":
            buy_date = step.get("info", "")
        elif step.get("title") == "\u786e\u8ba4\u4efd\u989d":
            confirm_date = step.get("info", "")

    result = {
        "fund_code": fund_code,
        "buy_date": buy_date,
        "confirm_date": confirm_date,
        "manage_fee": _pct(pr.get("manageFeeRatio", "0")),
        "custody_fee": _pct(pr.get("depositFeeRatio", "0")),
        "sale_fee": _pct(pr.get("saleServiceFeeRatio", "0")),
        "purchase_fee": purchase_fee,
        "purchase_fee_original": purchase_fee_orig,
        "day_limit": _amt(pr.get("dayLimitAmount", "\u65e0\u9650\u989d")),
        "min_purchase": _amt(pr.get("purchaseMinAmount", "0")),
        "redeem_fees": redeem_fees,
        "purchase_status": pr.get("purchaseStatus", ""),
        "redeem_status": rr.get("redeemStatus", ""),
    }
    if use_cache:
        _write_cache("trade_rules", fund_code, result)
    return result


def get_fund_holdings_distribution(fund_code, report_date=None, use_cache=False):
    cache_key = f"{fund_code}_{report_date or 'latest'}"
    if use_cache:
        cached = _read_cache("fund_holdings", cache_key, max_age_days=7)
        if cached:
            return cached

    body = {"fundCode": fund_code}
    if report_date:
        body["reportDate"] = report_date

    data = _api_post("gw/generic/jj/h5/m/getFundInvestmentDistributionPageInfo", body)
    rd = data.get("resultData", {})
    datas = rd.get("datas", {})
    if not datas:
        return None

    dist = datas.get("investmentDistribution", {})
    allocation = {}
    for item in dist.get("proportionList", []):
        allocation[item.get("name", "")] = float(item.get("fundValue", 0))

    top_stocks = []
    for stock in dist.get("stock", [])[:10]:
        top_stocks.append({
            "name": stock.get("name", ""),
            "code": stock.get("code", ""),
            "ratio": stock.get("ratio", ""),
            "change": stock.get("holdingSharesChange", ""),
        })

    result = {
        "fund_code": fund_code,
        "report_date": report_date,
        "total_asset": dist.get("totalAsset", 0),
        "allocation": allocation,
        "top_stocks": top_stocks,
        "invest_date": dist.get("investDate", ""),
    }
    if use_cache:
        _write_cache("fund_holdings", cache_key, result)
    return result


def get_fund_profile(fund_code, use_cache=False):
    if use_cache:
        cached = _read_cache("fund_profile", fund_code, max_age_days=7)
        if cached:
            return cached

    data = _api_post("gw/generic/jj/h5/m/getFundDetailProfilePageInfo", {"fundCode": fund_code})
    rd = data.get("resultData", {})
    datas = rd.get("datas", {})
    if not datas:
        return None

    info_map = {}
    for item in datas.get("fundInfo", []):
        info_map[item.get("title", "")] = item.get("value", "")

    company = datas.get("companyInfo", {})
    verbose_map = {}
    for item in datas.get("fundVerbose", []):
        verbose_map[item.get("title", "")] = item.get("value", "").strip()

    result = {
        "fund_code": fund_code,
        "full_name": info_map.get("\u57fa\u91d1\u5168\u79f0", ""),
        "established": info_map.get("\u6210\u7acb\u65e5\u671f", ""),
        "scale": info_map.get("\u8d44\u4ea7\u89c4\u6a21", ""),
        "manager_company": company.get("companyName", ""),
        "custodian": info_map.get("\u57fa\u91d1\u6258\u7ba1\u4eba", ""),
        "investment_target": verbose_map.get("\u6295\u8d44\u76ee\u6807", ""),
        "investment_strategy": verbose_map.get("\u6295\u8d44\u7b56\u7565", ""),
    }
    if use_cache:
        _write_cache("fund_profile", fund_code, result)
    return result


def get_fund_performance(fund_code, use_cache=False):
    if use_cache:
        cached = _read_cache("fund_perf", fund_code, max_age_days=7)
        if cached:
            return cached

    data = _api_post("gw/generic/jj/h5/m/getFundHistoryPerformancePageInfo", {"fundCode": fund_code})
    rd = data.get("resultData", {})
    datas = rd.get("datas", {})
    if not datas:
        return None

    perf_list = []
    for item in datas.get("performanceList", []):
        rank_str = item.get("rank", "")
        try:
            parts = rank_str.split("/")
            rank_pct = int(parts[0]) / int(parts[1]) if len(parts) == 2 else None
        except Exception:
            rank_pct = None
        perf_list.append({
            "period": item.get("name", ""),
            "return": float(item.get("rate", 0)) if item.get("rate") else None,
            "rank": rank_str,
            "rank_pct": rank_pct,
        })

    result = {"fund_code": fund_code, "performance": perf_list}
    if use_cache:
        _write_cache("fund_perf", fund_code, result)
    return result


def get_fund_detail(fund_code, use_cache=False, cookies=None):
    """One-call replacement for get_fund_profile + get_fund_performance + get_fund_holdings_distribution.

    Calls getFundDetailPageInfo which returns everything in a single request.
    Note: this endpoint requires auth cookies (unlike the individual endpoints).

    Returns dict with keys: profile, performance, holdings_distribution, manager, chart.
    """
    if use_cache:
        cached = _read_cache("fund_detail", fund_code, max_age_days=1)
        if cached:
            return cached

    if cookies is None:
        cookies = _ensure_cookies()
    data = _api_post("gw/generic/jj/h5/m/getFundDetailPageInfo", {"fundCode": fund_code}, cookies=cookies)
    rd = data.get("resultData", {})
    datas = rd.get("datas", {})
    if not datas:
        return None

    # --- Profile (replaces get_fund_profile) ---
    header = datas.get("headerOfItem", {})
    profile_section = datas.get("fundProfileOfItem", {})
    profile = {
        "fund_code": fund_code,
        "full_name": header.get("fundName", ""),
        "fund_type": header.get("fundTypeName", ""),
        "risk_level": header.get("riskLevel"),
        "morningstar_rating": header.get("morningstarRating"),
        "established": profile_section.get("establishedDate", ""),
        "scale": profile_section.get("fundScale", ""),
        "manager_company": profile_section.get("company_name", ""),
        "company_scale": profile_section.get("companyManageScale", ""),
        "manage_count": profile_section.get("manageNumber"),
        "is_for_sale": datas.get("isForSale", False),
        "wealth_rank": header.get("wealthRank", ""),
    }

    # --- Performance (replaces get_fund_performance) ---
    perf_section = datas.get("performanceOfItem", {})
    hist_perf = perf_section.get("historyPerformanceMap", {})
    perf_list = []
    for item in hist_perf.get("historyPerformanceList", []):
        rank_str = item.get("rank", "")
        try:
            parts = rank_str.split("/")
            rank_pct = int(parts[0]) / int(parts[1]) if len(parts) == 2 else None
        except Exception:
            rank_pct = None
        perf_list.append({
            "period": item.get("name", ""),
            "return": float(item.get("rate", 0)) if item.get("rate") else None,
            "avg": float(item.get("avg", 0)) if item.get("avg") else None,
            "rank": rank_str,
            "rank_pct": rank_pct,
        })

    # Annual returns
    year_perf = perf_section.get("yearPerformanceMap", {})
    year_list = []
    for item in year_perf.get("yearPerformanceList", []):
        year_list.append({
            "year": item.get("year", ""),
            "return": float(item.get("rate", 0)) if item.get("rate") else None,
            "avg": float(item.get("avg", 0)) if item.get("avg") else None,
        })

    # DCA (定投) returns
    aip_perf = perf_section.get("aipPerformanceMap", {})
    aip_list = []
    for item in aip_perf.get("aipPerformanceList", []):
        pt_rate = item.get("ptRate", "--")
        aip_list.append({
            "period": item.get("name", ""),
            "return": float(pt_rate) if pt_rate and pt_rate != "--" else None,
        })

    performance = {
        "fund_code": fund_code,
        "performance": perf_list,
        "year_performance": year_list,
        "aip_performance": aip_list,
    }

    # --- Holdings Distribution (replaces get_fund_holdings_distribution) ---
    dist_section = datas.get("investmentDistributionNewOfItem", {})
    dist = dist_section.get("investmentDistribution", dist_section)
    allocation = {}
    for item in dist.get("proportionList", []):
        allocation[item.get("name", "")] = float(item.get("fundValue", 0))

    top_stocks = []
    for stock in dist.get("stock", [])[:10]:
        top_stocks.append({
            "name": stock.get("name", ""),
            "code": stock.get("code", ""),
            "ratio": stock.get("ratio", ""),
            "change": stock.get("holdingSharesChange", ""),
            "rate": stock.get("rate", ""),
            "industry": stock.get("industryName", ""),
            "quarters_held": stock.get("positionQuarters", ""),
        })

    holdings_dist = {
        "fund_code": fund_code,
        "report_date": dist.get("investDate", ""),
        "total_asset": dist.get("totalAsset", 0),
        "allocation": allocation,
        "top_stocks": top_stocks,
        "stock_nav_ratio": dist.get("stockNavRatio", ""),
        "invest_date": dist.get("investDate", ""),
    }

    # --- Manager (replaces get_fund_manager) ---
    mgr_section = datas.get("fundManagerOfItem", {})
    managers = []
    for m in mgr_section.get("managerInfoList", []):
        managers.append({
            "name": m.get("managerName", ""),
            "year_performance": m.get("yearPerformance", ""),
            "employ_performance": m.get("employPerformance", ""),
            "manage_scale": m.get("manageScale", ""),
            "employment_date": m.get("employmentDate", ""),
            "accession_date": m.get("accessionDateDesc", ""),
        })
    manager = {"fund_code": fund_code, "managers": managers}

    # --- Chart (replaces get_fund_chart_data) ---
    chart_section = datas.get("trendChartOfItem", {})
    chart = {
        "fund_code": fund_code,
        "income_trend": chart_section.get("incomeTrendTip", ""),
        "chart_points": chart_section.get("majorChartPointList", []),
        "index_name": chart_section.get("indexName", ""),
    }

    # --- Notices (fund announcements) ---
    notices = []
    for n in datas.get("noticeList", []):
        notices.append({
            "date": n.get("noteDate", ""),
            "title": n.get("noticeTitle", ""),
            "url": n.get("noticeHtmlUrl", ""),
        })

    # --- Fee info from buttonTips ---
    btn_tips = datas.get("bottomButtonOfItem", {}).get("buttonTips", {})
    fee_info = {
        "buy_fee": btn_tips.get("leftDescHoldCard", ""),
        "buy_fee_new": btn_tips.get("leftDescNew", ""),
        "min_purchase": btn_tips.get("rightDescNew", ""),
    }

    # --- Recent quotations (近1年涨跌幅 etc) ---
    quotations = []
    for q in header.get("quotationsMap", []):
        quotations.append({
            "name": q.get("name", ""),
            "value": q.get("value", ""),
        })

    # --- NAV History (daily net values, separate API call) ---
    nav_history = []
    try:
        nav_data = _api_post("gw/generic/jj/h5/m/getFundHistoryNetValuePageInfo",
                             {"fundCode": fund_code}, cookies=cookies)
        nav_list = nav_data.get("resultData", {}).get("datas", {}).get("netValueList", [])
        for n in nav_list:
            nav_history.append({
                "date": n.get("date", ""),
                "nav": n.get("netValue", ""),
                "daily_return": n.get("dailyProfit", ""),
                "total_nav": n.get("totalNetValue", ""),
            })
    except Exception:
        pass

    # --- Profit History (daily profit, separate API call) ---
    profit_history = []
    try:
        profit_data = _api_post("gw/generic/jj/h5/m/getFundHistoryProfitPageInfo",
                                {"fundCode": fund_code}, cookies=cookies)
        profit_list = profit_data.get("resultData", {}).get("datas", {}).get("netValueList", [])
        for p in profit_list:
            profit_history.append({
                "date": p.get("date", ""),
            })
    except Exception:
        pass

    result = {
        "fund_code": fund_code,
        "profile": profile,
        "performance": performance,
        "holdings_distribution": holdings_dist,
        "manager": manager,
        "chart": chart,
        "notices": notices,
        "fee_info": fee_info,
        "quotations": quotations,
        "nav_history": nav_history,
        "profit_history": profit_history,
    }
    if use_cache:
        _write_cache("fund_detail", fund_code, result)
    return result


def get_fund_manager(fund_code):
    data = _api_post("gw/generic/jj/h5/m/getFundManagerListPageInfo", {"fundCode": fund_code})
    rd = data.get("resultData", {})

    managers = []
    for m in rd.get("currentManagers", []):
        manager_id = str(m.get("managerId", ""))
        tenure = ""
        other_info = m.get("managerOtherInfoList", [])
        if other_info:
            tenure = other_info[0].get("value", "")
        managers.append({
            "id": manager_id,
            "name": m.get("managerName", ""),
            "tenure": tenure,
        })

    for m in managers:
        if m["id"]:
            detail = get_manager_detail(m["id"])
            if detail:
                m.update(detail)

    return {"fund_code": fund_code, "managers": managers}


def get_manager_detail(manager_id):
    data = _api_post("gw/generic/jj/h5/m/getFundManagerDetailPageInfo", {"managerId": manager_id})
    rd = data.get("resultData", {})
    datas = rd.get("datas", {})
    if not datas:
        return None

    radar = {}
    for item in datas.get("radarData", []):
        radar[item.get("name", "")] = float(item.get("score", 0))

    return {"radar": radar, "total_score": float(datas.get("totalScore", 0))}


def get_followed_users_from_circle(cookies=None, max_pages=3):
    """Discover active users from JD Finance investment circle.

    Args:
        cookies: auth cookies
        max_pages: number of feed pages to scan (default 3)

    Returns:
        list of {"name": str, "uid": str, "summary": str}
    """
    if cookies is None:
        cookies = _ensure_cookies()
    import urllib.parse as _up

    users = []
    seen = set()
    last_id = None

    for _ in range(max_pages):
        body = {
            "tagId": 112, "contentId": "2689640",
            "iosType": "", "extParams": {"requestFrom": "h5"},
        }
        if last_id:
            body["lastId"] = last_id
        req_data = _up.quote(json.dumps(body, ensure_ascii=False))
        url = f"{_JD_BASE}/gw/generic/jimu/h5/m/feedFlowOfCircle?reqData={req_data}"
        req = urllib.request.Request(url, headers={
            "User-Agent": _USER_AGENT, "Accept": "application/json",
        })
        if cookies:
            cookie_str = "; ".join(f"{k}={v}" for k, v in cookies.items())
            req.add_header("Cookie", cookie_str)
        try:
            resp = urllib.request.urlopen(req, timeout=15)
            data = json.loads(resp.read())
        except Exception as e:
            return users or {"error": str(e)}

        rd = data.get("resultData", {}).get("data", {})
        items = rd.get("resultList", [])
        if not items:
            break

        for feed in items:
            td = feed.get("templateData", {})
            # Try multiple paths to find user info
            cd = td.get("contentData", {})
            uid = None
            user_name = ""
            summary = ""

            # Path 1: repostData has jumpData with user info
            rd2 = cd.get("repostData", {}) or cd.get("fundTrendData", {})
            jump = rd2.get("jumpData", {}).get("jumpUrl", "")
            import re as _re
            m = _re.search(r"contentId=(\d+)", jump)
            if m:
                uid = f"content_{m.group(1)}"

            # Path 2: look for description/title text
            desc = cd.get("description", {}).get("text", "")
            title = cd.get("title", {}).get("text", "")
            if desc:
                user_name = desc[:30]
            if title:
                summary = title[:100]

            if uid and uid not in seen:
                seen.add(uid)
                users.append({"name": user_name, "uid": uid, "summary": summary})

        last_id = rd.get("lastId")

    return users


# ============================================================
# Fund Notices & Daily News
# ============================================================
def get_fund_notices(fund_code, cookies=None, use_cache=False):
    """Fetch fund announcements from getFundNoticesPageInfo."""
    if use_cache:
        cached = _read_cache("fund_notices", fund_code, max_age_days=1)
        if cached:
            return cached

    if cookies is None:
        cookies = _ensure_cookies()
    data = _api_post("gw/generic/jj/h5/m/getFundNoticesPageInfo",
                     {"fundCode": fund_code}, cookies=cookies)
    rd = data.get("resultData", {})
    datas = rd.get("datas", {})
    notices = []
    for n in datas.get("noticeList", []):
        notices.append({
            "date": n.get("noteDate", ""),
            "title": n.get("noticeTitle", ""),
            "url": n.get("noticeHtmlUrl", ""),
            "type": n.get("noticeTypeCode", ""),
        })
    result = {"fund_code": fund_code, "notices": notices}
    if use_cache and notices:
        _write_cache("fund_notices", fund_code, result)
    return result


def get_daily_news(cookies=None, use_cache=False):
    """Fetch official fund news from JD Finance community (pageId=11575).

    Returns fund company posts and financial media content.
    """
    if use_cache:
        cached = _read_cache("daily_news", "main", max_age_days=0)
        if cached:
            return cached

    if cookies is None:
        cookies = _ensure_cookies()

    body = {
        "pageId": "11575", "pageType": "11575",
        "buildCodes": ["common", "feeds", "errorConfig", "topData"],
        "pageSize": 20,
        "busData": {"isFirstFeed": True, "pageSize": "20", "lastId": "", "end": False},
        "extParams": {"requestFrom": "pc"},
        "pageNum": 1, "clientVersion": "9.9.9", "clientType": "android",
    }
    data = _api_form("gw2/generic/aladdin/h5/m/getPageMutilData?pageId=11575",
                     body, cookies=cookies)
    rd = data.get("resultData", {})
    feeds = rd.get("resultList", []) or rd.get("data", {}).get("data", [])

    items = []
    for feed in feeds:
        if not isinstance(feed, dict):
            continue
        td = feed.get("templateData", {})
        title_data = td.get("titleData", {})
        content_data = td.get("contentData", {})
        jump_data = td.get("jumpData", {})

        title1 = title_data.get("title1", {})
        author = title1.get("text", "") if isinstance(title1, dict) else ""

        title2 = title_data.get("title2", {})
        time_str = title2.get("text", "") if isinstance(title2, dict) else ""

        content_title = content_data.get("contentTitle", {})
        headline = content_title.get("text", "") if isinstance(content_title, dict) else ""
        if not headline:
            ct2 = content_data.get("contentTitle2", {})
            headline = ct2.get("text", "") if isinstance(ct2, dict) else ""

        content_id = content_data.get("contentId", "")
        jump_url = jump_data.get("jumpUrl", "") if isinstance(jump_data, dict) else ""

        if author or headline:
            items.append({
                "author": author,
                "time": time_str,
                "headline": headline,
                "content_id": content_id,
                "url": jump_url,
            })

    result = {"date": datetime.now().strftime("%Y-%m-%d"), "items": items}
    if use_cache and items:
        _write_cache("daily_news", "main", result)
    return result


def get_fund_ranking(cookies=None, rank_sort_by="2", time_cycle="401", last_id=None):
    """Fetch fund ranking from JD Finance (实盘牛人 - 收益率榜).

    Args:
        cookies: JD auth cookies
        rank_sort_by: "1"=收益榜(金额), "2"=收益率榜(百分比)
        time_cycle: "101"=近一周, "201"=近一月, "401"=近一年
        last_id: pagination cursor, None for first page

    Returns dict with keys: users, roll_time, last_id, is_end, filters.
    """
    if cookies is None:
        cookies = _ensure_cookies()

    # Get ranking filters (head)
    body_head = f"reqData={urllib.parse.quote(json.dumps({}))}".encode("utf-8")
    url_head = f"{_JD_BASE}/gw2/generic/redEnv001/h5/m/queryFundFirmOfferMultiRankHead"
    req_head = urllib.request.Request(url_head, data=body_head, headers={
        "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
        "User-Agent": _USER_AGENT,
    })
    if cookies:
        req_head.add_header("Cookie", "; ".join(f"{k}={v}" for k, v in cookies.items()))

    filters = {}
    try:
        resp_head = urllib.request.urlopen(req_head, timeout=10)
        head_data = json.loads(resp_head.read())
        head_rd = head_data.get("resultData", {}).get("data", {})
        filters = {
            "rank_type_options": [o.get("label", "") for o in head_rd.get("rankTypeRadio", {}).get("options", []) if isinstance(o, dict)],
            "time_cycle_options": [o.get("label", "") for o in head_rd.get("timeCycleRadio", {}).get("options", []) if isinstance(o, dict)],
        }
    except Exception:
        pass

    # Get ranking data (minimal params work best)
    body_data = {"lastId": last_id}
    body = f"reqData={urllib.parse.quote(json.dumps(body_data))}".encode("utf-8")
    url = f"{_JD_BASE}/gw2/generic/redEnv001/h5/m/queryFundFirmOfferMultiRank"
    req = urllib.request.Request(url, data=body, headers={
        "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
        "User-Agent": _USER_AGENT,
    })
    if cookies:
        req.add_header("Cookie", "; ".join(f"{k}={v}" for k, v in cookies.items()))

    try:
        resp = urllib.request.urlopen(req, timeout=15)
        data = json.loads(resp.read())
    except Exception as e:
        return {"users": [], "error": str(e)}

    rd = data.get("resultData", {}).get("data", {})
    raw_users = rd.get("fundRankList", [])

    users = []
    for u in raw_users:
        info = u.get("userInfo", {})

        def _text(v):
            """Extract text from {text, textColor} format."""
            if isinstance(v, dict):
                return v.get("text", "")
            return str(v) if v else ""

        users.append({
            "rank": len(users) + 1,
            "name": info.get("userName", ""),
            "pin": info.get("createdPin", ""),
            "total_return": _text(u.get("rankColumnValue", "")),
            "return_rate": _text(u.get("rankColumnName", "")),
            "holdings_value": _text(u.get("showColumnValue", "")),
            "rank_position": _text(u.get("showColumnValue2", "")),
            "tag": _text(u.get("showColumnValue", "")),
        })

    return {
        "users": users,
        "roll_time": rd.get("rollTime", ""),
        "last_id": rd.get("lastId", ""),
        "is_end": rd.get("isEnd", True),
        "filters": filters,
    }


# ============================================================
# Batch Operations
# ============================================================
def batch_get_holdings(cookies=None, use_cache=False):
    if cookies is None:
        cookies = _ensure_cookies()
    results = {}
    for numeric_id, name in FOLLOWED_USERS.items():
        uid = f"jimu_user_info-{numeric_id}"
        holdings = get_user_holdings(uid, cookies, use_cache=use_cache)
        results[name] = holdings
        count = len(holdings.get("holdings", []))
        print(f"  [{name}] {count} funds")
    return results


# ============================================================
# Fund Chart Data (from demo.md verified)
# ============================================================

def get_fund_chart_data(fund_code):
    """getFundDetailChartPageInfo — drawdown, recovery, chart points."""
    data = _api_post("gw/generic/jj/h5/m/getFundDetailChartPageInfo",
                     {"fundCode": fund_code})
    rd = data.get("resultData", {})
    ds = rd.get("datas", {})
    return {
        "fund_code": fund_code,
        "income_trend": ds.get("incomeTrendTip", ""),
        "chart_points": ds.get("majorChartPointList", []),
        "index_name": ds.get("indexName", ""),
        "_raw": ds,
    }


# ============================================================
# Stock Quote API (穿透持仓估值用)
# ============================================================

def get_stock_quotes(stock_codes):
    """Fetch stock/index simple quotes (price, change %).
    No cookie required.

    Args:
        stock_codes: list like ["SH-000001", "NASDAQ-TSM"]

    Returns:
        dict of {uniqueCode: {name, last_price, change_pct}}
    """
    body = json.dumps({
        "ticket": "jd-jr-pc",
        "uniqueCodes": stock_codes,
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{_JD_BASE}/gw/generic/opdataapi/h5/m/getSimpleQuoteUseUniqueCodes",
        data=body,
        headers={"Content-Type": "application/json", "User-Agent": _USER_AGENT},
    )
    result = {}
    try:
        resp = urllib.request.urlopen(req, timeout=10)
        data = json.loads(resp.read())
        for item in data.get("resultData", {}).get("data", {}).get("data", []):
            result[item["uniqueCode"]] = {
                "name": item.get("name", ""),
                "last_price": float(item.get("lastPrice", 0)),
                "change_pct": float(item.get("raisePercent", 0)) * 100,
            }
    except Exception:
        pass
    return result


def get_stock_quotes_extended(stock_codes):
    """Fetch extended stock quotes with PE/PB/市值.
    No cookie required.

    Args:
        stock_codes: list like ["SH-688041", "NASDAQ-TSM"]

    Returns:
        dict of {uniqueCode: {pe_ratio, pb_ratio, market_value, ...}}
    """
    result = {}
    for code in stock_codes:
        try:
            body = json.dumps({
                "ticket": "jd-jr-pc",
                "uniqueCode": code,
            }).encode("utf-8")
            req = urllib.request.Request(
                "https://ms.jr.jd.com/gw2/generic/CaiFuPC/pc/m/getQuoteExtendUseUniqueCodeWithCache",
                data=body,
                headers={"Content-Type": "application/json", "User-Agent": _USER_AGENT},
            )
            resp = urllib.request.urlopen(req, timeout=10)
            data = json.loads(resp.read())
            raw = data.get("resultData", {}).get("data", "{}")
            parsed = json.loads(raw) if isinstance(raw, str) else raw
            result[code] = {
                "name": parsed.get("name", ""),
                "last_price": float(parsed.get("lastPrice", 0)),
                "pe_ratio": float(parsed.get("peRatio", 0)),
                "pb_ratio": float(parsed.get("pnaRatio", 0)),
                "market_value": float(parsed.get("marketValue", 0)),
                "change_pct": float(parsed.get("raisePercent", 0)) * 100,
            }
        except Exception:
            pass
    return result


# ============================================================
# NEW APIs
# ============================================================

def get_fund_fee_and_discount_data_list(fund_code, cookies=None):
    """Get fund fee and discount data (费率优惠).
    Requires auth cookies.
    """
    if cookies is None:
        cookies = _ensure_cookies()
    data = _api_form("gw2/generic/jj/h5/m/getFundFeeAndDiscountDataList",
                     {"fundCode": fund_code}, cookies=cookies)
    rd = data.get("resultData", {})
    if not rd:
        return None
    fee_info = {
        "fund_code": fund_code,
        "manage_fee": rd.get("data", {}).get("manageFeeRate"),
        "custody_fee": rd.get("data", {}).get("custodyFeeRate"),
        "purchase_fee": rd.get("data", {}).get("purchaseFeeRate"),
        "redeem_fee": rd.get("data", {}).get("redeemFeeRate"),
        "discounts": [],
    }
    for d in rd.get("data", {}).get("discountVos", []):
        fee_info["discounts"].append({
            "channel": d.get("channelName"),
            "discount": d.get("discount"),
            "actual_rate": d.get("actualRate"),
        })
    return fee_info


def get_fund_label(fund_code, cookies=None):
    """Get fund badges/labels (热搜标签等). Requires auth cookies.
    Returns list of badge strings like "连续上榜11天"."""
    if cookies is None:
        cookies = _ensure_cookies()
    data = _api_form("gw2/generic/opdataapi/newh5/m/getFundLabel",
                     {"fundCode": fund_code}, cookies=cookies)
    rd = data.get("resultData", {})
    label_text = rd.get("data", "")
    labels = [lbl.strip() for lbl in label_text.replace("，", ",").split(",") if lbl.strip()] if label_text else []
    return {"fund_code": fund_code, "labels": labels}


def get_index_valuation_trend_chart(index_code, date_range=3):
    """Get index PE/PB valuation trend. No auth required.
    Args:
        index_code: CSI index code e.g. "H30184.CSI" (中证行业指数代码)
        date_range: 1=近1年, 3=近3年
    """
    data = _api_form("gw2/generic/wealthBase/newh5/m/getIndexValuationTrendChart",
                     {"indexCode": index_code, "trackId": "", "bkId": "", "dateRange": date_range})
    rd = data.get("resultData", {})
    if not rd or rd.get("status") == "FAIL":
        return None
    datas = rd.get("datas", {})
    chart_list = datas.get("indexValuationTrendChatList", [])
    # Get latest data point
    latest = chart_list[-1] if chart_list else {}
    return {
        "index_code": index_code,
        "current_pe": latest.get("pe"),
        "current_pb": latest.get("pb"),
        "pe_percentile": latest.get("valuePeRank"),
        "pb_percentile": latest.get("valuePbRank"),
        "top_title": datas.get("topTitle"),
        "history": [{"date": p.get("dateTime","")[:10], "pe": p.get("pe"), "pb": p.get("pb"),
                     "pe_pct": p.get("valuePeRank"), "pb_pct": p.get("valuePbRank")}
                    for p in chart_list],
    }


def get_buy_index_related_fund(index_code, cookies=None):
    """Get funds tracking the same CSI index. Requires auth cookies.
    Args:
        index_code: CSI index code e.g. "H30184.CSI"
    """
    if cookies is None:
        cookies = _ensure_cookies()
    data = _api_form("gw2/generic/wealthBase/newh5/m/getBuyIndexRelatedFund",
                     {"indexCode": index_code, "trackId": "", "bkId": ""}, cookies=cookies)
    rd = data.get("resultData", {})
    result = {"index_code": index_code, "etf_funds": [], "otc_funds": []}
    if rd and rd.get("status") != "FAIL":
        datas = rd.get("datas", {})
        for item in datas.get("relatedExchangeFundList", []):
            result["etf_funds"].append({
                "code": item.get("fundCode"),
                "name": item.get("fundName"),
                "rate": item.get("dayRate"),
            })
        for item in datas.get("relatedOTCFundList", []):
            result["otc_funds"].append({
                "code": item.get("fundCode"),
                "name": item.get("fundName"),
                "year_rate": item.get("fundYearRate"),
                "tags": item.get("tagList", []),
            })
    return result


def get_fund_data(fund_code, use_cache=True, cookies=None):
    """Unified fund data fetch - merges all fund data into one cache file.
    Uses get_fund_detail as primary source, falls back to individual APIs.

    Cache: fund_data_{fund_code}.json (1 day TTL)

    Returns dict with keys: profile, performance, holdings, manager, rules, labels
    """
    cache_path = _CACHE_DIR / f"fund_data_{fund_code}.json"
    now = datetime.now()

    # Check cache
    if use_cache and cache_path.exists():
        try:
            cached = json.loads(cache_path.read_text("utf-8"))
            if "fetch_time" in cached:
                fetch_time = datetime.fromisoformat(cached["fetch_time"])
                if (now - fetch_time).days < 1:
                    return cached
        except:
            pass

    result = {"fund_code": fund_code, "fetch_time": now.isoformat()}

    # Primary: get_fund_detail (comprehensive, needs cookie)
    if cookies is None:
        cookies = _ensure_cookies()
    detail = get_fund_detail(fund_code, use_cache=False, cookies=cookies)
    if detail:
        result["profile"] = detail.get("profile", {})
        result["performance"] = detail.get("performance", {})
        result["holdings"] = detail.get("holdings_distribution", {})
        result["manager"] = detail.get("manager", {})
    else:
        # Fallback: individual APIs
        result["profile"] = get_fund_profile(fund_code, use_cache=False) or {}
        result["performance"] = get_fund_performance(fund_code, use_cache=False) or {}

    # Supplement: trade rules (no cookie needed)
    result["rules"] = get_fund_trade_rules(fund_code, use_cache=False) or {}

    # Supplement: manager detail if missing
    if not result.get("manager") or not result["manager"].get("managers"):
        result["manager"] = get_fund_manager(fund_code) or {}

    # Save unified cache
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


# ============================================================
# NEW: Index Block Info — industry-level valuation + investment signals
# ============================================================
def get_index_block_info(index_code, cookies=None):
    """Get industry index PE/PB daily percentiles (10-year) + 3D resonance investment signal.

    This is THE critical missing piece for sector-level market timing. It provides:
    - PE/PB daily percentile history (2016-present)
    - Three-dimensional resonance model: trend(10%) + sentiment(30%) + valuation(60%) → 0-100 score
    - Investment signal tiers: 0-50=观望, 51-75=中性, 76-100=有机会
    - Valuation judgment: 高估/中性/低估

    Args:
        index_code: Industry index code (e.g. "BK0447" for 半导体)
    Returns:
        dict with: index_code, signal_score, signal_grade, valuation_status,
                   pe_percentile, pb_percentile, pe_history, pb_history, top_title
    """
    if cookies is None:
        cookies = _ensure_cookies()
    data = _api_form("gw2/generic/wealthBase/newh5/m/getIndexBlockInfo",
                     {"indexCode": index_code, "trackId": "", "bkId": ""}, cookies=cookies)
    rd = data.get("resultData", {})
    if not rd or rd.get("status") == "FAIL":
        return {"index_code": index_code, "error": "API returned failure"}
    datas = rd.get("datas", {})

    # Valuation data is nested under indexValuationInfo
    val_info = datas.get("indexValuationInfo", {})
    chart_list = val_info.get("indexValuationTrendChatList", [])
    latest = chart_list[-1] if chart_list else {}

    # Signal score from totalScore field (string, e.g. "52")
    raw_score = datas.get("totalScore", "0")
    try:
        signal_score = float(raw_score)
    except (ValueError, TypeError):
        signal_score = 0
    signal_grade = "观望" if signal_score <= 50 else ("中性" if signal_score <= 75 else "有机会")

    # PE/PB percentiles
    pe_pct = float(latest.get("valuePeRank", 0)) if latest.get("valuePeRank") else None
    pb_pct = float(latest.get("valuePbRank", 0)) if latest.get("valuePbRank") else None

    # Valuation status from API's own topTitle
    valuation_status = val_info.get("topTitle", "")

    # Radar scores (趋势/景气/估值) from radar list
    trend_score = None
    sentiment_score = None
    valuation_score = None
    for radar in datas.get("indexBlockInfoRadarInfoList", []):
        name = radar.get("name", "")
        score = radar.get("score")
        if "趋势" in name:
            trend_score = float(score) if score else None
        elif "景气" in name:
            sentiment_score = float(score) if score else None
        elif "估值" in name:
            valuation_score = float(score) if score else None

    result = {
        "index_code": index_code,
        "description": datas.get("description", ""),
        "signal_score": signal_score,
        "signal_grade": signal_grade,
        "valuation_status": valuation_status,
        "current_pe": float(latest.get("pe", 0)) if latest.get("pe") else None,
        "current_pb": float(latest.get("pb", 0)) if latest.get("pb") else None,
        "pe_percentile": pe_pct,
        "pb_percentile": pb_pct,
        "trend_score": trend_score,
        "sentiment_score": sentiment_score,
        "valuation_score": valuation_score,
        # Full daily history (2016-present, ~2500 trading days)
        "pe_history": [{"date": p.get("dateTime","")[:10], "pe": float(p.get("pe",0)),
                        "pb": float(p.get("pb",0)),
                        "pe_pct": float(p.get("valuePeRank",0)),
                        "pb_pct": float(p.get("valuePbRank",0))}
                       for p in chart_list],
    }
    return result


# ============================================================
# NEW: Fund Detail (Logged-in version) — most comprehensive single endpoint
# ============================================================
def get_fund_detail_pin(fund_code, use_cache=False, cookies=None):
    """Logged-in version of fund detail — the most comprehensive single endpoint.

    Returns more data than get_fund_detail including:
    - fundDiagnosisOfItem: returns/volatility/drawdown/Sharpe scores
    - fundProfileOfItem: full company info, inception date, scale
    - purchaseProcessOfItem: fee details with discounts
    - All the same sections as get_fund_detail (performance, holdings, manager, chart, notices)

    Args:
        fund_code: 6-digit fund code
        use_cache: use cached data (1 day TTL)
        cookies: auth cookies (auto-loaded if None)
    Returns:
        dict with keys: profile, performance, holdings_distribution, manager,
                        diagnosis, fee_info, chart, notices, nav_history
    """
    if use_cache:
        cached = _read_cache("fund_detail_pin", fund_code, max_age_days=1)
        if cached:
            return cached

    if cookies is None:
        cookies = _ensure_cookies()
    data = _api_post("gw/generic/life/h5/m/getFundDetailPageInfoWithPin",
                     {"fundCode": fund_code}, cookies=cookies)
    rd = data.get("resultData", {})
    datas = rd.get("datas", {})
    if not datas:
        return None

    # --- Profile ---
    header = datas.get("headerOfItem", {})
    profile_section = datas.get("fundProfileOfItem", {})
    profile = {
        "fund_code": fund_code,
        "full_name": header.get("fundName", ""),
        "fund_type": header.get("fundTypeName", ""),
        "risk_level": header.get("riskLevel"),
        "morningstar_rating": header.get("morningstarRating"),
        "established": profile_section.get("establishedDate", ""),
        "scale": profile_section.get("fundScale", ""),
        "manager_company": profile_section.get("company_name", ""),
        "company_scale": profile_section.get("companyManageScale", ""),
        "manager_count": profile_section.get("manageNumber"),
        "wealth_rank": header.get("wealthRank", ""),
    }

    # --- Performance ---
    perf_section = datas.get("performanceOfItem", {})
    perf_list = []
    for item in perf_section.get("historyPerformanceMap", {}).get("historyPerformanceList", []):
        rank_str = item.get("rank", "")
        try:
            parts = rank_str.split("/")
            rank_pct = int(parts[0]) / int(parts[1]) if len(parts) == 2 else None
        except Exception:
            rank_pct = None
        perf_list.append({
            "period": item.get("name", ""),
            "return": float(item.get("rate", 0)) if item.get("rate") else None,
            "avg": float(item.get("avg", 0)) if item.get("avg") else None,
            "rank": rank_str,
            "rank_pct": rank_pct,
        })
    year_list = []
    for item in perf_section.get("yearPerformanceMap", {}).get("yearPerformanceList", []):
        year_list.append({
            "year": item.get("year", ""),
            "return": float(item.get("rate", 0)) if item.get("rate") else None,
            "avg": float(item.get("avg", 0)) if item.get("avg") else None,
        })
    performance = {"fund_code": fund_code, "performance": perf_list, "year_performance": year_list}

    # --- Holdings Distribution ---
    dist_section = datas.get("investmentDistributionNewOfItem", {})
    dist = dist_section.get("investmentDistribution", dist_section)
    allocation = {}
    for item in dist.get("proportionList", []):
        allocation[item.get("name", "")] = float(item.get("fundValue", 0))
    top_stocks = []
    for stock in dist.get("stock", [])[:10]:
        top_stocks.append({
            "name": stock.get("name", ""),
            "code": stock.get("code", ""),
            "ratio": stock.get("ratio", ""),
            "change": stock.get("holdingSharesChange", ""),
            "rate": stock.get("rate", ""),
            "industry": stock.get("industryName", ""),
            "quarters_held": stock.get("positionQuarters", ""),
        })
    holdings_dist = {
        "fund_code": fund_code,
        "report_date": dist.get("investDate", ""),
        "allocation": allocation,
        "top_stocks": top_stocks,
        "stock_nav_ratio": dist.get("stockNavRatio", ""),
    }

    # --- Manager ---
    mgr_section = datas.get("fundManagerOfItem", {})
    managers = []
    for m in mgr_section.get("managerInfoList", []):
        managers.append({
            "name": m.get("managerName", ""),
            "year_performance": m.get("yearPerformance", ""),
            "employ_performance": m.get("employPerformance", ""),
            "manage_scale": m.get("manageScale", ""),
            "employment_date": m.get("employmentDate", ""),
            "accession_date": m.get("accessionDateDesc", ""),
        })
    manager = {"fund_code": fund_code, "managers": managers}

    # --- Diagnosis (KEY NEW ADDITION from Pin endpoint) ---
    diag_section = datas.get("fundDiagnosisOfItem", {})
    diagnosis = {}
    if diag_section:
        diagnosis = {
            "ability": float(diag_section.get("ability", 0)),           # 收益能力
            "ability_desc": diag_section.get("abilityDesc", ""),
            "performance_ratio": float(diag_section.get("performanceRatio", 0)),  # 投资性价比
            "ratio_desc": diag_section.get("ratioDesc", ""),
            "anti_risk": float(diag_section.get("antiRisk", 0)),         # 抗跌能力
            "anti_risk_desc": diag_section.get("antiRiskDesc", ""),
            "anti_fluctuation": float(diag_section.get("antiFluctuation", 0)),  # 抗波动能力
            "fluctuation_desc": diag_section.get("fluctuationDesc", ""),
            "sharpe": float(diag_section.get("sharpe", 0)) if diag_section.get("sharpe") else None,
            "max_drawdown": float(diag_section.get("maxDrawdown", 0)) if diag_section.get("maxDrawdown") else None,
            "volatility": float(diag_section.get("volatility", 0)) if diag_section.get("volatility") else None,
            "advantage_index_name": diag_section.get("advantageIndexName", ""),
            "advantage_index_val": diag_section.get("advantageIndexVal", ""),
            "disadvantage_index_name": diag_section.get("disadvantageIndexName", ""),
            "disadvantage_index_val": diag_section.get("disadvantageIndexVal", ""),
        }

    # --- Chart ---
    chart_section = datas.get("trendChartOfItem", {})
    chart = {
        "fund_code": fund_code,
        "income_trend": chart_section.get("incomeTrendTip", ""),
        "chart_points": chart_section.get("majorChartPointList", []),
        "index_name": chart_section.get("indexName", ""),
    }

    # --- Fee info ---
    btn_tips = datas.get("bottomButtonOfItem", {}).get("buttonTips", {})
    fee_info = {
        "buy_fee": btn_tips.get("leftDescHoldCard", ""),
        "buy_fee_new": btn_tips.get("leftDescNew", ""),
        "min_purchase": btn_tips.get("rightDescNew", ""),
    }

    # --- Notices ---
    notices = []
    for n in datas.get("noticeList", []):
        notices.append({
            "date": n.get("noteDate", ""),
            "title": n.get("noticeTitle", ""),
            "url": n.get("noticeHtmlUrl", ""),
        })

    # --- NAV History ---
    nav_history = []
    try:
        nav_data = _api_post("gw/generic/jj/h5/m/getFundHistoryNetValuePageInfo",
                             {"fundCode": fund_code}, cookies=cookies)
        for n in nav_data.get("resultData", {}).get("datas", {}).get("netValueList", []):
            nav_history.append({
                "date": n.get("date", ""),
                "nav": n.get("netValue", ""),
                "daily_return": n.get("dailyProfit", ""),
            })
    except Exception:
        pass

    result = {
        "fund_code": fund_code,
        "profile": profile,
        "performance": performance,
        "holdings_distribution": holdings_dist,
        "manager": manager,
        "diagnosis": diagnosis,
        "fee_info": fee_info,
        "chart": chart,
        "notices": notices,
        "nav_history": nav_history,
    }
    if use_cache:
        _write_cache("fund_detail_pin", fund_code, result)
    return result


# ============================================================
# NEW: Watchlist (自选列表)
# ============================================================
def get_watchlist(cookies=None, use_cache=False):
    """Get user's watchlist (自选基金列表) with performance metrics.

    Returns each fund's: fundNo, fundName, latest NAV, daily/weekly/monthly/yearly returns,
    and cumulative P&L% since added to watchlist.

    Requires auth cookies.

    Returns:
        dict with: groups (list of group names), funds (list of fund items)
    """
    if use_cache:
        cached = _read_cache("watchlist", "mine", max_age_days=1)
        if cached:
            return cached

    def _to_num(v):
        """安全转 float，处理 '--' 等非数字值"""
        if v is None or v == "--" or v == "":
            return None
        try: return float(v)
        except: return None

    if cookies is None:
        cookies = _ensure_cookies()

    # Note: this endpoint uses a different format (jdtwt namespace on gw2)
    data = _api_form("gw2/generic/jdtwt/h5/m/queryZxProductList",
                     {"type": 1, "page": 1, "pageSize": 200}, cookies=cookies)

    rd = data.get("resultData", {})
    datas = rd.get("datas", {}) if rd else {}

    groups = []
    for g in datas.get("groupList", []):
        groups.append({
            "group_name": g.get("groupName", ""),
            "group_id": g.get("groupId", ""),
            "count": g.get("count", 0),
        })

    funds = []
    product_list = datas.get("zxProductInfoList", datas.get("productList", []))
    for f in product_list:
        funds.append({
            "fund_code": f.get("fundNo", ""),
            "fund_name": f.get("fundName", ""),
            "fund_type": f.get("fundType", ""),
            "latest_nav": f.get("newValue", ""),
            "day_return": _to_num(f.get("dayRiseRate")),
            "week_return": _to_num(f.get("weekRiseRate")),
            "month_return": _to_num(f.get("monthRiseRate")),
            "year_return": _to_num(f.get("yearRiseRate")),
            "total_pnl_pct": _to_num(f.get("allIncome")),
            "fund_id": f.get("fundId", ""),
            "url": f.get("url", ""),
        })

    result = {"groups": groups, "funds": funds, "total_count": len(funds)}

    if use_cache:
        _write_cache("watchlist", "mine", result)
    return result


# ============================================================
# NEW: Player Trading Feed (大佬实盘交易feed)
# ============================================================
def get_player_trading_feed(cookies=None, page_id="11567"):
    """Get real-time trading feed from the funded player square (实盘广场).

    More reliable than get_trading_records because it directly reads the
    community feed instead of scraping user trade history.

    Key fields per trade:
    - allAmount: trade amount/shares
    - tradeType: 1=buy, 2=sell
    - tradeTime: timestamp (ms)
    - statusCode: COMPLETE/PAY_SUCC/REDEEM
    - productId: JD internal code (map to 6-digit fund code)
    - jumpUrl: contains public fund code

    Returns:
        list of trade feed items
    """
    if cookies is None:
        cookies = _ensure_cookies()

    data = _api_form("gw/generic/aladdin/h5/m/getPageMutilData",
                     {"pageId": page_id, "extParams": {}}, cookies=cookies)
    rd = data.get("resultData", {})
    if not rd:
        return []

    datas = rd.get("datas", {})
    items = datas.get("itemList", [])

    trades = []
    for item in items:
        ext = item.get("extInfo", {})
        trades.append({
            "user_name": item.get("userName", ""),
            "user_id": item.get("userId", ""),
            "fund_name": item.get("productName", ""),
            "product_id": item.get("productId", ""),
            "amount": ext.get("allAmount", ""),
            "trade_type": 1 if ext.get("tradeType") == "1" else (2 if ext.get("tradeType") == "2" else None),
            "trade_time": ext.get("tradeTime", ""),
            "status": ext.get("statusCode", ""),
            "jump_url": ext.get("jumpUrl", ""),
            "order_type": item.get("orderType", ""),
        })

    return trades


# ============================================================
# NEW: Index Detail (行业指数详情)
# ============================================================
def get_index_detail(index_code, cookies=None):
    """Get industry index detail including linked ETFs and OTC funds.

    Returns:
        dict with: index_code, index_name, description, track_type,
                   linked_etfs (with returns/volume), linked_otc_funds (with 1yr/3yr/5yr returns)
    """
    if cookies is None:
        cookies = _ensure_cookies()
    data = _api_form("gw2/generic/wealthBase/newh5/m/getIndexDetail",
                     {"indexCode": index_code, "trackId": "", "bkId": ""}, cookies=cookies)
    rd = data.get("resultData", {})
    if not rd or rd.get("status") == "FAIL":
        return {"index_code": index_code, "error": "API returned failure"}

    datas = rd.get("datas", {})
    index_info = datas.get("indexInfo", {})

    etfs = []
    for e in datas.get("relatedExchangeFundList", []):
        etfs.append({
            "code": e.get("fundCode"),
            "name": e.get("fundName"),
            "day_return": e.get("dayRate"),
            "volume": e.get("dayTurnover"),
            "month_return": e.get("day30Rate"),
        })

    otc_funds = []
    for f in datas.get("relatedOTCFundList", []):
        otc_funds.append({
            "code": f.get("fundCode"),
            "name": f.get("fundName"),
            "year_return": f.get("fundYearRate"),
            "excess_return_vs_index": f.get("excessReturnRate"),
            "return_3y": f.get("fundYear3Rate"),
            "return_5y": f.get("fundYear5Rate"),
            "tags": f.get("tagList", []),
        })

    return {
        "index_code": index_code,
        "index_name": index_info.get("name", ""),
        "description": index_info.get("desc", ""),
        "track_type": index_info.get("trackTypeName", ""),
        "linked_etfs": etfs,
        "linked_otc_funds": otc_funds,
    }


# ============================================================
# Featured Rankings — queryFullRanking 端点
# 数据源: jj/h5/m/queryFullRanking (返 12+5 榜, TOP20)
# 端点: ms.jr.jd.com/gw2/generic/jj/h5/m/queryFullRanking
# 真实响应结构: resultData.datas.primRanking[].secRanking[]
# 特点: 需要 cookie, 实测可拉到 17 个榜单 (12 主题 + 5 人气)
# ============================================================


def get_featured_rankings(cookies=None, use_cache=True, max_items=20):
    """拉取 12 主题榜 + 5 人气认证榜 TOP20。

    Returns:
        dict: {
            "header": [一级分类列表 (业绩排行/定投排行/净值排行)],
            "boards": {secRankCode: {name, code, prim, top20: [{rank, code, name, value, ...}]}}
        }
    """
    if use_cache:
        cached = _read_cache("featured_rankings", "main", max_age_days=0)
        if cached:
            return cached
    if cookies is None:
        cookies = _ensure_cookies()

    # 调用 queryFullRanking (设备标识, 必带, 否则偶尔返空)
    body = {"deviceType": "h5", "clientVersion": "11.0.0"}
    raw = _api_form("gw2/generic/jj/h5/m/queryFullRanking", body, cookies)
    rd = raw.get("resultData", {}).get("datas", {}) if isinstance(raw, dict) else {}

    # header (一级分类)
    header_raw = _api_form("gw2/generic/jj/h5/m/getRankingHeaderInfoV2", {}, cookies)
    header_inner = header_raw.get("resultData", {}).get("resultData", {}) if isinstance(header_raw, dict) else {}
    header = header_inner.get("rankingList", [])

    # 解析榜单
    boards = {}
    for prim in rd.get("primRanking", []):
        prim_name = prim.get("primRankName", "")
        for sec in prim.get("secRanking", []):
            code = sec.get("secRankCode", "")
            name = sec.get("secRankName", "")
            top = []
            for idx, item in enumerate(sec.get("rankingContent", [])[:max_items]):
                top.append({
                    "rank": idx + 1,
                    "code": item.get("fundCode"),
                    "name": item.get("fundName"),
                    "prim_inv_key": item.get("primInvKey"),
                    "prim_inv_value": item.get("primInvValue"),
                    "sec_inv_key": item.get("secInvKey"),
                    "sec_inv_value": item.get("secInvValue"),
                    "risk_level": item.get("riskLevel"),
                    "sub_rank_name": item.get("subRankName"),
                    "detail_url": item.get("fundDetailUrl"),
                })
            boards[code] = {
                "code": code,
                "name": name,
                "prim": prim_name,
                "rec_content": sec.get("recContent", ""),
                "rank_subtitle": sec.get("rankSubtitle", ""),
                "hot": sec.get("hot", False),
                "rank_no": sec.get("secRankNo"),
                "rank_hot_no": sec.get("rankHotNo"),
                "top20": top,
            }

    result = {"header": header, "boards": boards}
    if use_cache and boards:
        _write_cache("featured_rankings", "main", result)
    return result


def get_board_by_code(sec_rank_code, cookies=None, use_cache=True, max_items=20):
    """从已缓存/重新拉取 featured_rankings, 取单个榜。"""
    all_data = get_featured_rankings(cookies=cookies, use_cache=use_cache, max_items=max_items)
    return all_data.get("boards", {}).get(sec_rank_code)


# ============================================================
# Snapshot Management


# ============================================================
# Snapshot Management
# ============================================================
def save_snapshot(tag, data):
    _SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    p = _SNAPSHOTS_DIR / f"{tag}_{ts}.json"
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return str(p)


def load_latest_snapshot(tag):
    if not _SNAPSHOTS_DIR.exists():
        return None
    files = sorted(_SNAPSHOTS_DIR.glob(f"{tag}_*.json"), reverse=True)
    if not files:
        return None
    with open(files[0], "r", encoding="utf-8") as f:
        return json.load(f)


# ============================================================
# CLI
# ============================================================
def main():
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="JD Finance Fund API Tool")
    parser.add_argument("--test", action="store_true", help="Test cookie validity")
    parser.add_argument("--login", action="store_true", help="Force re-login")
    parser.add_argument("--offline", action="store_true", help="Offline mode (cache only)")
    parser.add_argument("--holdings", type=str, help="View user holdings (uid)")
    parser.add_argument("--my-holdings", action="store_true", help="View own holdings")
    parser.add_argument("--trade-rules", type=str, help="View fund trade rules (code)")
    parser.add_argument("--fund-holdings", type=str, help="View fund holdings distribution (code)")
    parser.add_argument("--fund-profile", type=str, help="View fund profile (code)")
    parser.add_argument("--fund-perf", type=str, help="View fund performance (code)")
    parser.add_argument("--fund-manager", type=str, help="View fund manager (code)")
    parser.add_argument("--trading-records", type=str, help="View trading records for a user (uid)")
    parser.add_argument("--trading-records-all", action="store_true", help="View trading records for all followed users")
    parser.add_argument("--list-followed", action="store_true", help="List followed users")
    parser.add_argument("--batch-fund", type=str, nargs="+", help="Batch fetch all data for multiple fund codes (concurrent)")
    parser.add_argument("--batch-holdings", action="store_true", help="Batch get all followed holdings")
    parser.add_argument("--save-cookies", type=str, help="Manually paste cookie string to save")
    parser.add_argument("--fund-fees", type=str, help="Get fund fee and discount data (code)")
    parser.add_argument("--fund-label", type=str, help="Get fund official classification labels (code)")
    parser.add_argument("--index-valuation", type=str, help="Get index PE/PB valuation (e.g. SH-000300)")
    parser.add_argument("--index-related-funds", type=str, help="Get funds tracking an index (code)")
    parser.add_argument("--fund-data", type=str, help="Get unified fund data (code)")
    parser.add_argument("--index-block-info", type=str, help="Get industry index investment signal + 10yr PE/PB percentile (e.g. BK0447)")
    parser.add_argument("--index-detail", type=str, help="Get industry index detail with linked ETFs/funds (code)")
    parser.add_argument("--fund-detail-pin", type=str, help="Get fund detail (logged-in version, includes diagnosis)")
    parser.add_argument("--watchlist", action="store_true", help="Get your watchlist (自选基金列表)")
    parser.add_argument("--player-trading-feed", action="store_true", help="Get real-time trading feed from player square")
    args = parser.parse_args()

    if args.save_cookies:
        cookies = {}
        for part in args.save_cookies.split(";"):
            if "=" in part:
                k, v = part.strip().split("=", 1)
                cookies[k.strip()] = v.strip()
        _save_cookies(cookies)
        print(f"Cookie saved: {list(cookies.keys())}")
        return

    if args.login:
        cookies = asyncio.run(_auto_login_with_playwright())
        if cookies:
            print("Login success")
        return

    if args.test:
        cookies = _ensure_cookies(offline=args.offline)
        if not cookies:
            print("No cookie available")
            return
        valid, user_info = _verify_cookies(cookies)
        if valid:
            print(f"Cookie valid: {json.dumps(user_info, ensure_ascii=False)[:200]}")
        else:
            print("Cookie invalid or expired")
        return

    # Cookie-required APIs
    need_cookie = any([args.holdings, args.my_holdings, args.trading_records, args.trading_records_all, args.list_followed, args.batch_holdings])
    if need_cookie:
        cookies = _ensure_cookies(offline=args.offline)
        if not cookies:
            print("[ERROR] No cookie available")
            return

        if args.my_holdings:
            result = get_user_holdings(cookies=cookies, use_cache=args.offline)
            holdings = result.get("holdings", [])
            print(f"\nOwn holdings ({len(holdings)} funds):")
            for h in holdings:
                print(f"  {h['name']} ({h['code']}): {h['amount']} ({h['profit_rate']})")

        elif args.holdings:
            result = get_user_holdings(args.holdings, cookies=cookies, use_cache=args.offline)
            holdings = result.get("holdings", [])
            print(f"\n{args.holdings} holdings ({len(holdings)} funds):")
            for h in holdings:
                print(f"  {h['name']} ({h['code']}): {h['amount']} ({h['profit_rate']})")

        elif args.trading_records_all:
            print("\\nTrading records for all followed users...")
            for numeric_id, name in FOLLOWED_USERS.items():
                uid = f"jimu_user_info-{numeric_id}"
                try:
                    result = get_trading_records(uid, cookies=cookies)
                except Exception as e:
                    print(f"\\n  [{name}] ({uid}) failed: {e}")
                    continue
                records = result.get("records", [])
                if records:
                    print(f"\\n  [{name}] ({uid}) — {len(records)} records:")
                    for r in records[:5]:
                        act = r.get("action", "")
                        detail = r.get("detail", "")
                        fund = r.get("fund_name", "")
                        amt = r.get("amount", "")
                        print(f"    {act} | {fund} | {amt} | {detail}")
                else:
                    print(f"\\n  [{name}] no records")

        elif args.trading_records:
            result = get_trading_records(args.trading_records, cookies=cookies)
            records = result.get("records", [])
            print(f"\nTrading records for {args.trading_records} ({len(records)} records):")
            for r in records[:20]:
                act = r.get("action", "")
                detail = r.get("detail", "")
                fund = r.get("fund_name", "")
                amt = r.get("amount", "")
                print(f"  {act} | {fund} | {amt} | {detail}")

        elif args.list_followed:
            users = get_followed_users_from_circle(cookies)
            if isinstance(users, dict) and "error" in users:
                print(f"Failed: {users['error']}")
            else:
                print(f"\nFollowed users ({len(users)}):")
                for u in users:
                    print(f"  {u['name']}: {u['uid']} | {u['summary']}")

        elif args.batch_holdings:
            print("\nBatch fetching all followed users' holdings...")
            results = batch_get_holdings(cookies, use_cache=args.offline)
            total = sum(len(v.get("holdings", [])) for v in results.values())
            print(f"\nTotal: {len(results)} users, {total} funds")

    # Batch fund data (concurrent, no login needed)
    if args.batch_fund:
        codes = args.batch_fund
        print(f"\nBatch fetching data for {len(codes)} funds (concurrent, max_workers=10)...")
        t0 = time.time()
        results = batch_get_fund_data(codes, use_cache=args.offline)
        elapsed = time.time() - t0
        print(f"Completed in {elapsed:.1f}s\n")

        for code in codes:
            row = results.get(code, {})
            if "error" in row:
                print(f"[{code}] ERROR: {row['error']}")
                continue
            print(f"\n{'='*50}")
            print(f"  {code}")
            print(f"{'='*50}")

            # Profile
            pf = row.get("fund_profile")
            if pf:
                print(f"  名称: {pf.get('full_name', '')}")
                print(f"  成立: {pf.get('established', '')}")
                print(f"  规模: {pf.get('scale', '')}")

            # Performance
            perf = row.get("fund_perf")
            if perf:
                for p in perf.get("performance", [])[:8]:
                    r = p.get("return", "")
                    r_str = f"{r}%" if r is not None else "None"
                    print(f"  {p.get('period', '')}: {r_str} | Rank {p.get('rank', '')}")

            # Trade rules
            tr = row.get("trade_rules")
            if tr:
                print(f"  申购费: {tr.get('purchase_fee', '')}%")
                print(f"  管理费: {tr.get('manage_fee', '')}%/yr")
                print(f"  日限额: {tr.get('day_limit', '')} CNY")

            # Holdings
            hd = row.get("holdings")
            if hd:
                top = hd.get("top_stocks", [])[:5]
                items_str = " | ".join(f'{s["name"]} {s["ratio"]}' for s in top)
                print(f"  前5持仓: {items_str}")

            # Manager
            mgr = row.get("manager")
            if mgr:
                for m in mgr.get("managers", []):
                    print(f"  经理: {m.get('name', '')}, {m.get('tenure', '')}")

    # No-login APIs
    if args.trade_rules:
        rules = get_fund_trade_rules(args.trade_rules, use_cache=not args.offline)
        if rules:
            print(f"\nFund {args.trade_rules} trade rules:")
            print(f"  Buy cutoff: {rules['buy_date']}")
            print(f"  Confirm date: {rules['confirm_date']}")
            print(f"  Purchase fee: {rules['purchase_fee']}% (original {rules['purchase_fee_original']}%)")
            print(f"  Management fee: {rules['manage_fee']}%/yr")
            print(f"  Custody fee: {rules['custody_fee']}%/yr")
            print(f"  Daily limit: {rules['day_limit']} CNY")
            print(f"  Min purchase: {rules['min_purchase']} CNY")
            print(f"  Redemption fees:")
            for r in rules["redeem_fees"]:
                print(f"    {r['interval']}: {r['rate']}%")
        else:
            print("Failed to get trade rules")

    if args.fund_holdings:
        dist = get_fund_holdings_distribution(args.fund_holdings, use_cache=not args.offline)
        if dist:
            print(f"\nFund {args.fund_holdings} holdings (as of {dist['invest_date']}):")
            for k, v in dist["allocation"].items():
                print(f"  {k}: {v}%")
            print(f"\nTop 10 holdings:")
            for s in dist["top_stocks"]:
                print(f"  {s['name']} ({s['code']}): {s['ratio']} | Change: {s['change']}")
        else:
            print("Failed to get holdings distribution")

    if args.fund_profile:
        profile = get_fund_profile(args.fund_profile, use_cache=not args.offline)
        if profile:
            print(f"\nFund {args.fund_profile} profile:")
            print(f"  Full name: {profile['full_name']}")
            print(f"  Established: {profile['established']}")
            print(f"  Scale: {profile['scale']}")
            print(f"  Manager: {profile['manager_company']}")
            print(f"  Custodian: {profile['custodian']}")
        else:
            print("Failed to get fund profile")

    if args.fund_perf:
        perf = get_fund_performance(args.fund_perf, use_cache=not args.offline)
        if perf:
            print(f"\nFund {args.fund_perf} performance:")
            for p in perf["performance"][:8]:
                print(f"  {p['period']}: {p['return']}% | Rank {p['rank']}")
        else:
            print("Failed to get performance")

    if args.fund_manager:
        mgr = get_fund_manager(args.fund_manager)
        if mgr:
            print(f"\nFund {args.fund_manager} managers:")
            for m in mgr["managers"]:
                print(f"  {m['name']} ({m.get('title', '')}), tenure: {m.get('tenure', '')}")
                if "radar" in m:
                    print(f"    Radar: {m['radar']}")
                    print(f"    Total score: {m.get('total_score', 0)}")
        else:
            print("Failed to get fund manager")

    # New APIs
    if args.fund_fees:
        fees = get_fund_fee_and_discount_data_list(args.fund_fees)
        if fees:
            print(f"\nFund {args.fund_fees} fees:")
            print(f"  管理费: {fees.get('manage_fee', 'N/A')}")
            print(f"  托管费: {fees.get('custody_fee', 'N/A')}")
            print(f"  申购费: {fees.get('purchase_fee', 'N/A')}")
            print(f"  赎回费: {fees.get('redeem_fee', 'N/A')}")
            for d in fees.get('discounts', []):
                print(f"  优惠: {d.get('channel')} -> {d.get('discount')}折 (实付{d.get('actual_rate')})")
        else:
            print("Failed to get fee data")

    if args.fund_label:
        label = get_fund_label(args.fund_label)
        if label:
            print(f"\nFund {args.fund_label} labels: {', '.join(label['labels'])}")
        else:
            print("Failed to get labels")

    if args.index_valuation:
        val = get_index_valuation_trend_chart(args.index_valuation)
        if val:
            print(f"\nIndex {args.index_valuation} valuation:")
            print(f"  当前PE: {val.get('current_pe')}")
            print(f"  当前PB: {val.get('current_pb')}")
            print(f"  PE百分位: {val.get('pe_percentile')}")
            print(f"  PB百分位: {val.get('pb_percentile')}")
        else:
            print("Failed to get valuation data")

    if args.index_related_funds:
        funds = get_buy_index_related_fund(args.index_related_funds)
        if funds:
            print(f"\nFunds tracking {args.index_related_funds}:")
            print(f"  ETF funds:")
            for f in funds.get('etf_funds', []):
                print(f"    {f.get('code')} - {f.get('name')} ({f.get('rate')}%)")
            print(f"  OTC funds:")
            for f in funds.get('otc_funds', []):
                print(f"    {f.get('code')} - {f.get('name')} ({f.get('year_rate')}%)")
        else:
            print("Failed to get related funds")

    if args.fund_data:
        data = get_fund_data(args.fund_data)
        if data:
            p = data.get("profile", {})
            print(f"\nFund {args.fund_data} data:")
            print(f"  名称: {p.get('full_name', 'N/A')}")
            print(f"  类型: {p.get('fund_type', 'N/A')}")
            print(f"  规模: {p.get('scale', 'N/A')}")
            perf = data.get("performance", {}).get("performance", [])
            if perf:
                for item in perf[:5]:
                    print(f"  {item['period']}: {item.get('return','?')}%")
            mgr = data.get("manager", {}).get("managers", [])
            if mgr:
                for m in mgr[:2]:
                    print(f"  经理: {m.get('name','')}")
            print(f"  Cache: fund_data_{args.fund_data}.json")
        else:
            print("Failed to get fund data")

    if args.index_block_info:
        block = get_index_block_info(args.index_block_info)
        if block and "error" not in block:
            print(f"\nIndex {args.index_block_info} industry signal:")
            print(f"  综合评分: {block.get('signal_score')} ({block.get('signal_grade')})")
            print(f"  估值状态: {block.get('valuation_status')}")
            print(f"  PE百分位: {block.get('pe_percentile')}")
            print(f"  PB百分位: {block.get('pb_percentile')}")
            print(f"  趋势: {block.get('trend_score')}, 景气: {block.get('sentiment_score')}, 估值: {block.get('valuation_score')}")
        else:
            print("Failed to get index block info")

    if args.index_detail:
        detail = get_index_detail(args.index_detail)
        if detail and "error" not in detail:
            print(f"\nIndex {args.index_detail} detail:")
            print(f"  名称: {detail.get('index_name')}")
            print(f"  类型: {detail.get('track_type')}")
            etfs = detail.get('linked_etfs', [])
            if etfs:
                print(f"  关联ETF ({len(etfs)}):")
                for e in etfs[:5]:
                    print(f"    {e['code']} {e['name']}: 日涨幅={e['day_return']}%")
            otc = detail.get('linked_otc_funds', [])
            if otc:
                print(f"  关联场外基金 ({len(otc)}):")
                for f in otc[:5]:
                    print(f"    {f['code']} {f['name']}: 1年={f.get('year_return')}% 超额={f.get('excess_return_vs_index')}%")
        else:
            print("Failed to get index detail")

    if args.fund_detail_pin:
        detail = get_fund_detail_pin(args.fund_detail_pin)
        if detail:
            p = detail.get("profile", {})
            print(f"\nFund {args.fund_detail_pin} (Pin):")
            print(f"  名称: {p.get('full_name', 'N/A')}")
            print(f"  类型: {p.get('fund_type', 'N/A')}, 规模: {p.get('scale', 'N/A')}")
            diag = detail.get("diagnosis", {})
            if diag:
                print(f"  诊断: 收益={diag.get('ability')} 抗回撤={diag.get('anti_risk')} 夏普={diag.get('sharpe')} 最大回撤={diag.get('max_drawdown')}")
                adv = diag.get('advantage_index_name', '')
                dis = diag.get('disadvantage_index_name', '')
                if adv or dis:
                    print(f"  优势={adv}({diag.get('advantage_index_val')}) 劣势={dis}({diag.get('disadvantage_index_val')})")
            perf = detail.get("performance", {}).get("performance", [])
            if perf:
                for item in perf[:3]:
                    print(f"  {item['period']}: {item.get('return','?')}%")
        else:
            print("Failed to get fund detail (Pin)")

    if args.watchlist:
        wl = get_watchlist()
        if wl:
            print(f"\n自选列表 ({wl.get('total_count', 0)} funds):")
            for g in wl.get('groups', []):
                print(f"  分组: {g['group_name']} ({g['count']}只)")
            for f in wl.get('funds', []):
                print(f"  {f['fund_code']} {f['fund_name']}: 净值={f['latest_nav']} 日涨跌={f.get('day_return')}% 自选盈亏={f.get('total_pnl_pct')}%")
        else:
            print("Failed to get watchlist")

    if args.player_trading_feed:
        trades = get_player_trading_feed()
        print(f"\n实盘交易feed ({len(trades) if trades else 0} trades):")
        for t in (trades or [])[:10]:
            direction = "买入" if t.get('trade_type') == 1 else ("卖出" if t.get('trade_type') == 2 else "?")
            print(f"  {t.get('user_name')}: {direction} {t.get('fund_name')} {t.get('amount')}")


if __name__ == "__main__":
    main()
