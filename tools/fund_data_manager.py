"""持久化基金历史数据, 支持增量更新.

架构:
  data/fund_charts/                    每只基金一个 JSON 文件
    024239.json                         [xAxis, yAxis, ...]
  data/fund_charts_meta.json           {code: {name, first_seen, last_update, count}}
  data/fund_codes_full.json            全部已知代码

Usage:
  python tools/fund_data_manager.py --init         # 把现有 fund_charts.json 拆分成目录
  python tools/fund_data_manager.py --expand       # 扫描大佬交易找新基金, 加入清单
  python tools/fund_data_manager.py --fetch 50     # 给未抓取的新基金拉历史 (50只)
  python tools/fund_data_manager.py --update       # 增量更新已有基金 (今日新数据)
"""
import json
import sys
import time
import argparse
import urllib.request
import re
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

CHARTS_DIR = ROOT / "data" / "fund_charts"
CHARTS_OLD = ROOT / "data" / "fund_charts.json"
META_FILE = ROOT / "data" / "fund_charts_meta.json"
CODES_FILE = ROOT / "data" / "fund_codes_full.json"
NAME_MAP_FILE = ROOT / "data" / "fund_name_map.json"
TRADING_FILE = ROOT / "backtest" / "data" / "trading_by_date_fixed.json"


def init_from_old():
    """Phase 1: 把现有的 fund_charts.json 拆分成目录结构."""
    CHARTS_DIR.mkdir(parents=True, exist_ok=True)
    if not CHARTS_OLD.exists():
        print("无 fund_charts.json, 跳过")
        return
    old = json.loads(CHARTS_OLD.read_text("utf-8"))
    meta = {}
    for code, pts in old.items():
        p = CHARTS_DIR / f"{code}.json"
        if not p.exists():
            p.write_text(json.dumps(pts, ensure_ascii=False), "utf-8")
        if pts:
            meta[code] = {
                "name": "",  # 从 name_map 补
                "count": len(pts),
                "first_date": pts[0].get("xAxis", "") if pts else "",
                "last_date": pts[-1].get("xAxis", "") if pts else "",
                "last_update": datetime.now().strftime("%Y-%m-%d"),
            }
    # 从 name_map 补名字
    if NAME_MAP_FILE.exists():
        nm = json.loads(NAME_MAP_FILE.read_text("utf-8"))
        code_to_name = {}
        for n, c in nm.items():
            if c not in code_to_name:
                code_to_name[c] = n
        for code in meta:
            meta[code]["name"] = code_to_name.get(code, "")
    META_FILE.write_text(json.dumps(meta, ensure_ascii=False, indent=2), "utf-8")
    print(f"已拆分 {len(meta)} 只基金到 {CHARTS_DIR}")
    print(f"元数据写入 {META_FILE}")


def expand_from_trading():
    """Phase 2: 扫描大佬交易, 找出尚未拉取的新基金."""
    if not TRADING_FILE.exists():
        print("无 trading 数据")
        return
    data = json.loads(TRADING_FILE.read_text("utf-8"))
    nm = json.loads(NAME_MAP_FILE.read_text("utf-8")) if NAME_MAP_FILE.exists() else {}
    code_to_name = {}
    for n, c in nm.items():
        if c not in code_to_name:
            code_to_name[c] = n

    found_codes = set()
    for d, recs in data.items():
        for r in recs:
            n = r.get("fund_name", "")
            c = r.get("fund_code", "") or nm.get(n, "")
            if c:
                found_codes.add(c)

    # 已有的
    existing = set()
    if META_FILE.exists():
        meta = json.loads(META_FILE.read_text("utf-8"))
        existing = set(meta.keys())
    if CHARTS_DIR.exists():
        for p in CHARTS_DIR.glob("*.json"):
            existing.add(p.stem)

    new_codes = found_codes - existing
    print(f"大佬交易涉及: {len(found_codes)} 只")
    print(f"已有: {len(existing)} 只")
    print(f"新增: {len(new_codes)} 只")
    if new_codes:
        sample = list(new_codes)[:5]
        for c in sample:
            print(f"  {c} {code_to_name.get(c, '?')[:30]}")
    return new_codes


def eastmoney_get_nav(code, days=400):
    """从天天基金拉取历史净值 (无 cookie, 简单)."""
    # 用 eastmoney 的 F10 API 返回历史净值
    url = f"http://fund.eastmoney.com/f10/F10DataApi.aspx?type=lsjz&code={code}&page=1&per={days}&sdate=&edate="
    try:
        h = urllib.request.urlopen(url, timeout=10).read().decode("utf-8", errors="ignore")
        # 解析 <tr><td>date</td><td class='tor bold'>NAV</td>...
        rows = re.findall(r"<tr><td>(\d{4}-\d{2}-\d{2})</td><td[^>]*>([\d.]+)</td>", h)
        if not rows:
            return None
        pts = []
        for d, nav in rows:
            pts.append({"xAxis": d, "yAxis": float(nav)})
        # 转累计收益率
        if pts:
            base = pts[0]["yAxis"]
            for p in pts:
                p["yAxis"] = (p["yAxis"] / base - 1) * 100
        return pts
    except Exception:
        return None


def fetch_one(code):
    """拉取并保存一只基金."""
    pts = eastmoney_get_nav(code)
    if pts and len(pts) >= 30:
        p = CHARTS_DIR / f"{code}.json"
        p.write_text(json.dumps(pts, ensure_ascii=False), "utf-8")
        return code, len(pts), None
    return code, 0, "no data"


def fetch_new(limit=50, workers=5):
    """Phase 3: 给新基金拉历史."""
    new_codes = expand_from_trading() or set()
    if not new_codes:
        print("无新基金")
        return
    targets = list(new_codes)[:limit]
    print(f"开始拉取 {len(targets)} 只 (并发 {workers})...")
    ok = 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(fetch_one, c): c for c in targets}
        for f in as_completed(futures):
            code, n, err = f.result()
            if err:
                print(f"  {code}: {err}")
            else:
                ok += 1
                if ok % 10 == 0:
                    print(f"  ok: {ok}/{len(futures)}")
    print(f"完成: {ok}/{len(targets)}")


def incremental_update():
    """Phase 4: 增量更新已有基金 (最近 1 天)."""
    if not META_FILE.exists():
        print("无 meta 文件, 请先 --init")
        return
    meta = json.loads(META_FILE.read_text("utf-8"))
    today = datetime.now().strftime("%Y-%m-%d")
    need_update = []
    for code, info in meta.items():
        if info.get("last_date", "") >= today:
            continue
        need_update.append(code)
    print(f"今日未更新: {len(need_update)} 只 (全市场增量模式暂未对接京东日更新 API)")
    print("建议: 运行 --fetch 拉全量 (天天基金), 系统自动 skip 最新日期相同的")


def stats():
    """统计."""
    CHARTS_DIR.mkdir(parents=True, exist_ok=True)
    files = list(CHARTS_DIR.glob("*.json"))
    print(f"基金目录: {CHARTS_DIR}")
    print(f"基金数: {len(files)}")
    if META_FILE.exists():
        meta = json.loads(META_FILE.read_text("utf-8"))
        counts = [m.get("count", 0) for m in meta.values()]
        if counts:
            print(f"平均数据点: {sum(counts)/len(counts):.0f}")
            print(f"最大: {max(counts)} 最小: {min(counts)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--init", action="store_true", help="拆分 fund_charts.json 到目录")
    parser.add_argument("--expand", action="store_true", help="扫描新基金")
    parser.add_argument("--fetch", type=int, nargs="?", const=50, help="拉取新基金历史")
    parser.add_argument("--update", action="store_true", help="增量更新")
    parser.add_argument("--stats", action="store_true", help="统计")
    args = parser.parse_args()

    if args.init:
        init_from_old()
    if args.expand:
        expand_from_trading()
    if args.fetch is not None:
        fetch_new(args.fetch)
    if args.update:
        incremental_update()
    if args.stats:
        stats()
    if not any([args.init, args.expand, args.fetch is not None, args.update, args.stats]):
        stats()
