#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
daily_push.py — P5 + B5 实盘推送脚本 (2026-07-13 升级)
=========================================================

每日 14:30 跑:
  1. 调用 daily_check.py 体检
  2. 调 backtest_v2.py 当前最优参数验证 (用最近 30 天数据)
  3. B5 评分仓位调节: 对今日跟买信号按 5 维评分算仓位
  4. 飞书推送到指定群 (可选)
  5. GitHub Actions: .github/workflows/daily.yml

用法:
  py -3.10 scripts/daily_push.py                    # 完整流程
  py -3.10 scripts/daily_push.py --no-feishu        # 跳过飞书
  py -3.10 scripts/daily_push.py --no-backtest      # 跳过回测
"""
import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))


def run(cmd, cwd=None, check=True):
    """运行命令, 返回 (returncode, stdout)"""
    r = subprocess.run(cmd, capture_output=True, text=True,
                       shell=isinstance(cmd, str), cwd=cwd or PROJECT)
    if check and r.returncode != 0:
        print(f"  ❌ 命令失败: {cmd}")
        print(r.stderr)
    return r.returncode, r.stdout


def call_daily_check(no_feishu=True):
    """运行 daily_check.py 拿今日决策"""
    print("\n  📊 Step 1/4 — daily_check 体检 ...")
    cmd = ["py", "-3.10", "-X", "utf8", "scripts/daily_check.py"]
    if no_feishu:
        cmd.append("--no-feishu")
    code, out = run(cmd)
    if code != 0:
        return None
    # 读最新产出
    today = datetime.now().strftime("%Y-%m-%d")
    f = PROJECT / "data" / f"daily_check_{today}.json"
    if f.exists():
        d = json.loads(f.read_text("utf-8", errors="replace"))
        print(f"  ✅ 今日体检完成: {f.relative_to(PROJECT)}")
        return d
    print(f"  ⚠️  找不到 {f}")
    return None


def call_recent_backtest():
    """跑最近 30 天回测, 验证策略当前是否仍有效"""
    print("\n  📈 Step 2/4 — 最近 30 天 V2 策略回测 ...")
    end = datetime.now().strftime("%Y-%m-%d")
    start = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    cmd = ["py", "-3.10", "-X", "utf8", "scripts/backtest_v2.py",
           "--start", start, "--end", end,
           "--no-dynamic", "--no-scorer",
           "--max-holdings", "3", "--min-buyers", "1"]
    code, out = run(cmd)
    if code != 0:
        return None
    # 解析: 找 "年化" / "夏普" / "胜率" 等
    result = {}
    for line in out.split("\n"):
        s = line.strip()
        for k in ["年化", "夏普", "最大回撤", "胜率", "Alpha", "交易"]:
            if k in s and ":" in s:
                try:
                    val = s.split(":")[-1].strip().split()[0].rstrip("%")
                    result[k] = val
                except Exception:
                    pass
    if result:
        print(f"  ✅ 30 天回测: {result}")
    return result


def compute_score_position_today(daily_result):
    """Step 3: B5 评分仓位调节 — 对今日跟买信号, 现场算 5 维评分, 给仓位建议

    返回:
        {
            "positions": [
                {"code": "024239", "name": "华夏全球科技先锋A", "score": 18.5,
                 "position_pct": 0.35, "score_breakdown": {...}},
                ...
            ],
            "summary": {"avg_score": 16.2, "total_position": 0.85}
        }
    """
    print("\n  🎯 Step 3/4 — B5 评分仓位调节 ...")
    if not daily_result or "actions" not in daily_result:
        print("  ⚠️  今日无跟买信号, 跳过评分仓位计算")
        return None

    # 抓出今日的"买入"信号 — 支持多种格式
    buy_signals = []
    for a in daily_result.get("actions", []):
        if a.get("type") in ("buy", "跟买", "follow_buy", "buy_candidate"):
            # 优先从 follow_buy_consensus / ranking_top5 拿结构化数据
            if a.get("type") == "follow_buy":
                for c in daily_result.get("feed_buy_consensus", []):
                    buy_signals.append({
                        "code": "",  # 共识里没 code, 反查
                        "name": c.get("name") or c.get("key", ""),
                        "key": c.get("key", ""),
                    })
            elif a.get("type") == "buy_candidate":
                for t in daily_result.get("ranking_top5", []):
                    buy_signals.append({
                        "code": t.get("code", ""),
                        "name": t.get("name", ""),
                    })
    if not buy_signals:
        print("  ⚠️  今日无买入信号, 跳过")
        return None

    # 延迟导入 (避免 daily_check 失败时无法加载)
    try:
        from backtest_v2 import (
            load_charts, load_fund_cache, load_name_map, load_trading_history,
            compute_score_at
        )
    except Exception as e:
        print(f"  ❌ 导入 backtest_v2 失败: {e}")
        return None

    charts = load_charts()
    fund_cache = load_fund_cache()
    name_to_code = load_name_map()
    trades = load_trading_history()

    # 交易按日聚合
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
    for sig in buy_signals:
        # 拿 code (优先 sig 里的 code, 否则按 name 反查)
        code = sig.get("code") or sig.get("fund_code")
        name = sig.get("name") or sig.get("fund_name") or sig.get("key", "")
        if not code and name:
            code = name_to_code.get(name, "")
        if not code:
            # 尝试模糊: 名字去掉括号
            short_name = name.split("(")[0].strip()
            for n, c in name_to_code.items():
                if short_name in n or n.startswith(short_name[:6]):
                    code = c
                    break
        if not code:
            print(f"  ⚠️  跳过: {name} 无 code")
            continue
        if not name:
            name = code

        # 现场算 5 维评分 (按 today 截止)
        try:
            sc = compute_score_at(code, today, charts, fund_cache,
                                  trades_by_date, name_to_code)
        except Exception as e:
            print(f"  ❌ {name} 评分失败: {e}")
            continue

        # 仓位映射: score 5~25 -> 仓位 0.10~0.40
        # total=12.5 (中性) -> 0.25; total=25 (满分) -> 0.40; total=5 -> 0.10
        position_pct = max(0.10, min(0.40, 0.10 + (sc["total"] - 5) * 0.02))

        positions.append({
            "code": code,
            "name": name,
            "score": sc["total"],
            "position_pct": round(position_pct, 3),
            "score_breakdown": sc["breakdown"],
        })
        bd = sc["breakdown"]
        bd_str = ", ".join(f"{k}={v}" for k, v in bd.items() if v is not None and not k.startswith("_"))
        print(f"  📊 {name} ({code}): score={sc['total']:.1f} → 仓位 {position_pct*100:.1f}%")
        print(f"      {bd_str[:120]}")

    if not positions:
        return None

    # 归一化: 如果总仓位 > 1.0, 按比例缩放
    total = sum(p["position_pct"] for p in positions)
    if total > 1.0:
        for p in positions:
            p["position_pct"] = round(p["position_pct"] / total, 3)

    summary = {
        "avg_score": round(sum(p["score"] for p in positions) / len(positions), 2),
        "total_position": round(sum(p["position_pct"] for p in positions), 3),
        "n": len(positions),
    }
    print(f"  ✅ 评分仓位计算完成: {summary}")
    return {"positions": positions, "summary": summary}


def run_fund_audit(score_pos):
    """Step 4: 6 关审计 - 对 B5 评分仓位中的每只基跑 fund-checklist 逻辑"""
    print("\n  🔍 Step 4/5 — 6 关 AI 审计 (fund-checklist) ...")
    if not score_pos or not score_pos.get("positions"):
        print("  ⚠️  无评分仓位, 跳过审计")
        return None

    try:
        sys.path.insert(0, str(PROJECT / "scripts"))
        from fund_audit import audit_fund
    except Exception as e:
        print(f"  ❌ 导入 fund_audit 失败: {e}")
        return None

    audits = []
    for p in score_pos["positions"]:
        try:
            r = audit_fund(p["code"], p["name"])
            audits.append({
                "code": p["code"],
                "name": p["name"],
                "score": p["score"],
                "position_pct": p["position_pct"],
                "audit": r,
            })
            pass_n = r["pass_count"]
            total_n = r["total"]
            score_n = r["total_score"]
            print(f"  📋 {p['name'][:20]}: {pass_n}/{total_n} pass, audit_score={score_n:.1f}")
        except Exception as e:
            print(f"  ❌ {p['name']} 审计失败: {e}")
    if not audits:
        return None
    # 排序: pass 数少 + 1y 异常高的排前面
    return audits


def push_feishu(daily_result, backtest_result, score_pos, audits):
    """飞书推送 (可选)"""
    if not daily_result:
        return
    print("\n  📤 Step 5/5 — 飞书推送 ...")
    try:
        from tools.feishu_push import send_text
    except Exception as e:
        print(f"  ⚠️  找不到 feishu_push: {e}")
        return
    msg = build_message(daily_result, backtest_result, score_pos, audits)
    try:
        send_text(msg)
        print("  ✅ 已推送")
    except Exception as e:
        print(f"  ❌ 推送失败: {e}")


def build_message(daily, bt, score_pos, audits):
    """构建飞书消息"""
    lines = [f"📊 daily_check 每日体检 ({daily.get('asof', 'today')})"]
    if "actions" in daily:
        for a in daily["actions"]:
            lines.append(f"  • {a.get('type')}: {a.get('summary', '')}")
    if bt:
        lines.append(f"\n📈 V2 策略 30 天表现: {bt}")

    # B5 评分仓位
    if score_pos and score_pos.get("positions"):
        lines.append(f"\n🎯 B5 评分仓位调节 (avg score={score_pos['summary']['avg_score']}):")
        for p in score_pos["positions"]:
            lines.append(
                f"  • {p['name']} ({p['code']}): "
                f"score={p['score']:.1f} → 仓位 {p['position_pct']*100:.1f}%"
            )
        lines.append(
            f"  💰 建议总仓位: {score_pos['summary']['total_position']*100:.1f}%"
        )

    # 6 关 AI 审计
    if audits:
        lines.append(f"\n🔍 6 关 AI 审计 (fund-checklist):")
        for a in audits:
            audit = a["audit"]
            pass_n = audit["pass_count"]
            total_n = audit["total"]
            score_n = audit["total_score"]
            warning = " ⚠️" if pass_n < total_n else ""
            lines.append(
                f"  • {a['name'][:24]} ({a['code']}): "
                f"{pass_n}/{total_n} pass, score={score_n:.1f}{warning}"
            )
            for g in audit["gates"]:
                if not g["pass"]:
                    lines.append(f"      ❌ {g['name']}: {g['reason']}")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-feishu", action="store_true")
    ap.add_argument("--no-backtest", action="store_true")
    ap.add_argument("--no-score-position", action="store_true",
                    help="跳过 B5 评分仓位调节")
    ap.add_argument("--no-audit", action="store_true",
                    help="跳过 6 关 AI 审计")
    args = ap.parse_args()

    print("=" * 70)
    print(f"  daily_check + backtest + B5 评分仓位 每日推送  ({datetime.now().strftime('%Y-%m-%d %H:%M')})")
    print("=" * 70)

    daily = call_daily_check(no_feishu=True)
    bt = None
    if not args.no_backtest:
        bt = call_recent_backtest()

    score_pos = None
    if not args.no_score_position:
        score_pos = compute_score_position_today(daily)

    audits = None
    if not args.no_audit:
        audits = run_fund_audit(score_pos)

    if not args.no_feishu and daily:
        push_feishu(daily, bt, score_pos, audits)

    # 落盘当次日志
    out = PROJECT / "logs" / f"daily_push_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "ts": datetime.now().isoformat(),
        "daily_check": daily,
        "backtest_30d": bt,
        "score_position": score_pos,
        "ai_audit": audits,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n  💾 {out.relative_to(PROJECT)}")
    print("=" * 70)


if __name__ == "__main__":
    main()
