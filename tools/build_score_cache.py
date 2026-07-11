#!/usr/bin/env python3
"""为自选基金预计算评分, 写入 data/cache/scores.json

前端 /api/score?codes=X,Y 走这个预计算文件, 不每次 spawn python。
"""
from __future__ import annotations
import glob
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backtest.engine.backtest import score_fund_backtest, score_4433, detect_market_state
from tools.technical_indicators import compute_entry_timing_score, compute_rsi


def load_cache(prefix: str) -> dict:
    out = {}
    for f in glob.glob(str(ROOT / "data" / "fund_cache" / f"{prefix}_*.json")):
        code = Path(f).stem.replace(f"{prefix}_", "", 1)
        try:
            out[code] = json.loads(Path(f).read_text(encoding="utf-8"))
        except Exception:
            pass
    return out


def main() -> int:
    fc = json.loads((ROOT / "data" / "fund_charts.json").read_text(encoding="utf-8"))
    trades = json.loads((ROOT / "backtest" / "data" / "trading_by_date_fixed.json").read_text(encoding="utf-8"))
    fr = load_cache("trade_rules")
    fm = load_cache("fund_manager")
    fp = load_cache("fund_profile")
    TODAY = datetime.now().strftime("%Y-%m-%d")
    market = detect_market_state(TODAY, fc)

    # 自选基金
    wl_path = ROOT / "data" / "fund_cache" / "watchlist_mine.json"
    if wl_path.exists():
        wl = json.loads(wl_path.read_text(encoding="utf-8"))
        watch_codes = [f.get("fund_code") for f in wl.get("funds", []) if f.get("fund_code")]
    else:
        watch_codes = list(fr.keys())[:30]

    results = []
    for code in watch_codes:
        if code not in fr:
            continue
        name = fp.get(code, {}).get("full_name") or code
        blocked = False
        block_reason = ""
        pts = fc.get(code, [])
        if len(pts) >= 60:
            timing = compute_entry_timing_score(pts, TODAY)
            if timing.get("should_warn"):
                blocked = True
                block_reason = "RSI超买"
        try:
            s_obj = score_fund_backtest(code, name, fc, None, fr.get(code), fm.get(code), TODAY, trades, fp.get(code))
            s = {"total": round(s_obj.total, 1)}
            for d in ["quality", "cost", "manager", "momentum", "smart_money"]:
                dim = getattr(s_obj, d, None)
                s[d] = round(dim.score, 1) if dim else 0
        except Exception:
            s = {"total": 3.0, "quality": 3.0, "cost": 3.0, "manager": 3.0, "momentum": 3.0, "smart_money": 0}
        p4433 = score_4433(code, TODAY, fc)[1]
        rsi_val = None
        if len(pts) >= 60:
            try:
                valid = [p for p in pts if p["xAxis"] <= TODAY]
                navs = [(100 + float(p["yAxis"])) / 100 for p in valid]
                rsi_val = round(compute_rsi(navs), 1)
            except Exception:
                pass
        results.append({
            "code": code, "name": name, **s,
            "pass4433": p4433, "rsi": rsi_val,
            "blocked": blocked, "blockReason": block_reason,
        })
    results.sort(key=lambda x: -x["total"])

    out_path = ROOT / "data" / "cache" / "scores.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps({
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "today": TODAY,
        "market": market,
        "count": len(results),
        "items": results,
    }, ensure_ascii=False), encoding="utf-8")
    print(f"scores.json: {len(results)} items → {out_path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
