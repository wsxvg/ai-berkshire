#!/usr/bin/env python3
"""为关键 SKILL 加 '必读数据' 段 (AI 一看就知道去哪找)

只在 skills/*.md 源文件加, 然后跑 sync-all-skills 同步到 codex/opencode。
"""
from __future__ import annotations
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / "skills"

# 每个 SKILL 的必读数据 (按代码 / 全局)
DATA_REFS = {
    "fund-monitor": """
## 必读数据 (先读这)

| 文件 | 用途 |
|------|------|
| `data/auto/status.json` | 当前所有大佬持仓快照 + 交易汇总 |
| `backtest/data/trading_by_date_fixed.json` | 按日聚合交易 (448 交易日) |
| `backtest/data/trading_history_fixed.json` | 全部交易记录 (8856 条) |
| `data/fund_charts_meta.json` | 净值元数据 (273 只) |
| `data/fund_name_map.json` | 基金名→代码 (433 条) |
| `data/cache/scores.json` | 30 只预计算评分 |
| `data/cache/ranking.json` | 271 只排行指标 |

**API 入口**: `python tools/jd_finance_api.py --batch-holdings` / `--trading-records <uid>`
""",
    "fund-checklist": """
## 必读数据 (按代码)

| 文件 | 用途 |
|------|------|
| `data/fund_cache/fund_profile_<code>.json` | 基金档案 (类型/规模/经理公司) |
| `data/fund_cache/fund_perf_<code>.json` | 业绩 (近 1/3/6/12 月 + 排名) |
| `data/fund_cache/fund_holdings_<code>.json` | 持仓分布 + 重仓股 |
| `data/fund_cache/trade_rules_<code>.json` | 费率/T+N/限额 |
| `data/fund_cache/fund_manager_<code>.json` | 经理 (任职/历史业绩) |
| `data/fund_cache/fund_notices_<code>.json` | 公告 (限购/分红/清盘) |
| `data/fund_charts/<code>.json` | 净值曲线 (算 RSI/择时) |
| `data/cache/scores.json` | 评分引擎结果 |

**完整指南**: `docs/AI_DATA_GUIDE.md` → fund-checklist 章节
""",
    "fund-sell": """
## 必读数据

| 文件 | 用途 |
|------|------|
| `reports/sim/virtual_portfolio.json` | 虚拟持仓 + PnL |
| `data/trading_records_cache.json` | 交易记录 (供 fund_rules) |
| `data/holdings_diff_cache.json` | 持仓变化 (供 fund_rules) |
| `data/auto/status.json` | 实时状态 |
| `data/industry_valuation.json` | 行业估值 (供卖出择时) |

**输入**: 用户持仓代码 / `--my-holdings` 自动读
""",
    "fund-penetration": """
## 必读数据

| 文件 | 用途 |
|------|------|
| `data/fund_cache/fund_holdings_<code>.json` | 重仓股列表 |
| `data/industry_valuation.json` | 重仓股所属行业 PE 百分位 |
| `data/fund_charts/<code>.json` | 基金净值 (算换手/波动) |

**API 补充**: `python tools/jd_finance_api.py --stock-quotes <stock_code>`
""",
    "fund-scan": """
## 必读数据

| 文件 | 用途 |
|------|------|
| `data/cache/ranking.json` | 271 只排行 (近1/3/6/12月+夏普+回撤) |
| `data/fund_cache/featured_rankings_main.json` | 京东官方 26 榜 TOP20 |
| `data/fund_name_map.json` | 名称→代码 |
| `data/fund_charts_meta.json` | 元数据 |
""",
    "fund-analyze": """
## 必读数据

完整数据 → `docs/AI_DATA_GUIDE.md` → fund-analyze 章节

主要复用: fund-checklist + fund-penetration + fund-sell 三套数据
- `data/cache/scores.json` (评分引擎结果)
- `data/fund_cache/fund_*_<code>.json` (档案/持仓/经理/费率)
- `data/fund_charts/<code>.json` (净值/择时)
""",
    "fund-compare": """
## 必读数据

| 文件 | 用途 |
|------|------|
| `data/fund_cache/fund_profile_<code1,code2>.json` | 多只基金档案 |
| `data/fund_charts/<code>.json` | 净值曲线 (算相关/对比) |
| `data/cache/scores.json` | 评分对比 |
""",
    "portfolio-review": """
## 必读数据

| 文件 | 用途 |
|------|------|
| `reports/sim/virtual_portfolio.json` | 模拟持仓 |
| `data/auto/status.json` | 实时大佬信号 |
| `data/fund_charts_meta.json` | 持仓基金净值 |
| `data/industry_valuation.json` | 行业暴露评估 |
""",
    "news-pulse": """
## 必读数据

| 文件 | 用途 |
|------|------|
| `data/fund_cache/daily_news_main.json` | 当日基金报/财联社/格隆汇资讯 |
""",
    "industry-research": """
## 必读数据

| 文件 | 用途 |
|------|------|
| `data/industry_valuation.json` | 行业 PE/PB 百分位 + 三维共振评分 |
| `data/fund_cache/featured_rankings_main.json` | 主题榜 (光模块/机器人/半导体/...) |

**API 补充**: `python tools/jd_finance_api.py --index-block-info` / `--index-detail <code>`
""",
    "investment-research": """
## 必读数据

| 文件 | 用途 |
|------|------|
| `data/auto/status.json` | 大佬持仓/市场状态 |
| `data/fund_cache/fund_detail_pin_<code>.json` | 完整基金数据 (最强端点) |
| `data/fund_charts/<code>.json` | 净值 (估值百分位) |
| `data/industry_valuation.json` | 行业估值 |
""",
}


def main() -> None:
    updated = 0
    for name, ref in DATA_REFS.items():
        f = SKILLS / f"{name}.md"
        if not f.exists():
            print(f"  skip (not found): {name}")
            continue
        text = f.read_text(encoding="utf-8")
        if "## 必读数据" in text:
            print(f"  skip (already has): {name}")
            continue
        # 找到第一个 # 标题, 在标题之前插入
        lines = text.split("\n")
        insert_at = 0
        for i, line in enumerate(lines):
            if line.startswith("# "):
                insert_at = i
                break
        new_lines = lines[:insert_at] + ref.rstrip("\n").split("\n") + [""] + lines[insert_at:]
        f.write_text("\n".join(new_lines), encoding="utf-8")
        print(f"  + data ref: {name}")
        updated += 1
    print(f"\nUpdated {updated} skills")


if __name__ == "__main__":
    main()
