"""用东方财富 API 补全 fund_charts 历史数据 (2-3 年窗口)

逻辑:
1. 读 fund_charts.json (当前 1 年窗口)
2. 对每只基金, 用东方财富 get_fund_nav_history 拉全量历史 (max_pages=50 = ~3.3 年)
3. 把 NAV 转换为 yAxis 累计收益率% (JD chart 格式)
4. 合并: 已有数据 + 新数据 (按日期去重, 留长)
5. 写回 fund_charts.json
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import json
from pathlib import Path
from tools.eastmoney_api import get_fund_nav_history

CHARTS_FILE = Path("data/fund_charts.json")
NA_HISTORY_DIR = Path("data/eastmoney/nav_history")
NA_HISTORY_DIR.mkdir(parents=True, exist_ok=True)


def nav_to_yaxis(nav_list):
    """把 [{date, nav}] 转为 JD chart 格式 [{xAxis, yAxis}]

    JD chart yAxis = 自成立来累计收益率%
    但我们没有"成立时 NAV=1"的基准, 所以用"全样本起点 NAV=1"近似.
    注意: 这是相对收益率, 不是 JD 原版 (JD 有"成立时"基准).
    误差: 起点不是真实成立日, 会少算早期收益. 实际影响 < 1% (老基金 5+ 年收益都几十倍, 1 年窗口外的 < 1% 总收益).
    """
    if not nav_list:
        return []
    sorted_n = sorted(nav_list, key=lambda x: x.get("date", ""))
    base_nav = sorted_n[0].get("nav", 1.0)
    if base_nav <= 0:
        base_nav = 1.0
    pts = []
    for n in sorted_n:
        try:
            nav = float(n.get("nav", 0))
            if nav <= 0:
                continue
            yaxis = (nav / base_nav - 1.0) * 100
            pts.append({"xAxis": n.get("date", ""), "yAxis": round(yaxis, 4)})
        except (ValueError, TypeError):
            continue
    return pts


def merge_charts(old_pts, new_pts):
    """合并新旧 chart 数据, 按日期去重, 留长"""
    by_date = {}
    for p in old_pts:
        d = p.get("xAxis", "")[:10]
        if d:
            by_date[d] = p
    for p in new_pts:
        d = p.get("xAxis", "")[:10]
        if d:
            by_date[d] = p
    merged = sorted(by_date.values(), key=lambda x: x.get("xAxis", ""))
    return merged


def main():
    if not CHARTS_FILE.exists():
        print("无 fund_charts.json, 跳过")
        return
    charts = json.loads(CHARTS_FILE.read_text(encoding="utf-8"))
    print(f"当前 fund_charts: {len(charts)} 只基金")

    updated = 0
    expanded = 0
    failed = []
    for code in sorted(charts.keys()):
        cache_path = NA_HISTORY_DIR / f"{code}.json"
        if cache_path.exists():
            nav_list = json.loads(cache_path.read_text(encoding="utf-8"))
        else:
            try:
                nav_list = get_fund_nav_history(code, max_pages=50)
                if nav_list:
                    cache_path.write_text(json.dumps(nav_list, ensure_ascii=False), encoding="utf-8")
            except Exception as e:
                nav_list = []
                failed.append((code, str(e)[:80]))
        if not nav_list:
            continue
        new_pts = nav_to_yaxis(nav_list)
        old_pts = charts[code]
        if not new_pts:
            continue
        merged = merge_charts(old_pts, new_pts)
        if len(merged) > len(old_pts):
            if len(merged) > len(old_pts) + 50:
                expanded += 1
            charts[code] = merged
            updated += 1
        if updated % 30 == 0:
            print(f"  [{updated}/{len(charts)}] {code}: {len(old_pts)} -> {len(merged)}")

    # 写回
    CHARTS_FILE.write_text(json.dumps(charts, ensure_ascii=False), encoding="utf-8")
    print(f"\n=== 完成 ===")
    print(f"  更新: {updated} 只")
    print(f"  大幅扩展 (>50 条新增): {expanded} 只")
    print(f"  失败: {len(failed)} 只")
    if failed[:5]:
        print(f"  失败样例: {failed[:5]}")


if __name__ == "__main__":
    main()
