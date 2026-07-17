"""用京东金融 getFundHistoryNetValuePageInfo 拉全量历史, 补全 fund_charts

每个基金缓存到:
- data/fund_cache/fund_chart_full_{code}.json: 完整 NAV 历史 (含 yAxis 转换)
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import json
from pathlib import Path
from tools.jd_finance_api import get_fund_chart_data

CHARTS_FILE = Path("data/fund_charts.json")
CACHE = Path("data/fund_cache")
CACHE.mkdir(parents=True, exist_ok=True)


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
        # 检查缓存
        cache_path = CACHE / f"fund_chart_full_{code}.json"
        if cache_path.exists():
            full_pts = json.loads(cache_path.read_text(encoding="utf-8"))
        else:
            try:
                r = get_fund_chart_data(code, full_history=True)
                full_pts = r.get("chart_points_full", [])
                if full_pts:
                    cache_path.write_text(json.dumps(full_pts, ensure_ascii=False), encoding="utf-8")
            except Exception as e:
                failed.append((code, str(e)[:80]))
                continue
        if not full_pts:
            continue
        old_pts = charts[code]
        # 合并 (JD 全量优先, 因 NAV 转 yAxis 是连续曲线; 旧 chart 1 年是相同格式, 留长即可)
        by_date = {p.get("xAxis", "")[:10]: p for p in old_pts}
        for p in full_pts:
            by_date[p.get("xAxis", "")[:10]] = p
        merged = sorted(by_date.values(), key=lambda x: x.get("xAxis", ""))
        if len(merged) > len(old_pts):
            if len(merged) > len(old_pts) + 50:
                expanded += 1
            charts[code] = merged
            updated += 1
        if updated % 30 == 0:
            print(f"  [{updated}/{len(charts)}] {code}: {len(old_pts)} -> {len(merged)}")

    CHARTS_FILE.write_text(json.dumps(charts, ensure_ascii=False), encoding="utf-8")
    print(f"\n=== 完成 ===")
    print(f"  更新: {updated} 只")
    print(f"  大幅扩展 (>50 条新增): {expanded} 只")
    print(f"  失败: {len(failed)}")
    if failed[:5]:
        print(f"  失败样例: {failed[:5]}")


if __name__ == "__main__":
    main()
