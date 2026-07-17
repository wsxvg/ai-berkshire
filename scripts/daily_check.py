#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
daily_check.py — 每日投资决策快速体检
=====================================

调用 5 个最有用 API, 一键生成今日决策摘要:
  1. /api/ranking  — 优质候选 (Sharpe + 1年>10%)
  2. /api/feed     — 大佬集中买入/卖出
  3. /api/sector   — 行业估值 (低估机会 / 高估风险)
  4. /api/notices  — 自选基金关键公告
  5. /api/status   — 数据完整性 (缓存有没有过期)

输出:
  - data/daily_check_YYYY-MM-DD.json  (机器可读)
  - reports/daily_check_YYYY-MM-DD.md  (人类可读一页纸)
  - 飞书推送 (可选)

用法:
  py -3.10 scripts/daily_check.py
  py -3.10 scripts/daily_check.py --no-feishu
  py -3.10 scripts/daily_check.py --watchlist "005660,016416"
"""
import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, date
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))

DEFAULT_API = "http://127.0.0.1:3456/api"
DEFAULT_WATCHLIST = "013841,024663,024239,016416,011036,012922,012240,005660,002943,018736,011102,019280"


def _find_name(items, key):
    """在 feed items 里反查 key 对应的 fund name"""
    for it in items:
        k = (it.get("code") or "").strip() or (it.get("fund") or "").strip()
        if k == key:
            return it.get("fund", "")
    return ""


def _http_get(url: str, timeout: int = 30) -> dict:
    """调 API, 失败返 error dict"""
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as e:
        try: body = e.read().decode("utf-8", errors="replace")
        except: body = ""
        return {"_http_status": e.code, "_error": body[:200] or e.reason}
    except Exception as e:
        return {"_error": str(e)}


def _http_post(url: str, body: dict, timeout: int = 30) -> dict:
    try:
        req = urllib.request.Request(
            url, method="POST",
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8", errors="replace"))
    except Exception as e:
        return {"_error": str(e)}


def _format_top5(items, score_key="r1y", name_key="name", code_key="code"):
    """取前 5, 格式化"""
    out = []
    for it in (items or [])[:5]:
        out.append({
            "code": it.get(code_key, ""),
            "name": it.get(name_key, ""),
            "score": round(it.get(score_key, 0) or 0, 2),
        })
    return out


def main():
    ap = argparse.ArgumentParser(description="Daily Investment Check")
    ap.add_argument("--api", default=DEFAULT_API, help="API base URL")
    ap.add_argument("--watchlist", default=DEFAULT_WATCHLIST, help="comma-separated fund codes")
    ap.add_argument("--no-feishu", action="store_true", help="不推送飞书")
    ap.add_argument("--no-markdown", action="store_true", help="不写 markdown")
    ap.add_argument("--cash", type=float, default=100000, help="建议仓位计算用本金")
    args = ap.parse_args()

    today = date.today().strftime("%Y-%m-%d")
    base = args.api.rstrip("/")
    print(f"\n{'='*70}\n  每日投资决策体检 — {today}\n  API: {base}\n{'='*70}\n")

    report = {
        "date": today,
        "ts": int(datetime.now().timestamp() * 1000),
        "api_base": base,
        "watchlist": args.watchlist.split(","),
        "actions": [],
    }

    # ───────────── 1. 优质候选 (Sharpe + 1年>10%) ─────────────
    print("  [1/5] 拉取优质候选 (Sharpe 排序 + 1年收益≥10%) ...")
    ranking = _http_get(f"{base}/ranking?sortBy=sharpe&min=10&limit=10")
    if "items" in ranking:
        top5 = _format_top5(ranking["items"], "r1y", "name", "code")
        report["ranking_top5"] = top5
        report["actions"].append({
            "type": "buy_candidate",
            "summary": f"5 只候选: {' / '.join([t['name'][:8] for t in top5])}",
        })
        print(f"        ✅ 找到 {len(top5)} 只 (Sharpe 高, 1年≥10%)")
    else:
        report["ranking_top5"] = []
        report["_ranking_err"] = ranking.get("_error", "unknown")
        print(f"        ⚠️  失败: {ranking.get('_error', '')[:80]}")

    # ───────────── 2. 大佬集中买入 ─────────────
    print("  [2/5] 拉取大佬最近买入动态 ...")
    feed_buy = _http_get(f"{base}/feed?action=buy&pageSize=30")
    items = feed_buy.get("items", []) if isinstance(feed_buy, dict) else []
    report["feed_buy"] = items[:15]
    if items:
        # 共识: 同一基金被多用户买 (code 优先, 没有 code 用 fund_name)
        from collections import Counter
        keys = []
        for i in items:
            k = (i.get("code") or "").strip() or (i.get("fund") or "").strip()
            if k:
                keys.append(k)
        cnt = Counter(keys).most_common(5)
        report["feed_buy_consensus"] = [{"key": c, "buyers": n, "name": _find_name(items, c)} for c, n in cnt]
        report["actions"].append({
            "type": "follow_buy",
            "summary": f"{len(items)} 笔买入, 共识 TOP3: {', '.join([f'{c}×{n}' for c, n in cnt[:3]])}",
        })
        print(f"        ✅ {len(items)} 笔, 共识: {cnt[:3]}")
    else:
        report["feed_buy"] = []
        print(f"        ⚠️  无买入数据")

    # ───────────── 3. 大佬集中卖出 (风控信号) ─────────────
    print("  [3/5] 拉取大佬最近卖出动态 ...")
    feed_sell = _http_get(f"{base}/feed?action=sell&pageSize=30")
    items = feed_sell.get("items", []) if isinstance(feed_sell, dict) else []
    report["feed_sell"] = items[:15]
    if items:
        from collections import Counter
        keys = []
        for i in items:
            k = (i.get("code") or "").strip() or (i.get("fund") or "").strip()
            if k:
                keys.append(k)
        cnt = Counter(keys).most_common(5)
        report["feed_sell_consensus"] = [{"key": c, "sellers": n, "name": _find_name(items, c)} for c, n in cnt]
        report["actions"].append({
            "type": "risk_alert",
            "summary": f"{len(items)} 笔卖出, 共识: {', '.join([f'{c}×{n}' for c, n in cnt[:3]])}",
        })
        print(f"        ✅ {len(items)} 笔, 共识: {cnt[:3]}")
    else:
        report["feed_sell"] = []
        print(f"        ⚠️  无卖出数据")

    # ───────────── 4. 行业估值 ─────────────
    print("  [4/5] 拉取行业估值 ...")
    sector_low = _http_get(f"{base}/sector?status=low")
    sector_high = _http_get(f"{base}/sector?status=high")
    low_count = sector_low.get("total", 0) if isinstance(sector_low, dict) else 0
    high_count = sector_high.get("total", 0) if isinstance(sector_high, dict) else 0
    report["sector_low"] = list((sector_low.get("items") or {}).items())[:8]
    report["sector_high"] = list((sector_high.get("items") or {}).items())[:8]
    report["actions"].append({
        "type": "sector_rotation",
        "summary": f"低估 {low_count} 个行业 / 高估 {high_count} 个行业",
    })
    print(f"        ✅ 低估 {low_count} / 高估 {high_count}")

    # ───────────── 5. 自选关键公告 ─────────────
    print("  [5/5] 检查自选基金关键公告 ...")
    watchlist_enc = urllib.parse.quote(args.watchlist)
    notices = _http_get(f"{base}/notices?codes={watchlist_enc}&criticalOnly=true")
    nlist = notices.get("items", []) if isinstance(notices, dict) else []
    report["critical_notices"] = nlist[:10]
    if nlist:
        report["actions"].append({
            "type": "critical_notice",
            "summary": f"⚠️ {len(nlist)} 条关键公告 (限购/分红/清盘/费率)",
        })
        print(f"        ✅ {len(nlist)} 条关键公告")
    else:
        print(f"        ✅ 无关键公告")

    # ───────────── 6. 数据健康 ─────────────
    print("  [BONUS] 检查数据完整性 ...")
    status = _http_get(f"{base}/status")
    if isinstance(status, dict) and "data" in status:
        report["data_health"] = {
            "watchlist_funds": status["data"]["watchlist"]["funds"],
            "ranking_items": status["data"]["ranking"]["items"],
            "scores_items": status["data"]["scores"]["items"],
            "reports_count": status["data"]["reports"]["count"],
            "issues": status.get("issues", []),
        }
        issues = status.get("issues", [])
        if issues:
            print(f"        ⚠️  {len(issues)} 个问题: {issues[:2]}")
        else:
            print(f"        ✅ 数据完整 (自选 {status['data']['watchlist']['funds']} / 排行 {status['data']['ranking']['items']} / 评分 {status['data']['scores']['items']})")
    else:
        report["data_health"] = {}
        print(f"        ⚠️  /api/status 失败")

    # ───────────── 建议仓位 (粗算) ─────────────
    cash = args.cash
    n_buy = len(report.get("ranking_top5", []))
    if n_buy > 0:
        per_buy = round(cash * 0.15 / min(n_buy, 3), 0)  # 最多 3 只, 单只 15% 仓位
        report["suggested_position"] = {
            "total_cash": cash,
            "max_new_buys": min(n_buy, 3),
            "per_buy_yuan": per_buy,
            "single_position_pct": 15,
        }
    else:
        report["suggested_position"] = None

    # ───────────── 写 JSON ─────────────
    out_json = PROJECT / "data" / f"daily_check_{today}.json"
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n  💾 JSON: {out_json.relative_to(PROJECT)}")

    # ───────────── 写 Markdown ─────────────
    if not args.no_markdown:
        md = _render_markdown(report)
        out_md = PROJECT / "reports" / f"daily_check_{today}.md"
        out_md.parent.mkdir(parents=True, exist_ok=True)
        out_md.write_text(md, encoding="utf-8")
        print(f"  📄 MD:   {out_md.relative_to(PROJECT)}")

    # ───────────── 飞书推送 ─────────────
    if not args.no_feishu:
        try:
            from tools.feishu_push import _send_card
            card = _build_feishu_card(report)
            ok = _send_card(card)
            print(f"  📨 飞书: {'✅' if ok else '⚠️  失败'}")
        except Exception as e:
            print(f"  📨 飞书: ⚠️  {str(e)[:80]}")

    print(f"\n  完成. actions={len(report['actions'])}\n")
    return report


def _render_markdown(r: dict) -> str:
    """生成一页纸决策报告"""
    today = r["date"]
    actions = r.get("actions", [])
    lines = [
        f"# 每日投资决策体检 — {today}",
        "",
        f"**API**: `{r['api_base']}`  |  **自选**: {len(r['watchlist'])} 只  |  **生成时间**: {datetime.fromtimestamp(r['ts']/1000).strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "## 🎯 今日建议",
        "",
    ]
    for a in actions:
        emoji = {"buy_candidate": "🟢", "follow_buy": "👥", "risk_alert": "🔴", "sector_rotation": "🌐", "critical_notice": "⚠️"}.get(a["type"], "•")
        lines.append(f"- {emoji} **{a['type']}**: {a['summary']}")
    lines.append("")

    # 1. 候选
    top5 = r.get("ranking_top5", [])
    if top5:
        lines.append("## 🟢 优质候选 (Sharpe 高 + 1年≥10%)")
        lines.append("")
        lines.append("| # | 基金 | 代码 | 1年收益 |")
        lines.append("|---|------|------|---------|")
        for i, t in enumerate(top5, 1):
            lines.append(f"| {i} | {t['name'][:20]} | `{t['code']}` | +{t['score']:.1f}% |")
        lines.append("")

    # 2. 跟买共识
    cons = r.get("feed_buy_consensus", [])
    if cons:
        lines.append("## 👥 大佬集中买入 (共识 TOP5)")
        lines.append("")
        lines.append("| # | 基金 | 标识 | 大佬数 |")
        lines.append("|---|------|------|-------|")
        for i, c in enumerate(cons, 1):
            name = c.get("name", "")[:18]
            k = c.get("key", "")[:14]
            lines.append(f"| {i} | {name} | `{k}` | {c['buyers']} 人 |")
        lines.append("")

    # 3. 跟卖共识 (风控)
    cons = r.get("feed_sell_consensus", [])
    if cons:
        lines.append("## 🔴 大佬集中卖出 (风控信号)")
        lines.append("")
        lines.append("| # | 基金 | 标识 | 大佬数 |")
        lines.append("|---|------|------|-------|")
        for i, c in enumerate(cons, 1):
            name = c.get("name", "")[:18]
            k = c.get("key", "")[:14]
            lines.append(f"| {i} | {name} | `{k}` | {c['sellers']} 人 |")
        lines.append("")

    # 4. 行业
    low = r.get("sector_low", [])
    high = r.get("sector_high", [])
    if low or high:
        lines.append("## 🌐 行业估值")
        lines.append("")
        if low:
            lines.append("**🟢 低估 (建议加仓)**")
            for code, v in low[:5]:
                pe = v.get("pe_pct")
                lines.append(f"- `{code}` {v.get('name', '')} — PE 百分位 {pe:.1f}%" if pe else f"- `{code}` {v.get('name', '')}")
            lines.append("")
        if high:
            lines.append("**🔴 高估 (建议减仓/止盈)**")
            for code, v in high[:5]:
                pe = v.get("pe_pct")
                lines.append(f"- `{code}` {v.get('name', '')} — PE 百分位 {pe:.1f}%" if pe else f"- `{code}` {v.get('name', '')}")
            lines.append("")

    # 5. 公告
    notes = r.get("critical_notices", [])
    if notes:
        lines.append("## ⚠️ 关键公告 (限购/分红/清盘)")
        lines.append("")
        for n in notes[:8]:
            lines.append(f"- `{n.get('code', '')}` {n.get('title', '')[:50]} ({n.get('date', '')})")
        lines.append("")
    else:
        lines.append("## ⚠️ 关键公告")
        lines.append("")
        lines.append("无关键公告 ✅")
        lines.append("")

    # 6. 数据健康
    h = r.get("data_health", {})
    if h:
        lines.append("## 📊 数据完整性")
        lines.append("")
        lines.append(f"- 自选: {h.get('watchlist_funds', '?')} 只")
        lines.append(f"- 排行: {h.get('ranking_items', '?')} 只")
        lines.append(f"- 评分: {h.get('scores_items', '?')} 只")
        lines.append(f"- 模拟盘日报: {h.get('reports_count', '?')} 份")
        if h.get("issues"):
            lines.append("")
            lines.append("**问题:**")
            for issue in h["issues"]:
                lines.append(f"- ⚠️ {issue}")
        lines.append("")

    # 7. 建议仓位
    sp = r.get("suggested_position")
    if sp:
        lines.append("## 💰 建议仓位 (基于今日本金)")
        lines.append("")
        lines.append(f"- 本金: ¥{sp['total_cash']:,.0f}")
        lines.append(f"- 最多新建仓位: {sp['max_new_buys']} 只")
        lines.append(f"- 单只仓位: {sp['single_position_pct']}% = ¥{sp['per_buy_yuan']:,.0f}")
        lines.append("")

    lines.append("---")
    lines.append("*由 `scripts/daily_check.py` 自动生成. 数据源: 京东金融 API.*")
    return "\n".join(lines)


def _build_feishu_card(r: dict) -> dict:
    """飞书卡片消息"""
    today = r["date"]
    title = f"📊 基金体检 — {today}"
    elements = []
    for a in r.get("actions", []):
        elements.append({
            "tag": "div",
            "text": {"tag": "lark_md", "content": f"**{a['type']}**: {a['summary']}"}
        })
    if r.get("ranking_top5"):
        items_text = "\n".join([f"- {t['name'][:16]} `{t['code']}` (+{t['score']:.1f}%)" for t in r["ranking_top5"]])
        elements.append({"tag": "hr"})
        elements.append({"tag": "div", "text": {"tag": "lark_md", "content": f"**🟢 候选 TOP5**\n{items_text}"}})
    return {
        "config": {"wide_screen_mode": True},
        "header": {"template": "blue", "title": {"tag": "plain_text", "content": title}},
        "elements": elements or [{"tag": "div", "text": {"tag": "plain_text", "content": "无数据"}}],
    }


if __name__ == "__main__":
    main()
