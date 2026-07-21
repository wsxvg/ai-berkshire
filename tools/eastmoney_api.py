#!/usr/bin/env python3
"""天天基金/东方财富数据源 — 补充京东金融数据不足

数据:
- 历史净值 (lsjz): 从成立至今的全量数据
- 基金排行 (fundranking): 按类型/周期排名

零外部依赖，stdlib only。
"""

import re
import json
import urllib.request
import urllib.parse
import time
from pathlib import Path
from datetime import datetime

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
CACHE_DIR = DATA_DIR / "eastmoney"
CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _fetch_raw(url, timeout=15):
    """GET请求返回原始bytes"""
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0",
        "Referer": "http://fund.eastmoney.com/",
    })
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
        return resp.read()
    except Exception as e:
        print(f"[ERROR] {url}: {e}")
        return b""


def _fetch_html(url, timeout=15):
    """GET请求返回HTML（优先UTF-8，东方财富HTTP头声明charset=utf-8）"""
    raw = _fetch_raw(url, timeout)
    if not raw:
        return ""
    # 东方财富HTTP头声明 charset=utf-8，优先使用
    for encoding in ("utf-8", "gbk", "gb2312"):
        try:
            return raw.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("utf-8", errors="replace")


def get_fund_nav_history(code, max_pages=20):
    """获取基金历史净值（全部历史，分页）
    
    Args:
        code: 6位基金代码
        max_pages: 最大分页数 (每页20条, 20页=400条≈1.6年)
    
    Returns:
        [{date: "2026-07-09", nav: 3.5121, daily_return: 5.94}, ...]
    """
    nav_list = []
    for page in range(1, max_pages + 1):
        url = f"http://fund.eastmoney.com/f10/F10DataApi.aspx?type=lsjz&code={code}&page={page}&per=20"
        html = _fetch_html(url)
        if not html or "暂无数据" in html:
            break

        # 解析: <tr><td>日期</td><td class='tor bold'>净值</td>...
        rows = re.findall(
            r"<tr><td>(\d{4}-\d{2}-\d{2})</td>"
            r"<td class='tor bold'>(.*?)</td>"
            r"<td class='tor bold'>(.*?)</td>"
            r"<td class='tor bold (red|grn)?'>(.*?)</td>",
            html
        )
        if not rows:
            break

        for row in rows:
            date_str, nav_str, acc_nav_str, _, daily_ret_str = row
            try:
                nav_list.append({
                    "date": date_str,
                    "nav": float(nav_str),
                    "acc_nav": float(acc_nav_str) if acc_nav_str else None,
                    "daily_return": float(daily_ret_str.replace("%", "").replace("--", "0")),
                })
            except ValueError:
                continue

        if len(rows) < 20:  # 最后一页
            break
        time.sleep(0.3)  # 礼貌限速

    nav_list.sort(key=lambda x: x["date"])
    return nav_list


def get_fund_ranking(fund_type="all", sort_by="1n", page=1, page_size=50):
    """获取天天基金排行
    
    Args:
        fund_type: 'all'/'gp'/'hh'/'zq'/'zs'/'qdii'/'fof'/'lof'
        sort_by: '1z'(近1周)/'1y'(近1月)/'3y'/'6y'/'1n'(近1年)/'2n'/'3n'/'jn'(今年)/'ln'(成立来)
        page: 页码（从1开始）
        page_size: 每页条数（最大5000）
    
    Returns:
        dict with total_count, rankings list
    """
    url = (f"http://fund.eastmoney.com/data/rankhandler.aspx?"
           f"op=ph&dt=kf&ft={fund_type}&rs=&gs=0&sc={sort_by}&st=desc&"
           f"pi={page}&pn={page_size}&dx=1")
    html = _fetch_html(url)
    if not html:
        return {"total_count": 0, "rankings": []}

    # 解析 var rankData = {datas:[...],allRecords:20015,...}
    match = re.search(r"var rankData = ({.*?});", html, re.DOTALL)
    if not match:
        return {"total_count": 0, "rankings": []}

    js_obj = match.group(1)
    # 东方财富返回的是JS对象（键无引号），转换为标准JSON
    js_obj = re.sub(r"(\w+):", r'"\1":', js_obj)
    js_obj = js_obj.replace("'", '"')
    try:
        data = json.loads(js_obj)
    except json.JSONDecodeError:
        return {"total_count": 0, "rankings": []}

    rankings = []
    for item_str in data.get("datas", []):
        parts = item_str.split(",")
        if len(parts) >= 12:
            def _safe_float(val):
                try:
                    return float(val) if val else 0
                except (ValueError, TypeError):
                    return 0
            rankings.append({
                "code": parts[0],
                "name": parts[1],
                "nav_date": parts[3] if len(parts) > 3 else "",
                "nav": _safe_float(parts[4]) if len(parts) > 4 else 0,
                "daily_return": _safe_float(parts[6]) if len(parts) > 6 else 0,
                "week_return": _safe_float(parts[7]) if len(parts) > 7 else 0,
                "month_return": _safe_float(parts[8]) if len(parts) > 8 else 0,
                "quarter_return": _safe_float(parts[9]) if len(parts) > 9 else 0,
                "half_year_return": _safe_float(parts[10]) if len(parts) > 10 else 0,
                "year_return": _safe_float(parts[11]) if len(parts) > 11 else 0,
            })

    return {
        "total_count": data.get("allRecords", 0),
        "rankings": rankings,
    }


def get_all_funds(fund_type="all", sort_by="1n", max_funds=None):
    """获取全量基金列表（分页拉取，支持20000+基金）
    
    Args:
        fund_type: 'all'/'gp'/'hh'/'zq'/'zs'/'qdii'/'fof'/'lof'
        sort_by: 排序字段（见get_fund_ranking）
        max_funds: 最大获取数量，None=全部
    
    Returns:
        {total_count, rankings: [...]}  rankings包含code/name/收益率等
    """
    all_rankings = []
    page = 1
    page_size = 5000  # 每页最大5000
    
    while True:
        r = get_fund_ranking(fund_type, sort_by, page, page_size)
        total = r["total_count"]
        batch = r["rankings"]
        if not batch:
            break
        all_rankings.extend(batch)
        print(f"  Page {page}: got {len(batch)} funds (total {len(all_rankings)}/{total})")
        
        if max_funds and len(all_rankings) >= max_funds:
            all_rankings = all_rankings[:max_funds]
            break
        if len(all_rankings) >= total:
            break
        page += 1
        time.sleep(0.5)  # 礼貌限速
    
    return {"total_count": r.get("total_count", 0), "rankings": all_rankings}


def build_extended_charts(fund_codes, max_pages=20):
    """为指定基金列表构建扩展净值历史（替代 fund_charts.json 不足）
    
    Returns: {code: [{date, nav, daily_return}, ...]}
    """
    result = {}
    for i, code in enumerate(fund_codes):
        print(f"  [{i+1}/{len(fund_codes)}] {code}...", end=" ", flush=True)
        nav = get_fund_nav_history(code, max_pages)
        if nav:
            result[code] = nav
            print(f"{len(nav)} days ({nav[0]['date']}~{nav[-1]['date']})")
        else:
            print("FAILED")
        time.sleep(0.2)
    return result


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--nav", type=str, help="Get NAV history for fund code")
    parser.add_argument("--ranking", action="store_true", help="Get fund ranking (page 1)")
    parser.add_argument("--all", action="store_true", help="Get ALL funds (paginated)")
    parser.add_argument("--type", type=str, default="all", help="Fund type: all/gp/hh/zq/zs/qdii/fof/lof")
    parser.add_argument("--sort", type=str, default="1n", help="Sort by: 1z/1y/3y/6y/1n/2n/3n/jn/ln")
    parser.add_argument("--pages", type=int, default=20, help="Max pages for NAV")
    parser.add_argument("--max", type=int, default=None, help="Max funds for --all")
    args = parser.parse_args()

    if args.nav:
        data = get_fund_nav_history(args.nav, args.pages)
        print(json.dumps(data[-5:], ensure_ascii=False, indent=2))
        print(f"Total: {len(data)} days")
    elif args.all:
        r = get_all_funds(args.type, args.sort, args.max)
        print(f"Total: {r['total_count']} funds, got {len(r['rankings'])}")
        for item in r["rankings"][:5]:
            print(f"  {item['code']} {item['name']}: 1yr={item['year_return']}%")
    elif args.ranking:
        r = get_fund_ranking(fund_type=args.type, sort_by=args.sort, page=1)
        print(f"Total: {r['total_count']} funds")
        for item in r["rankings"][:5]:
            print(f"  {item['code']} {item['name']}: 1yr={item['year_return']}%")


if __name__ == "__main__":
    main()
