#!/usr/bin/env python3
"""增量更新 fund_charts.json —— 用京东金融接口（非东方财富）。

为什么用京东金融而不是东方财富:
  1. 我们本来就在京东金融平台买基金，cookie 已有
  2. 东方财富 F10DataApi 有反爬限制，经常返回空数据
  3. 京东金融 getFundHistoryNetValuePageInfo 接口稳定、数据准确、支持大分页

本脚本做的事:
  1. 读取 fund_charts.json (格式: {code: [{xAxis: "日期", yAxis: 累计收益率%}, ...]})
  2. 对每只基金, 找到 chart 中最后一个日期
  3. 调用京东金融 getFundHistoryNetValuePageInfo 拉取最近20条净值
  4. 把新日期的净值转换为累计收益率%格式, 追加到 chart 中
  5. 保存更新后的文件

用法:
  python scripts/update_fund_charts.py                     # 更新 data/fund_charts.json (实盘用, ~273只)
  python scripts/update_fund_charts.py --backtest           # 更新 backtest/data/fund_charts.json (回测用, ~2187只)
  python scripts/update_fund_charts.py --both               # 两个都更新
  python scripts/update_fund_charts.py --max-funds 50       # 只更新前50只 (调试用)
  python scripts/update_fund_charts.py --force-full          # 全量重拉 (不用增量, 慢但完整)
"""
import json, sys, time, argparse
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))

from tools.jd_finance_api import _api_post, _ensure_cookies, _load_cookies


def _get_cookies():
    """获取京东金融 cookies"""
    cookies = _ensure_cookies(offline=True)
    if not cookies:
        cookies = _load_cookies()
    if not cookies:
        print("[ERROR] 无京东金融 Cookie，请先运行: python tools/jd_finance_api.py --login")
        sys.exit(1)
    return cookies


def load_charts(path: Path) -> dict:
    if not path.exists():
        print(f"  [WARN] 文件不存在: {path}")
        return {}
    return json.loads(path.read_text("utf-8"))


def save_charts(path: Path, charts: dict):
    path.write_text(json.dumps(charts, ensure_ascii=False), encoding="utf-8")
    print(f"  已保存: {path} ({len(charts)} 只基金)")


def fetch_nav_from_jd(code: str, cookies: dict, page_size: int = 20) -> list:
    """调用京东金融 getFundHistoryNetValuePageInfo 获取净值列表。

    page_size=20 只拉最近20条 (增量更新用)
    page_size=2000 拉全量 (全量重拉用)
    返回: [{date, netValue, dailyProfit, totalNetValue}, ...] 按日期升序
    """
    data = _api_post("gw/generic/jj/h5/m/getFundHistoryNetValuePageInfo",
                     {"fundCode": code, "pageNum": 1, "pageSize": page_size},
                     cookies=cookies)
    nav_list = data.get("resultData", {}).get("datas", {}).get("netValueList", [])
    if not nav_list:
        return []
    # 按日期升序排列 (京东默认是倒序, 最新在前)
    nav_list.sort(key=lambda x: x.get("date", ""))
    return nav_list


def nav_to_chart_pts(nav_list: list, base_nav: float = None) -> list:
    """将京东净值列表转换为 fund_charts 格式。

    格式: [{xAxis: "2026-07-21", yAxis: 93.02}, ...]
    yAxis = (netValue / base_nav - 1) * 100  (累计收益率%)
    """
    if not nav_list:
        return []

    if base_nav is None:
        # 用最早的有效净值作为基准
        for n in nav_list:
            try:
                v = float(n.get("netValue", 0))
                if v > 0:
                    base_nav = v
                    break
            except (ValueError, TypeError):
                continue
    if not base_nav or base_nav <= 0:
        return []

    pts = []
    for n in nav_list:
        try:
            v = float(n.get("netValue", 0))
            if v <= 0:
                continue
            yaxis = (v / base_nav - 1.0) * 100
            pts.append({"xAxis": n.get("date", ""), "yAxis": round(yaxis, 4)})
        except (ValueError, TypeError):
            continue
    return pts


def infer_base_nav(pts: list, nav_list: list) -> float:
    """从已有的 chart 数据反推 base_nav。

    chart 格式: yAxis = (nav / base_nav - 1) * 100
    → base_nav = nav / (1 + yAxis/100)

    从 nav_list 中找一个日期在 pts 中也存在的点, 用它推算 base_nav。
    """
    pts_map = {p["xAxis"]: p["yAxis"] for p in pts}
    for n in nav_list:
        d = n.get("date", "")
        if d in pts_map:
            try:
                nav = float(n.get("netValue", 0))
                if nav > 0:
                    yaxis = pts_map[d]
                    base = nav / (1 + yaxis / 100)
                    if base > 0:
                        return base
            except (ValueError, TypeError):
                continue
    return None


def update_single_fund(code: str, pts: list, cookies: dict, force_full: bool = False) -> tuple:
    """增量更新单只基金的 chart 数据。
    返回 (updated_pts, new_days_added)
    """
    # 找最后日期
    last_date = ""
    if pts:
        for p in pts:
            d = p.get("xAxis", "")
            if d > last_date:
                last_date = d

    if force_full or not pts:
        # 全量拉取
        nav_list = fetch_nav_from_jd(code, cookies, page_size=2000)
        if not nav_list:
            return pts, 0
        new_pts = nav_to_chart_pts(nav_list)
        return new_pts, len(new_pts) - len(pts) if pts else len(new_pts)

    # 增量: 只拉最近20条
    nav_list = fetch_nav_from_jd(code, cookies, page_size=20)
    if not nav_list:
        return pts, 0

    # 反推 base_nav (用已有 chart 数据和新的 nav 数据交叉推算)
    base_nav = infer_base_nav(pts, nav_list)
    if base_nav is None or base_nav <= 0:
        # 如果反推失败, 用 nav_list 最早的净值作为基准重建
        new_pts = nav_to_chart_pts(nav_list)
        if new_pts:
            return new_pts, len(new_pts)
        return pts, 0

    # 筛选出新日期
    existing_dates = {p["xAxis"] for p in pts}
    new_pts = []
    for n in nav_list:
        d = n.get("date", "")
        if d > last_date and d not in existing_dates:
            try:
                v = float(n.get("netValue", 0))
                if v > 0:
                    yaxis = (v / base_nav - 1.0) * 100
                    new_pts.append({"xAxis": d, "yAxis": round(yaxis, 4)})
            except (ValueError, TypeError):
                continue

    if new_pts:
        new_pts.sort(key=lambda x: x["xAxis"])
        return pts + new_pts, len(new_pts)
    return pts, 0


def update_charts_file(charts_path: Path, max_funds: int = 0, force_full: bool = False):
    """更新指定的 fund_charts.json 文件"""
    print(f"\n{'='*60}")
    print(f"更新: {charts_path}")
    print(f"{'='*60}")

    charts = load_charts(charts_path)
    if not charts:
        print("  无数据, 跳过")
        return

    cookies = _get_cookies()
    codes = sorted(charts.keys())
    if max_funds > 0:
        codes = codes[:max_funds]

    total = len(codes)
    updated = 0
    skipped = 0
    failed = 0
    total_new_days = 0

    # 找全局最新日期
    global_max = ""
    for c in codes:
        for p in charts[c]:
            d = p.get("xAxis", "")
            if d > global_max:
                global_max = d
    print(f"  当前最新日期: {global_max}")
    print(f"  待更新基金数: {total}")
    print(f"  数据源: 京东金融 getFundHistoryNetValuePageInfo")

    for i, code in enumerate(codes):
        old_pts = charts[code]
        try:
            new_pts, new_days = update_single_fund(code, old_pts, cookies, force_full)
            if new_days > 0:
                charts[code] = new_pts
                updated += 1
                total_new_days += new_days
                last_new = new_pts[-1].get("xAxis", "")
                if (i + 1) <= 5 or (i + 1) % 50 == 0:
                    print(f"  [{i+1}/{total}] {code}: +{new_days} 天 → {last_new}")
            else:
                skipped += 1
                if (i + 1) <= 3:
                    last_old = old_pts[-1].get("xAxis", "") if old_pts else "N/A"
                    print(f"  [{i+1}/{total}] {code}: 已是最新 ({last_old})")
        except Exception as e:
            failed += 1
            if i < 5 or (i + 1) % 100 == 0:
                print(f"  [{i+1}/{total}] {code}: FAIL {e}")

        # 每50只保存一次 (防止中途崩溃丢数据)
        if (i + 1) % 50 == 0:
            save_charts(charts_path, charts)
            print(f"  --- 进度: {i+1}/{total} | 更新:{updated} 跳过:{skipped} 失败:{failed} ---")

        # 限速 (京东金融接口不要太快)
        time.sleep(0.15)

    # 最终保存
    save_charts(charts_path, charts)

    # 汇总
    new_global_max = ""
    for c in codes:
        if charts.get(c):
            d = charts[c][-1].get("xAxis", "")
            if d > new_global_max:
                new_global_max = d

    print(f"\n  ── 更新完成 ──")
    print(f"  更新: {updated} 只 | 跳过: {skipped} | 失败: {failed}")
    print(f"  新增数据点: {total_new_days}")
    print(f"  原最新日期: {global_max} → 新最新日期: {new_global_max}")


def main():
    parser = argparse.ArgumentParser(description="增量更新 fund_charts.json (京东金融数据源)")
    parser.add_argument("--backtest", action="store_true", help="更新 backtest/data/fund_charts.json")
    parser.add_argument("--both", action="store_true", help="同时更新实盘和回测数据")
    parser.add_argument("--max-funds", type=int, default=0, help="最多更新N只 (0=全部)")
    parser.add_argument("--force-full", action="store_true", help="全量重拉 (不用增量)")
    args = parser.parse_args()

    if args.both:
        update_charts_file(PROJECT / "data" / "fund_charts.json", args.max_funds, args.force_full)
        update_charts_file(PROJECT / "backtest" / "data" / "fund_charts.json", args.max_funds, args.force_full)
    elif args.backtest:
        update_charts_file(PROJECT / "backtest" / "data" / "fund_charts.json", args.max_funds, args.force_full)
    else:
        update_charts_file(PROJECT / "data" / "fund_charts.json", args.max_funds, args.force_full)


if __name__ == "__main__":
    main()
