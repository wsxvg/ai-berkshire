#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gen-prompt-context.py — 自动生成 AI IDE 上下文

用法:
    py -3.10 scripts/gen-prompt-context.py              # 输出 PROJECT_DEEP_DIVE.md 路径
    py -3.10 scripts/gen-prompt-context.py --mini       # 迷你版摘要 (< 3KB)
    py -3.10 scripts/gen-prompt-context.py --stats      # 显示项目统计
    py -3.10 scripts/gen-prompt-context.py --checklist  # 输出文件清单 (适合 grep)

作用:
    让任何 IDE AI (Claude Code / CodeBuddy / Cursor / OpenCode) 在 10 秒内
    拿到项目结构 + 关键文件 + 常用命令的摘要, 不用读 100+ 个文件。
"""
import os
import sys
import json
import argparse
from pathlib import Path
from datetime import datetime

PROJECT = Path(__file__).resolve().parent.parent


def get_stats():
    """统计项目文件数 + 大小"""
    stats = {}
    for sub in ['tools', 'scripts', 'backtest', 'tests', 'skills', 'specs', 'docs',
                'codex-skills', 'codex-prompts', 'opencode-skills']:
        p = PROJECT / sub
        if p.exists():
            files = sum(1 for _ in p.rglob('*') if _.is_file())
            stats[sub] = files

    # data / reports 单独统计（太大，只数文件数）
    for sub in ['data', 'reports']:
        p = PROJECT / sub
        if p.exists():
            total = sum(1 for _ in p.rglob('*') if _.is_file())
            md = sum(1 for _ in p.rglob('*.md') if _.is_file())
            json_n = sum(1 for _ in p.rglob('*.json') if _.is_file())
            stats[sub] = f"{total} 文件 (md={md}, json={json_n})"

    # 关键文件大小
    key_files = {
        'tools/jd_finance_api.py': '75K/2876 行 (JD 42 API)',
        'tools/fund_scorer.py': '40K/1105 行 (五维评分)',
        'tools/fund_rules.py': '10K/237 行 (规则引擎)',
        'backtest/engine/backtest.py': '100K/2250 行 (回测引擎)',
        'scripts/auto-pipeline.py': '107K (每日 14:30 管道)',
        'scripts/daily_live.py': '每日实盘模拟',
        'data/auto/status.json': '500KB (实时状态)',
        'data/fund_charts_extended.json': '扩展净值 (部分 8 年)',
        'backtest/data/trading_history_fixed.json': '8856 笔大佬交易',
        'backtest/data/trading_by_date_fixed.json': '448 个交易日聚合',
        'data/fund_name_map.json': '433 条名称映射 (81.2% 覆盖)',
        'data/industry_valuation.json': '1MB (PE 百分位)',
    }
    stats['关键文件'] = key_files
    return stats


def build_mini():
    """迷你版摘要 (适合 < 3KB 上下文窗口)"""
    return """# 项目速记 (MINI)

**项目**: 基金/股票智能投研系统 (AI Berkshire + 京东金融数据 + 五维评分 + 严格回测)

**核心命令** (Python 3.10):
- `py -3.10 run.py` — 一键监控 (实盘持仓 + 11 大佬 + 共识 + 风控)
- `py -3.10 scripts/auto-pipeline.py` — 每日 14:30 抓数据 + 评分 + 报告
- `py -3.10 backtest/run.py` — 完整回测
- `py -3.10 backtest/run_strategies.py` — 12 策略对比

**核心三件套**:
- `tools/jd_finance_api.py` (75K/2876 行) — JD 金融 42 API
- `tools/fund_scorer.py` (40K/1105 行) — 五维评分
- `backtest/engine/backtest.py` (100K/2250 行) — 回测引擎

**关键文件**:
- `data/holdings_snapshot.json` — 当前持仓
- `data/auto/status.json` (500KB) — 实时状态
- `reports/sim/YYYY-MM-DD.md` — 实盘模拟日报
- `data/evolution/best_config.json` — 进化最优参数
- `docs/AI_DATA_GUIDE.md` — 数据地图 (最优先)
- `PROJECT_DEEP_DIVE.md` — 项目深度文档

**SKILL 30 个**:
- 基金 (13): fund-monitor / fund-checklist / fund-sell / fund-analyze / fund-penetration / fund-quarterly / fund-compare / fund-debate / fund-scan / fund-trade / fund-investment-team / fund-strategy-d-review / codebuddy-fund-research
- 股票 (10): investment-research / investment-team / investment-checklist / earnings-review / earnings-team / management-deep-dive / industry-research / industry-funnel / private-company-research / quality-screen
- 辅助 (7): bottleneck-hunter / deep-company-series / dyp-ask / financial-data / news-pulse / portfolio-review / thesis-tracker / wechat-article

**回测最佳** (18 月, 基准沪深 300 = +27.37%):
- 风险调整最优: M20+跟卖2 = +160.53% / 夏普 26.59 / DD 6.04%
- 最高绝对收益: K 无脑跟投 = +82.64% / 夏普 19.01 / DD 4.35%
- 注意: 18 月是过拟合窗口, 28 月 K 跟投只有 +31.66% (年化 12.51%)

**关键约束**:
1. Python 必须 3.10
2. 反未来函数 (cutoff_date 必传)
3. Cookie 在 `data/jd_auth/cookies.json` (2.4 天寿命)
4. IP 风控: 连续 max_pages=10+ 触发, 60-180 秒冷却
5. 五维评分 falsify: 规模<5000万/经理<1年/近3月涨>100% 触发否决

**用户意图触发**:
- "分析今天基金操作" → `py -3.10 scripts/auto-pipeline.py`
- "X 该不该买" → `fund-checklist X`
- "今天大佬买了什么" → `fund-monitor`
- "我这只该卖吗" → `fund-sell X`
- "扫一下基金" → `fund-scan`
"""


def build_checklist():
    """输出文件清单 (适合 IDE 用 grep 查找)"""
    lines = ["# 项目文件清单 (AI 检索用)", ""]
    for sub in ['tools', 'scripts', 'backtest', 'tests', 'skills', 'specs', 'docs']:
        p = PROJECT / sub
        if not p.exists():
            continue
        py_files = sorted(p.rglob('*.py'))
        md_files = sorted(p.rglob('*.md'))
        if py_files:
            lines.append(f"## {sub}/ (Python)")
            for f in py_files:
                rel = f.relative_to(PROJECT)
                size_kb = f.stat().st_size / 1024
                lines.append(f"- `{rel}` ({size_kb:.0f}KB)")
            lines.append("")
        if md_files:
            lines.append(f"## {sub}/ (Markdown)")
            for f in md_files:
                rel = f.relative_to(PROJECT)
                size_kb = f.stat().st_size / 1024
                lines.append(f"- `{rel}` ({size_kb:.0f}KB)")
            lines.append("")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description="生成 AI IDE 上下文摘要")
    ap.add_argument('--mini', action='store_true', help='迷你版 (适合 < 3KB 窗口)')
    ap.add_argument('--stats', action='store_true', help='显示项目统计')
    ap.add_argument('--checklist', action='store_true', help='输出文件清单')
    ap.add_argument('--output', help='输出到文件')
    args = ap.parse_args()

    if args.stats:
        print("=== 项目统计 ===")
        for k, v in get_stats().items():
            if isinstance(v, dict):
                print(f"\n{k}:")
                for fk, fv in v.items():
                    print(f"  {fk}: {fv}")
            else:
                print(f"  {k}: {v}")
        return

    if args.mini:
        content = build_mini()
    elif args.checklist:
        content = build_checklist()
    else:
        deep = PROJECT / 'PROJECT_DEEP_DIVE.md'
        if deep.exists():
            content = f"# 完整文档\n\n请阅读: `{deep}`\n\n(也可用 --mini 看迷你版, --stats 看统计, --checklist 看文件清单)"
        else:
            content = "未找到 PROJECT_DEEP_DIVE.md"

    if args.output:
        Path(args.output).write_text(content, encoding='utf-8')
        print(f"已写入: {args.output}")
    else:
        print(content)


if __name__ == '__main__':
    main()
