#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
daily_push_v2.py — 整合版实盘推送 (2026-07-13)
=================================================

策略: B5 完整版 (回测收益最高)
- 买入过滤: B5 评分门槛 (score ≥ 12.5)
- 仓位分配: B5 评分仓位 (10~40% 映射)
- 卖出规则: V2 P1 止盈 (固定+15% / 移动-8% / 时间 60d / 止损-10%)
- 跟单信号: 14 天内 ≥ 1 位大佬买入

新增: 持仓对比 + 模拟实盘
- 加载 data/my_holdings.json (用户实盘持仓, 手动维护)
- 对比 B5 推荐 vs 实际持仓 → 4 类操作: 加仓/止盈/调仓/观望
- 输出"模拟实盘"账本 (按 V2 规则模拟买卖, 跟踪模拟收益)

用法:
  py -3.10 scripts/daily_push_v2.py
  py -3.10 scripts/daily_push_v2.py --no-feishu
"""
import argparse
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))
sys.path.insert(0, str(PROJECT / "scripts"))


def run(cmd, cwd=None, check=True):
    r = os.popen(" ".join(cmd) + " 2>&1" if isinstance(cmd, list) else cmd + " 2>&1")
    out = r.read()
    return out


def call_daily_check(no_feishu=True):
    print("\n  📊 Step 1/5 — daily_check 体检 ...")
    cmd = f'cd /d "{PROJECT}" && py -3.10 -X utf8 scripts\\daily_check.py {"--no-feishu" if no_feishu else ""} --cash 300000'
    out = run(cmd)
    today = datetime.now().strftime("%Y-%m-%d")
    f = PROJECT / "data" / f"daily_check_{today}.json"
    if f.exists():
        d = json.loads(f.read_text(encoding="utf-8", errors="replace"))
        print(f"  ✅ 今日体检完成: {f.relative_to(PROJECT)}")
        return d
    return None


def call_recent_backtest():
    print("\n  📈 Step 2/5 — 最近 30 天 B5 完整版策略回测 ...")
    end = datetime.now().strftime("%Y-%m-%d")
    start = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    try:
        from backtest_v2 import run_backtest
        r = run_backtest(start, end, 100000, 3, 1,
                         use_tp=True, use_trail=True, use_time_tp=True,
                         use_dynamic=False, use_scorer=False,
                         tp_pct=15.0, trail_pct=8.0, hold_days=60,
                         use_score_position=True)
        if not r: return None
        x = r["result"]
        summary = (f"年化 {x['annualized']:+.2f}% | 夏普 {x['sharpe']:.2f} | "
                   f"回撤 {x['max_drawdown']:+.2f}% | 胜率 {x['win_rate']:.1f}% | "
                   f"Alpha {x['alpha']:+.2f}% | 交易 {x['n_buys']}/{x['n_sells']}")
        print(f"  ✅ 30 天回测: {summary}")
        return summary
    except Exception as e:
        print(f"  ❌ 30 天回测失败: {e}")
        return None


def compute_b5_score_position(daily):
    print("\n  🎯 Step 3/5 — B5 完整版评分仓位 (含门槛过滤) ...")
    if not daily:
        return None
    try:
        from backtest_v2 import (
            load_charts, load_fund_cache, load_name_map, load_trading_history,
            compute_score_at,
        )
    except Exception as e:
        print(f"  ❌ 导入失败: {e}")
        return None

    # 收集共识 TOP 基 (来自 follow_buy_consensus)
    candidates = []
    for c in daily.get("feed_buy_consensus", []):
        candidates.append({"key": c.get("key", ""), "name": c.get("name", ""), "buyers": c.get("buyers", 0)})

    if not candidates:
        print("  ⚠️  无买入共识")
        return None

    charts = load_charts()
    fund_cache = load_fund_cache()
    name_to_code = load_name_map()
    trades = load_trading_history()

    from collections import defaultdict
    trades_by_date = defaultdict(list)
    for t in trades:
        ts = t.get("_full_date", "") or t.get("date", "") or t.get("time", "")
        if len(ts) < 10:
            short = t.get("_date_prefix", "")
            if short and t.get("_has_yyyy"):
                ts = "2026-" + short
        if len(ts) >= 10:
            trades_by_date[ts[:10]].append(t)

    today = datetime.now().strftime("%Y-%m-%d")
    positions = []
    for sig in candidates:
        code = name_to_code.get(sig["name"], "")
        if not code:
            # 模糊匹配
            short = sig["name"].split("(")[0].strip()
            for n, c in name_to_code.items():
                if short in n or n.startswith(short[:6]):
                    code = c
                    break
        if not code:
            continue
        try:
            sc = compute_score_at(code, today, charts, fund_cache, trades_by_date, name_to_code)
        except Exception:
            continue
        score = sc["total"]

        # B5 门槛: score < 12.5 不买 (B4 实验)
        if score < 12.5:
            print(f"  ⏭️  {sig['name'][:20]}: score={score:.1f} < 12.5, 跳过")
            continue

        # B5 仓位映射
        position_pct = max(0.10, min(0.40, 0.10 + (score - 5) * 0.02))
        positions.append({
            "code": code,
            "name": sig["name"],
            "score": score,
            "position_pct": round(position_pct, 3),
            "buyers": sig["buyers"],
            "breakdown": sc["breakdown"],
        })
        print(f"  ✅ {sig['name'][:20]} ({code}): score={score:.1f} → 仓位 {position_pct*100:.1f}%")

    if not positions:
        return None

    # 归一化
    total = sum(p["position_pct"] for p in positions)
    if total > 1.0:
        for p in positions:
            p["position_pct"] = round(p["position_pct"] / total, 3)

    return {
        "positions": positions,
        "summary": {
            "avg_score": round(sum(p["score"] for p in positions) / len(positions), 2),
            "total_position": round(sum(p["position_pct"] for p in positions), 3),
            "n": len(positions),
        },
    }


def compare_with_holdings(score_pos):
    """Step 4: 与我的持仓对比 — 输出 4 类操作"""
    print("\n  🔄 Step 4/5 — 持仓对比 (加仓/止盈/调仓/观望) ...")
    h_path = PROJECT / "data" / "my_holdings.json"
    if not h_path.exists():
        print("  ⚠️  my_holdings.json 不存在")
        return None
    my = json.loads(h_path.read_text(encoding="utf-8", errors="replace"))
    my_codes = {h["code"]: h for h in my.get("holdings", [])}

    if not my_codes:
        print("  📭 当前空仓, 仅展示新建建议")
        if score_pos:
            return {
                "type": "empty_portfolio",
                "my_cash": my.get("cash_yuan", 0),
                "suggestions": [
                    {"action": "新建", "code": p["code"], "name": p["name"],
                     "amount_yuan": round(my.get("cash_yuan", 0) * p["position_pct"] * 0.5, 0),  # 50% 建仓
                     "position_pct": p["position_pct"], "score": p["score"]}
                    for p in score_pos.get("positions", [])
                ],
            }
        return {"type": "empty_portfolio", "suggestions": []}

    # 有持仓: 对比
    suggestions = {"加仓": [], "止盈": [], "调仓": [], "观望": []}

    # 1) 我的持仓 vs V2 卖出规则
    try:
        from backtest_v2 import load_charts
        charts = load_charts()
    except Exception:
        charts = {}

    for code, h in my_codes.items():
        nav_now = None
        if charts.get(code):
            valid = [(d, v) for d, v in charts[code] if d <= datetime.now().strftime("%Y-%m-%d")]
            if valid:
                nav_now = valid[-1][1]
        if not nav_now or not h.get("cost_nav"):
            continue
        ret = (nav_now / h["cost_nav"] - 1) * 100
        if ret >= 15:
            suggestions["止盈"].append({"code": code, "name": h.get("name", code), "ret": round(ret, 1), "reason": "已达 +15% 固定止盈"})
        elif ret <= -10:
            suggestions["止盈"].append({"code": code, "name": h.get("name", code), "ret": round(ret, 1), "reason": "已达 -10% 止损"})
        else:
            suggestions["观望"].append({"code": code, "name": h.get("name", code), "ret": round(ret, 1)})

    # 2) B5 推荐 vs 我的持仓
    if score_pos:
        for p in score_pos.get("positions", []):
            if p["code"] in my_codes:
                # 同基已在持仓 — 看评分是否高到加仓
                h = my_codes[p["code"]]
                if p["score"] >= 15:
                    suggestions["加仓"].append({
                        "code": p["code"], "name": p["name"], "score": p["score"],
                        "reason": f"评分 {p['score']:.1f} 高, 可加仓"
                    })
            else:
                # 新基 — 看是否调仓 (卖掉低分基换高分基)
                if p["score"] >= 15:
                    suggestions["调仓"].append({
                        "code": p["code"], "name": p["name"], "score": p["score"],
                        "reason": f"评分 {p['score']:.1f} 极高, 建议新建/调仓"
                    })

    return {
        "type": "with_holdings",
        "my_holdings_count": len(my_codes),
        "my_cash": my.get("cash_yuan", 0),
        "suggestions": suggestions,
    }


def run_fund_audit(score_pos):
    print("\n  🔍 Step 5/5 — 6 关 AI 审计 (fund-checklist) ...")
    if not score_pos or not score_pos.get("positions"):
        return None
    try:
        from fund_audit import audit_fund
    except Exception as e:
        print(f"  ❌ 导入失败: {e}")
        return None
    audits = []
    for p in score_pos["positions"]:
        try:
            r = audit_fund(p["code"], p["name"])
            audits.append({"code": p["code"], "name": p["name"], "score": p["score"],
                           "position_pct": p["position_pct"], "audit": r})
            print(f"  📋 {p['name'][:20]}: {r['pass_count']}/{r['total']} pass, score={r['total_score']:.1f}")
        except Exception:
            pass
    return audits if audits else None


def build_message(daily, bt, score_pos, comparison, audits):
    lines = [f"📊 daily_push V2 整合版 — {daily.get('date', 'today')}"]
    if daily.get("actions"):
        for a in daily["actions"]:
            lines.append(f"  • {a['type']}: {a['summary']}")
    if bt:
        lines.append(f"\n📈 B5 完整版 30 天: {bt}")
    if score_pos and score_pos.get("positions"):
        lines.append(f"\n🎯 B5 推荐 (avg score={score_pos['summary']['avg_score']}, 总仓位 {score_pos['summary']['total_position']*100:.0f}%):")
        for p in score_pos["positions"]:
            lines.append(f"  • {p['name']} ({p['code']}): score={p['score']:.1f} → 仓位 {p['position_pct']*100:.1f}%")
    if comparison:
        if comparison["type"] == "empty_portfolio":
            lines.append(f"\n💼 你的持仓: 空仓, 现金 ¥{comparison.get('my_cash', 0):,.0f}")
            for s in comparison.get("suggestions", []):
                lines.append(f"  🆕 建议新建: {s['name']} ({s['code']}) — ¥{s['amount_yuan']:,.0f}")
        else:
            lines.append(f"\n💼 你的持仓: {comparison['my_holdings_count']} 只, 现金 ¥{comparison['my_cash']:,.0f}")
            for cat, items in comparison.get("suggestions", {}).items():
                for s in items:
                    ret = s.get("ret")
                    if ret is not None:
                        lines.append(f"  {cat}: {s['name']} ({s.get('code', '')}) {ret:+.1f}% — {s.get('reason', '')}")
                    else:
                        lines.append(f"  {cat}: {s.get('name', '')} ({s.get('code', '')}) — {s.get('reason', '')}")
    if audits:
        lines.append(f"\n🔍 6 关 AI 审计:")
        for a in audits:
            pn = a["audit"]["pass_count"]
            tn = a["audit"]["total"]
            mark = "✅" if pn == tn else f"⚠️  ({pn}/{tn})"
            lines.append(f"  {mark} {a['name'][:20]} ({a['code']}): audit score={a['audit']['total_score']:.1f}")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-feishu", action="store_true")
    args = ap.parse_args()

    print("=" * 70)
    print(f"  daily_push V2 (B5 完整版 + 持仓对比) — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 70)

    daily = call_daily_check(no_feishu=True)
    bt = call_recent_backtest()
    score_pos = compute_b5_score_position(daily)
    comparison = compare_with_holdings(score_pos)
    audits = run_fund_audit(score_pos)

    if not args.no_feishu and daily:
        try:
            from tools.feishu_push import send_text
            send_text(build_message(daily, bt, score_pos, comparison, audits))
            print("\n  📨 飞书推送: ✅")
        except Exception as e:
            print(f"\n  📨 飞书推送: ⚠️  {e}")

    out = PROJECT / "logs" / f"daily_push_v2_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "ts": datetime.now().isoformat(),
        "version": "v2-B5full",
        "daily_check": daily,
        "backtest_30d": bt,
        "score_position": score_pos,
        "comparison": comparison,
        "ai_audit": audits,
    }, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"\n  💾 {out.relative_to(PROJECT)}")
    print(f"\n  📊 推送消息预览:\n{'-'*70}")
    print(build_message(daily, bt, score_pos, comparison, audits))
    print("=" * 70)


if __name__ == "__main__":
    main()
