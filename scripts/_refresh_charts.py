"""快速刷新 fund_chart_full_*.json 到最新 JD 数据 (到 2026-07-31)。"""
import json, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.jd_finance_api import get_fund_chart_data

CACHE = Path("data/fund_cache")
codes = sorted([f.stem.replace("fund_chart_full_", "") for f in CACHE.glob("fund_chart_full_*.json")])
print(f"刷新 {len(codes)} 只基金 chart...")

ok = fail = 0
for i, code in enumerate(codes):
    try:
        r = get_fund_chart_data(code, full_history=True, page_size=2000)
        pts = r.get("chart_points_full", [])
        if pts:
            CACHE.joinpath(f"fund_chart_full_{code}.json").write_text(
                json.dumps(pts, ensure_ascii=False), encoding="utf-8")
            ok += 1
        else:
            fail += 1
    except Exception as e:
        fail += 1
    if (ok + fail) % 50 == 0:
        print(f"  [{ok+fail}/{len(codes)}] ok={ok} fail={fail}")
    time.sleep(0.05)  # ~50ms per call, 273 funds ≈ 15s

print(f"\n完成: ok={ok}, fail={fail}")
