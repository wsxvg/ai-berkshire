#!/usr/bin/env python3
"""生成排行榜预计算缓存。

每天 daily_live.py 跑完后调用一次 → data/cache/ranking.json
前端 /api/ranking 直接读 JSON, 不再 spawn python 算 sharpe/vol。

性能: API 从 1-2s (含 spawn) 降到 50-200ms (纯读 JSON)
"""
from __future__ import annotations
import json
import statistics
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

CHARTS_DIR = ROOT / "data" / "fund_charts"
NAME_MAP = ROOT / "data" / "fund_name_map.json"
CACHE_DIR = ROOT / "data" / "fund_cache"
META = ROOT / "data" / "fund_charts_meta.json"
OUT = ROOT / "data" / "cache" / "ranking.json"

TODAY = datetime.now().strftime("%Y-%m-%d")


def main() -> int:
    # 读 meta
    meta = json.loads(META.read_text(encoding="utf-8")) if META.exists() else {}
    # 读 name map (name -> code, 反向 code -> name)
    nm = json.loads(NAME_MAP.read_text(encoding="utf-8")) if NAME_MAP.exists() else {}
    code_to_name = {}
    for n, c in nm.items():
        if c not in code_to_name:
            code_to_name[c] = n
    # 读 fund_type
    fund_types = {}
    for f in CACHE_DIR.glob("fund_profile_*.json"):
        code = f.stem.replace("fund_profile_", "", 1)
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
            fund_types[code] = d.get("fund_type") or d.get("fund_type_name") or ""
        except Exception:
            pass

    results = []
    # 读每只基金 chart
    for code in meta.keys():
        chart_path = CHARTS_DIR / f"{code}.json"
        if not chart_path.exists():
            continue
        try:
            pts = json.loads(chart_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        valid = [p for p in pts if p.get("xAxis", "") <= TODAY]
        if len(valid) < 63:
            continue
        navs = [(100 + float(p["yAxis"])) / 100 for p in valid]
        cur = navs[-1]

        r1m = r3m = r6m = r1y = r3y = rSince = None
        if len(navs) > 21:
            r1m = (cur - navs[-21]) / navs[-21] * 100
        if len(navs) > 63:
            r3m = (cur - navs[-63]) / navs[-63] * 100
        if len(navs) > 126:
            r6m = (cur - navs[-126]) / navs[-126] * 100
        if len(navs) > 252:
            r1y = (cur - navs[-252]) / navs[-252] * 100
        if len(navs) > 756:
            r3y = (cur - navs[-756]) / navs[-756] * 100
        rSince = (cur - navs[0]) / navs[0] * 100

        # 夏普 (近1年, 无风险利率 2%)
        sharpe = 0
        if len(navs) >= 252:
            daily = [navs[i + 1] / navs[i] - 1 for i in range(len(navs) - 252, len(navs) - 1)]
            if len(daily) > 1:
                mu = statistics.mean(daily) - 0.02 / 252
                sd = statistics.stdev(daily)
                sharpe = (mu / sd) * (252 ** 0.5) if sd > 0 else 0

        # 最大回撤 (成立以来)
        maxdd = 0
        peak = navs[0]
        for v in navs:
            if v > peak:
                peak = v
            dd = (peak - v) / peak * 100
            if dd > maxdd:
                maxdd = dd

        # 年化波动率 (近1年)
        vol = 0
        if len(navs) >= 252:
            daily = [navs[i + 1] / navs[i] - 1 for i in range(len(navs) - 252, len(navs) - 1)]
            if len(daily) > 1:
                vol = statistics.stdev(daily) * (252 ** 0.5) * 100

        results.append({
            "code": code,
            "name": code_to_name.get(code, "") or code,
            "type": fund_types.get(code, ""),
            "r1m": round(r1m, 2) if r1m is not None else None,
            "r3m": round(r3m, 2) if r3m is not None else None,
            "r6m": round(r6m, 2) if r6m is not None else None,
            "r1y": round(r1y, 2) if r1y is not None else None,
            "r3y": round(r3y, 2) if r3y is not None else None,
            "rSince": round(rSince, 2),
            "sharpe": round(sharpe, 2),
            "maxdd": round(maxdd, 2),
            "vol": round(vol, 2),
        })

    # 排序 (默认近1年)
    results.sort(key=lambda x: (x["r1y"] is None, -(x["r1y"] or 0)))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "today": TODAY,
        "count": len(results),
        "items": results,
    }, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    size = OUT.stat().st_size / 1024
    print(f"ranking.json: {len(results)} items, {size:.1f} KB → {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
