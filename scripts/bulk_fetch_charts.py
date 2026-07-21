"""批量拉取所有基金的全量历史净值。

数据源: JD API getFundHistoryNetValuePageInfo (无需 Cookie)
输出: data/fund_charts/{code}.json + 更新索引

用法:
  python scripts/bulk_fetch_charts.py                    # 拉取所有缺失的基金
  python scripts/bulk_fetch_charts.py --force             # 全量重拉
  python scripts/bulk_fetch_charts.py --code 110020       # 拉单只
  python scripts/bulk_fetch_charts.py --max 50            # 最多拉50只
"""
import json
import sys
import time
import argparse
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))

from tools.jd_finance_api import _api_post
from tools.chart_loader import load_single_chart, update_chart, get_chart_index
from tools.eastmoney_api import get_all_funds

CHARTS_DIR = PROJECT / "data" / "fund_charts"
TRADING_FILE = PROJECT / "backtest" / "data" / "trading_by_date_fixed.json"
NAME_MAP_FILE = PROJECT / "data" / "fund_name_map.json"


def fetch_full_nav(code: str, max_pages: int = 10) -> list:
    """JD API 拉取全量净值，返回 [{xAxis, yAxis}, ...] 格式。"""
    all_nav = []
    for page in range(1, max_pages + 1):
        data = _api_post(
            "gw/generic/jj/h5/m/getFundHistoryNetValuePageInfo",
            {"fundCode": code, "pageNum": page, "pageSize": 2000},
            cookies={},
        )
        nav_list = data.get("resultData", {}).get("datas", {}).get("netValueList", [])
        if not nav_list:
            break
        all_nav.extend(nav_list)
        if len(nav_list) < 2000:
            break
        time.sleep(0.15)

    if not all_nav:
        return []

    # 按日期升序
    all_nav.sort(key=lambda x: x.get("date", ""))

    # 用最早的有效净值作为基准
    base_nav = None
    for n in all_nav:
        try:
            v = float(n.get("netValue", 0))
            if v > 0:
                base_nav = v
                break
        except (ValueError, TypeError):
            continue

    if not base_nav:
        return []

    # 转换为 chart 格式
    pts = []
    for n in all_nav:
        try:
            v = float(n.get("netValue", 0))
            if v <= 0:
                continue
            yaxis = (v / base_nav - 1.0) * 100
            pts.append({"xAxis": n.get("date", ""), "yAxis": round(yaxis, 4)})
        except (ValueError, TypeError):
            continue
    return pts


def collect_fund_codes() -> set:
    """合并三来源基金代码列表。"""
    codes = set()

    # 来源1: 交易记录
    if TRADING_FILE.exists():
        data = json.loads(TRADING_FILE.read_text("utf-8"))
        for d, recs in data.items():
            for r in recs:
                c = r.get("fund_code", "")
                if c:
                    codes.add(c)

    # 来源2: 名称映射
    if NAME_MAP_FILE.exists():
        nm = json.loads(NAME_MAP_FILE.read_text("utf-8"))
        codes.update(nm.values())

    # 来源3: 现有 charts 目录
    if CHARTS_DIR.exists():
        for f in CHARTS_DIR.glob("*.json"):
            codes.add(f.stem)

    # 来源4: 全市场 Top 2000
    print("拉取全市场基金列表 (Top 2000)...")
    try:
        r = get_all_funds(sort_by="1n", max_funds=2000)
        for item in r["rankings"]:
            codes.add(item["code"])
        print(f"  全市场获取 {len(r['rankings'])} 只")
    except Exception as e:
        print(f"  全市场拉取失败(非致命): {e}")

    # 过滤空字符串
    codes.discard("")
    return codes


def main():
    parser = argparse.ArgumentParser(description="批量拉取基金全量历史净值")
    parser.add_argument("--code", type=str, help="只拉单只基金")
    parser.add_argument("--force", action="store_true", help="强制重拉已有基金")
    parser.add_argument("--max", type=int, default=0, help="最多拉取数量 (0=全部)")
    args = parser.parse_args()

    CHARTS_DIR.mkdir(parents=True, exist_ok=True)

    if args.code:
        codes = {args.code}
    else:
        codes = collect_fund_codes()

    # 过滤已存在的（除非 --force）
    if not args.force:
        index = get_chart_index(CHARTS_DIR)
        existing = {c for c, info in index.items() if info.get("count", 0) >= 20}
        codes = codes - existing
        print(f"已有足够数据: {len(existing)} 只, 待拉取: {len(codes)} 只")
    else:
        print(f"强制重拉: {len(codes)} 只")

    if args.max > 0:
        codes = set(sorted(codes)[:args.max])
        print(f"限制最多 {args.max} 只")

    if not codes:
        print("无待拉取基金")
        return

    print(f"\n开始拉取 {len(codes)} 只基金...")
    ok = fail = 0
    failed_list = []

    for i, code in enumerate(sorted(codes)):
        try:
            pts = fetch_full_nav(code)
            if pts:
                update_chart(code, pts, CHARTS_DIR)
                ok += 1
                if (i + 1) % 50 == 0:
                    print(f"  [{i+1}/{len(codes)}] ok={ok} fail={fail} (last: {code} {len(pts)}天)")
            else:
                fail += 1
                failed_list.append(code)
        except Exception as e:
            fail += 1
            failed_list.append(code)
            if (i + 1) % 50 == 0:
                print(f"  [{i+1}/{len(codes)}] ok={ok} fail={fail} ERR: {e}")

        time.sleep(0.15)

    print(f"\n=== 完成 ===")
    print(f"成功: {ok}, 失败: {fail}, 总计: {ok + fail}")

    if failed_list:
        print(f"\n失败列表 (前20个): {failed_list[:20]}")
        # 保存失败列表供后续重试
        (PROJECT / "data" / "bulk_fetch_failed.json").write_text(
            json.dumps(failed_list, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
