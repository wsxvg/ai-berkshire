#!/usr/bin/env python3
"""60 天 LLM 模式批量回放 — 验证 v3 改造效果

用法:
    py -3.10 tools/replay_llm_60day.py [start_date] [end_date] [label]

输出:
    - reports/llm-vs-machine/replay_<label>.json (含每日 total_value)
    - 控制台打印最终收益 vs 机器基线
"""
import json, sys, os, glob
from datetime import datetime, timedelta
from pathlib import Path
import subprocess

PROJECT = Path(__file__).resolve().parent.parent

def get_trading_dates(start, end):
    """从 reports/sim/*.json 拿真实交易日列表"""
    dates = []
    for fp in sorted(glob.glob(str(PROJECT / "reports" / "sim" / "[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9].json"))):
        d = Path(fp).stem
        if start <= d <= end:
            dates.append(d)
    return dates

def run_one(date_str):
    """跑单日 LLM 模式"""
    vp = PROJECT / "reports" / "llm-vs-machine" / "virtual_portfolio.json"
    proc = subprocess.run(
        [sys.executable, str(PROJECT / "scripts" / "daily_live_llm.py"), "--simulate-date", date_str],
        capture_output=True, text=True, timeout=120,
    )
    if proc.returncode != 0:
        print(f"  [ERROR] {date_str}: {proc.stderr[:200]}")
        return None
    if vp.exists():
        vp_data = json.loads(vp.read_text(encoding="utf-8"))
        snaps = vp_data.get("snapshots", [])
        if snaps:
            return snaps[-1]
    return None

def main():
    start = sys.argv[1] if len(sys.argv) > 1 else "2026-04-13"
    end = sys.argv[2] if len(sys.argv) > 2 else "2026-07-11"
    label = sys.argv[3] if len(sys.argv) > 3 else "v3_baseline"

    # 备份旧 vp
    vp = PROJECT / "reports" / "llm-vs-machine" / "virtual_portfolio.json"
    if vp.exists():
        bk = vp.with_suffix(f".{label}.bak.json")
        if not bk.exists():
            bk.write_text(vp.read_text(encoding="utf-8"), encoding="utf-8")
        vp.unlink()

    dates = get_trading_dates(start, end)
    print(f"=== LLM 60 天回放 {start} ~ {end} ({len(dates)} 天, label={label}) ===")

    results = []
    for d in dates:
        snap = run_one(d)
        if snap:
            results.append({"date": d, **snap})
            tv = snap.get("total_value", 0)
            cash = snap.get("cash", 0)
            n_hold = snap.get("holdings", 0)
            print(f"  {d}: 总={tv:,.0f} 现金={cash:,.0f} 持仓={n_hold}")

    if not results:
        print("[ERROR] 无结果")
        return

    final = results[-1]
    final_tv = final["total_value"]
    initial = 100000
    pnl = (final_tv - initial) / initial * 100
    print(f"\n=== 最终: {final['date']} 总资产 {final_tv:,.0f} ({pnl:+.2f}%) ===")
    print(f"=== 机器基线: 119,272 (+19.27%) ===")
    print(f"=== 差距: {pnl - 19.27:+.2f}% ===")

    # 写回放结果
    out = PROJECT / "reports" / "llm-vs-machine" / f"replay_{label}.json"
    out.write_text(json.dumps({
        "label": label, "start": start, "end": end,
        "initial_cash": initial, "final_total_value": final_tv,
        "pnl_pct": round(pnl, 2),
        "machine_baseline_pct": 19.27,
        "diff_pct": round(pnl - 19.27, 2),
        "daily": results,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"=== 已保存: {out.name} ===")

if __name__ == "__main__":
    main()
