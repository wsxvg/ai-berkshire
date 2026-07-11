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


def _fetch_html(url, timeout=15):
    """GET请求返回HTML"""
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0",
        "Referer": "http://fund.eastmoney.com/",
    })
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
        return resp.read().decode("utf-8")
    except Exception as e:
        print(f"[ERROR] {url}: {e}")
        return ""


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


def get_fund_ranking(fund_type="all", sort_by="1n", page=1):
    """获取天天基金排行
    
    Args:
        fund_type: 'all'/'gp'/'hh'/'zq'/'zs'/'qdii'/'fof'/'lof'
        sort_by: '1z'(近1周)/'1y'(近1月)/'3y'/6y'/1n'(近1年)/'2n'/'3n'/'jn'(今年)/'ln'(成立来)
        page: 页码
    
    Returns:
        dict with total_count, rankings list
    """
    url = (f"http://fund.eastmoney.com/data/rankhandler.aspx?"
           f"op=ph&dt=kf&ft={fund_type}&rs=&gs=0&sc={sort_by}&st=desc&"
           f"pi={page}&pn=50&dx=1")
    html = _fetch_html(url)
    if not html:
        return {"total_count": 0, "rankings": []}

    # 解析 var rankData = {datas:[...],allRecords:19905,...}
    match = re.search(r"var rankData = ({.*?});", html, re.DOTALL)
    if not match:
        return {"total_count": 0, "rankings": []}

    data = json.loads(match.group(1))
    rankings = []
    for item_str in data.get("datas", []):
        parts = item_str.split(",")
        if len(parts) >= 12:
            rankings.append({
                "code": parts[0],
                "name": parts[1],
                "nav_date": parts[3] if len(parts) > 3 else "",
                "nav": float(parts[4]) if len(parts) > 4 and parts[4] else 0,
                "daily_return": float(parts[6]) if len(parts) > 6 and parts[6] else 0,
                "week_return": float(parts[7]) if len(parts) > 7 and parts[7] else 0,
                "month_return": float(parts[8]) if len(parts) > 8 and parts[8] else 0,
                "quarter_return": float(parts[9]) if len(parts) > 9 and parts[9] else 0,
                "half_year_return": float(parts[10]) if len(parts) > 10 and parts[10] else 0,
                "year_return": float(parts[11]) if len(parts) > 11 and parts[11] else 0,
            })

    return {
        "total_count": data.get("allRecords", 0),
        "rankings": rankings,
    }


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
    parser.add_argument("--ranking", action="store_true", help="Get fund ranking")
    parser.add_argument("--pages", type=int, default=20, help="Max pages for NAV")
    args = parser.parse_args()

    if args.nav:
        data = get_fund_nav_history(args.nav, args.pages)
        print(json.dumps(data[-5:], ensure_ascii=False, indent=2))
        print(f"Total: {len(data)} days")
    elif args.ranking:
        r = get_fund_ranking(page=1)
        print(f"Total: {r['total_count']} funds")
        for item in r["rankings"][:5]:
            print(f"  {item['code']} {item['name']}: 1yr={item['year_return']}%")


if __name__ == "__main__":
    main()
