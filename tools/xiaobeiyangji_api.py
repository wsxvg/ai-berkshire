#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
小倍养基 API 模块（零外部依赖）

从 小倍养基 微信小程序抓取 API 数据。
提供了京东金融不覆盖的基金信号数据。

核心API:
  - fundSwingSignals: 基金摆动信号（低区/高区）→ 过度上涨检测
  - accFundHeatTop: 基金热度排行 → 广告基检测
  - getMarketSentiment: 市场情绪指数
  - getMoneyFlow: 北向资金流向

用法:
  python tools/xiaobeiyangji_api.py --test
  python tools/xiaobeiyangji_api.py --swing-signals lowZone
  python tools/xiaobeiyangji_api.py --heat-top stock
  python tools/xiaobeiyangji_api.py --sentiment
  python tools/xiaobeiyangji_api.py --fund-signal 005698
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DATA_DIR = _PROJECT_ROOT / "data"
_CACHE_DIR = _DATA_DIR / "fund_cache"
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36 "
    "MicroMessenger/7.0.20.1781(0x6700143B) NetType/WIFI "
    "MiniProgramEnv/Windows WindowsWechat/WMPF WindowsWechat(0x63090a13)"
)

# 小倍养基 API base URLs
_API_V1 = "https://api.xiaobeiyangji.com/yangji-api/api"
_API_V2 = "https://apiv2.xiaobeiyangji.com/api/app"

# 缓存有效期（秒）
_CACHE_TTL_SWING = 3600       # 摆动信号 1小时
_CACHE_TTL_HEAT = 1800         # 热度排行 30分钟
_CACHE_TTL_SENTIMENT = 3600    # 市场情绪 1小时

# 小倍养基用户凭证
_UNION_ID = "o896o50mccwg8Ye1-tHApVbL1oq8"
_CLIENT_VERSION = "3.8.2.5"
_CLIENT_TYPE = "MPO"


def _cache_path(name: str) -> Path:
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return _CACHE_DIR / f"xbyj_{name}.json"


def _read_cache(name: str, ttl: int) -> dict | None:
    path = _cache_path(name)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text("utf-8"))
        cached_at = data.get("_cached_at", 0)
        if time.time() - cached_at < ttl:
            return data.get("data")
    except Exception:
        pass
    return None


def _write_cache(name: str, data: dict):
    path = _cache_path(name)
    try:
        path.write_text(json.dumps({
            "_cached_at": time.time(),
            "data": data,
        }, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def _post(url: str, body: dict) -> dict | None:
    """发送 POST 请求到小倍养基 API"""
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("User-Agent", _USER_AGENT)
    req.add_header("Accept", "*/*")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"  [xbyj] POST {url} failed: {e}", file=sys.stderr)
        return None


def get_fund_swing_signals(zone: str = "lowZone", hold_and_pick: bool = True) -> list[dict]:
    """获取基金摆动信号（低区/高区）。

    Args:
        zone: "lowZone" 低区(可关注) / "highZone" 高区(警惕)
        hold_and_pick: 是否只返回持有和自选的基金

    Returns:
        [{code, name, zone, heat}, ...]
    """
    cache_name = f"swing_{zone}"
    cached = _read_cache(cache_name, _CACHE_TTL_SWING)
    if cached:
        return cached

    body = {
        "zone": zone,
        "page": 1,
        "pageSize": 50,
        "holdAndPick": hold_and_pick,
        "template": "default",
        "unionId": _UNION_ID,
        "version": _CLIENT_VERSION,
        "clientType": _CLIENT_TYPE,
    }
    resp = _post(f"{_API_V2}/user/valuation/fundSwingSignalsOpportunityByPage", body)
    if not resp or resp.get("code") != 200:
        return []

    data = resp.get("data", {})
    items = data.get("list", [])
    _write_cache(cache_name, items)
    return items


def get_fund_swing_signal_for_code(fund_code: str) -> dict | None:
    """查询某只基金是否在高区/低区。

    Returns:
        {"code": "005698", "zone": "lowZone", "heat": 0} 或 None
    """
    # 查低区
    low_signals = get_fund_swing_signals("lowZone")
    for s in low_signals:
        if s.get("code") == fund_code:
            return s
    # 查高区
    high_signals = get_fund_swing_signals("highZone")
    for s in high_signals:
        if s.get("code") == fund_code:
            return s
    return None


def get_fund_heat_top(fund_type: str = "all") -> list[dict]:
    """获取基金热度排行。

    Args:
        fund_type: "all"/"stock"/"bond"

    Returns:
        [{fundCode, fundName, heat, sectorCode, sectorName, sectorChangeRate}, ...]
    """
    cache_name = f"heat_{fund_type}"
    cached = _read_cache(cache_name, _CACHE_TTL_HEAT)
    if cached:
        return cached

    body = {
        "fundType": fund_type,
        "unionId": _UNION_ID,
        "version": _CLIENT_VERSION,
        "clientType": _CLIENT_TYPE,
    }
    resp = _post(f"{_API_V2}/account/accFundHeatTop", body)
    if not resp or resp.get("code") != 200:
        return []

    data = resp.get("data", {})
    items = data.get("list", [])
    _write_cache(cache_name, items)
    return items


def get_market_sentiment(is_daily: bool = False) -> dict | None:
    """获取市场情绪指数。

    Args:
        is_daily: True=日级别情绪曲线, False=历史日数据

    Returns:
        情绪数据
    """
    cache_name = f"sentiment_{'daily' if is_daily else 'history'}"
    cached = _read_cache(cache_name, _CACHE_TTL_SENTIMENT)
    if cached:
        return cached

    body = {
        "isDaily": is_daily,
        "unionId": _UNION_ID,
        "version": _CLIENT_VERSION,
        "clientType": _CLIENT_TYPE,
    }
    resp = _post(f"{_API_V1}/get-market-sentiment", body)
    if not resp:
        return None

    _write_cache(cache_name, resp)
    return resp


def get_money_flow(is_daily: bool = False) -> dict | None:
    """获取北向资金流向。"""
    body = {
        "isDaily": is_daily,
        "unionId": _UNION_ID,
        "version": _CLIENT_VERSION,
        "clientType": _CLIENT_TYPE,
    }
    return _post(f"{_API_V1}/get-money-flow", body)


def get_market_indices() -> list[dict] | None:
    """获取各大市场指数实时行情。"""
    body = {
        "unionId": _UNION_ID,
        "version": _CLIENT_VERSION,
        "clientType": _CLIENT_TYPE,
    }
    resp = _post(f"{_API_V1}/get-market-index-list", body)
    if resp:
        return resp.get("data", [])
    return None


def get_heat_modifier(fund_code: str) -> float:
    """根据基金热度计算评分修正。
    热度异常高（top 5且heat>500万）→ -0.5~-1.0 扣分
    """
    try:
        heat_list = get_fund_heat_top("stock")
        if not heat_list:
            return 0.0
        for i, item in enumerate(heat_list):
            if item.get("fundCode") == fund_code:
                heat = item.get("heat", 0)
                rank = i + 1
                if rank <= 5 and heat > 5_000_000:
                    return -0.5 - (rank / 10)
                if rank <= 10 and heat > 1_000_000:
                    return -0.3
                break
    except Exception:
        pass
    return 0.0


def get_swing_modifier(fund_code: str) -> float:
    """根据基金摆动信号计算评分修正。
    highZone（高区）→ 扣分
    lowZone  → 不加分不减分（已在评分里反映）
    """
    signal = get_fund_swing_signal_for_code(fund_code)
    if signal:
        zone = signal.get("zone", "")
        if zone == "highZone":
            return -0.8  # 高区，强制扣分
    return 0.0


# ── CLI ──────────────────────────────────────────────────────

def _test():
    """测试 API 连通性"""
    print("测试小倍养基API...")
    indices = get_market_indices()
    if indices:
        print(f"  [OK] 市场指数: {len(indices)}条")
        for idx in indices[:5]:
            print(f"     {idx.get('name','')} {idx.get('current','')} {idx.get('percent','')}%")
    else:
        print("  [FAIL] 市场指数API不通")

    sentiment = get_market_sentiment(False)
    if sentiment:
        print(f"  [OK] 市场情绪: {len(sentiment.get('data',[]))}天")
    else:
        print("  [FAIL] 市场情绪API不通")

    low = get_fund_swing_signals("lowZone")
    high = get_fund_swing_signals("highZone")
    print(f"  [OK] 低区信号: {len(low)}只")
    print(f"  [OK] 高区信号: {len(high)}只")

    heat = get_fund_heat_top("stock")
    if heat:
        print(f"  [OK] 热度排行: {len(heat)}条 (top: {heat[0].get('fundName','')} heat={heat[0].get('heat',0)})")
    else:
        print("  [FAIL] 热度排行API不通")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="小倍养基 API 工具")
    parser.add_argument("--test", action="store_true", help="测试API连通性")
    parser.add_argument("--swing-signals", choices=["lowZone", "highZone"], help="获取摆动信号")
    parser.add_argument("--heat-top", choices=["all", "stock", "bond"], help="获取热度排行")
    parser.add_argument("--sentiment", action="store_true", help="获取市场情绪")
    parser.add_argument("--fund-signal", help="查询某只基金的摆动信号")
    args = parser.parse_args()

    if args.test:
        _test()
    elif args.swing_signals:
        items = get_fund_swing_signals(args.swing_signals)
        print(json.dumps(items, ensure_ascii=False, indent=2))
    elif args.heat_top:
        items = get_fund_heat_top(args.heat_top)
        print(json.dumps(items, ensure_ascii=False, indent=2)[:2000])
    elif args.sentiment:
        data = get_market_sentiment(False)
        print(json.dumps(data, ensure_ascii=False, indent=2)[:1000])
    elif args.fund_signal:
        sig = get_fund_swing_signal_for_code(args.fund_signal)
        if sig:
            print(f"基金 {args.fund_signal} 当前区域: {sig.get('zone')}")
        else:
            print(f"基金 {args.fund_signal} 不在摆动信号中（可能正常区间）")
    else:
        parser.print_help()
