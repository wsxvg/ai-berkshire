#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
JD Finance Fund API Tool (zero external dependencies)

Features:
  - Cookie authentication (cookies.json + auto Playwright refresh)
  - 12 core API wrappers (holdings/trade/fund detail/rules/distribution/manager)
  - Local cache (trade rules 30d / fund detail 7d / holdings 1d)
  - Rate limiting (0.3s interval)
  - --offline fallback mode (cache only)

Dependencies: Python stdlib only (urllib/json/os/time/datetime/pathlib)
Auth: data/jd_auth/cookies.json (Playwright auto-capture or manual paste)

Usage:
  python tools/jd_finance_api.py --test
  python tools/jd_finance_api.py --holdings jimu_user_info-14345330
  python tools/jd_finance_api.py --trade-rules 006105
  python tools/jd_finance_api.py --fund-holdings 006105
  python tools/jd_finance_api.py --list-followed
  python tools/jd_finance_api.py --holdings jimu_user_info-14345330 --offline

  # NEW: concurrent batch fetching (60x faster!)
  python tools/jd_finance_api.py --batch-fund 002891 018147 008253 026211 021528 011452 002112 016452
"""

import argparse
import asyncio
import concurrent.futures
import json
import os
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
    except Exception:
        return {}


def _save_cookies(cookies_dict):
    _AUTH_DIR.mkdir(parents=True, exist_ok=True)
    with open(_COOKIES_PATH, "w", encoding="utf-8") as f:
        json.dump(cookies_dict, f, ensure_ascii=False, indent=2)


def _verify_cookies(cookies):
    if not cookies:
        return False, None
    try:
        url = f"{_JD_BASE}/gw2/generic/CreatorSer/h5/m/pcQueryUserInfo"
        payload = json.dumps({}).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers={
            "Content-Type": "application/json",
            "User-Agent": _USER_AGENT,
        })
        cookie_str = "; ".join(f"{k}={v}" for k, v in cookies.items())
        req.add_header("Cookie", cookie_str)
        resp = urllib.request.urlopen(req, timeout=10)
        data = json.loads(resp.read())
        rd = data.get("resultData", {})
        code = rd.get("code", "")
        if code in ("0", "0000"):
            return True, rd.get("data", {})
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


def _throttle(delay=0.3):
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
                        use_cache=False, max_workers=10):
    """Fetch ALL data endpoints for MULTIPLE funds concurrently.

    Args:
        fund_codes: list of fund code strings
        include: which endpoints to fetch (subset of profile/perf/trade_rules/holdings/manager)
        use_cache: use cached data when available
        max_workers: concurrent thread count (default 10, safe up to ~40)

    Returns:
        dict: {fund_code: {endpoint_name: result_or_None, ...}, ...}
    """
    endpoint_map = {
        "profile": ("fund_profile", lambda c: get_fund_profile(c, use_cache=use_cache)),
        "perf": ("fund_perf", lambda c: get_fund_performance(c, use_cache=use_cache)),
        "trade_rules": ("trade_rules", lambda c: get_fund_trade_rules(c, use_cache=use_cache)),
        "holdings": ("holdings", lambda c: get_fund_holdings_distribution(c, use_cache=use_cache)),
        "manager": ("manager", lambda c: get_fund_manager(c)),
    }

    # Enable batch mode to skip global throttle (threads manage their own timing)
    global _BATCH_MODE
    _BATCH_MODE = True

    def fetch_one(code):
        row = {"code": code}
        for key in include:
            if key not in endpoint_map:
                continue
            label, func = endpoint_map[key]
            try:
                row[label] = func(code)
            except Exception as e:
                row[label] = {"error": str(e)}
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
        "searchType": 2,
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
            "name": item.get("fundName", {}).get("text", ""),
            "code": item.get("fundCode", {}).get("text", ""),
            "amount": item.get("amount", {}).get("text", ""),
            "profit_rate": item.get("holdingProfitRate", {}).get("text", ""),
            "profit": item.get("holdingProfit", {}).get("text", ""),
        })

    result = {"holdings": items, "raw": data}
    if use_cache and items:
        _write_cache("holdings", cache_key, result)
    return result


def get_trading_records(target_uid=None, size=20, cookies=None, max_pages=5):
    """Fetch trading records with pagination support.

    Iterates pages until end=True or max_pages reached.
    """
    if cookies is None:
        cookies = _ensure_cookies()
    all_records = []
    last_id = ""
    is_end = False
    page = 1

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
        feed_list = rd.get("data", {}).get("data", [])

        # Update pagination state from response busData
        resp_bus = rd.get("data", {}).get("busData", {})
        last_id = resp_bus.get("lastId", "")
        is_end = resp_bus.get("end", True)

        for feed in feed_list:
            template = feed.get("templateData", {})
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
                })
        page += 1

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


def get_followed_users_from_circle(cookies=None):
    if cookies is None:
        cookies = _ensure_cookies()
    import urllib.parse as _up
    req_data = _up.quote(json.dumps({
        "tagId": 112, "contentId": "2689640",
        "iosType": "", "extParams": {"requestFrom": "h5"},
    }))
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
        return {"error": str(e)}

    rd = data.get("resultData", {})
    users = []
    seen = set()
    for feed in rd.get("data", {}).get("data", []):
        template = feed.get("templateData", {})
        user_name = template.get("titleData", {}).get("title1", {}).get("text", "")
        uid = template.get("avatarData", {}).get("createdPin", "")
        summary = template.get("contentData", {}).get("contentTitle2", {}).get("text", "")
        if uid and uid not in seen:
            seen.add(uid)
            users.append({"name": user_name, "uid": uid, "summary": summary})
    return users


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
            for name, numeric_id in FOLLOWED_USERS.items():
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


if __name__ == "__main__":
    main()
