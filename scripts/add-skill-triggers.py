#!/usr/bin/env python3
"""为 SKILL frontmatter 加 triggers 字段（仅 source skills/*.md）

格式:
---
name: fund-monitor
description: ...
triggers:
  - "持仓监控 {uid?}"
  - "大佬最近买了什么"
  - "基金共识信号"
  - "fund-monitor"
---

然后 codex/opencode 同步会自动带上。
"""
from __future__ import annotations
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / "skills"

# 每个 skill 的中文触发短语 (按 skill 名)
TRIGGERS = {
    "bottleneck-hunter": ["瓶颈分析 {公司}", "找卡脖子环节", "卡脖子行业"],
    "deep-company-series": ["公司深度研究 {公司}", "深度报告 {公司}", "公司基本面"],
    "dyp-ask": ["答疑 {问题}", "dyp 问", "dyp-ask"],
    "earnings-review": ["财报解读 {公司}", "季报点评 {公司}", "业绩点评"],
    "earnings-team": ["财报研究团队", "earnings team"],
    "financial-data": ["财务数据 {公司}", "财务三表 {公司}"],
    "fund-analyze": ["基金综合分析 {代码}", "基金体检 {代码}"],
    "fund-checklist": ["基金买入检查 {代码}", "基金六关 {代码}", "fund-checklist {代码}"],
    "fund-compare": ["基金对比 {代码1,代码2}", "基金 PK"],
    "fund-debate": ["基金辩论 {代码1 vs 代码2}", "多空辩论"],
    "fund-monitor": ["大佬持仓监控", "持仓变化", "基金共识", "fund-monitor"],
    "fund-penetration": ["穿透分析 {代码}", "底层资产 {代码}", "fund-penetration"],
    "fund-quarterly": ["基金季报 {代码}", "季报点评 {代码}"],
    "fund-scan": ["基金扫描", "基金筛选", "扫基金"],
    "fund-sell": ["基金卖出检查 {代码}", "该卖了吗", "fund-sell {代码}"],
    "fund-strategy-d-review": ["策略D复盘", "D策略回顾", "D策略复盘"],
    "fund-trade": ["基金交易记录", "交易流水", "fund-trade"],
    "industry-funnel": ["行业漏斗 {行业}", "行业筛选", "industry-funnel"],
    "industry-research": ["行业研究 {行业}", "行业分析 {行业}"],
    "investment-checklist": ["投资清单 {标的}", "买入检查 {标的}"],
    "investment-memo-craft": ["投资备忘", "写一份 memo", "memo 撰写"],
    "investment-research": ["投资研究 {公司}", "投研报告 {公司}"],
    "investment-team": ["投研团队", "投资团队"],
    "management-deep-dive": ["管理层深挖 {公司}", "管理层分析 {公司}"],
    "news-pulse": ["新闻快讯", "市场动态", "news-pulse"],
    "portfolio-review": ["组合复盘", "持仓复盘", "组合检查"],
    "private-company-research": ["非上市公司研究 {公司}", "未上市研究 {公司}"],
    "quality-screen": ["质量筛选", "质优筛选", "quality-screen"],
    "thesis-tracker": ["投资逻辑跟踪", "thesis 更新", "逻辑复盘"],
    "wechat-article": ["公众号文章 {主题}", "写文章 {主题}"],
}


def update_skill(path: Path) -> bool:
    name = path.stem
    triggers = TRIGGERS.get(name)
    if not triggers:
        return False
    text = path.read_text(encoding="utf-8")
    # 已加过
    if "triggers:" in text[:500]:
        return False
    # 在第一个 # 标题前插入 triggers
    lines = text.split("\n")
    insert_at = 0
    for i, line in enumerate(lines):
        if line.startswith("# "):
            insert_at = i
            break
    trigger_block = ["", "## 触发短语 (triggers)", "", "以下自然语言/命令会自动触发本 SKILL:", ""]
    for t in triggers:
        trigger_block.append(f"- `{t}`")
    trigger_block.append("")
    new_lines = lines[:insert_at] + trigger_block + lines[insert_at:]
    path.write_text("\n".join(new_lines), encoding="utf-8")
    return True


def main() -> None:
    updated = 0
    for f in sorted(SKILLS.glob("*.md")):
        if update_skill(f):
            print(f"  + triggers: {f.name}")
            updated += 1
    print(f"\nUpdated {updated} / {len(list(SKILLS.glob('*.md')))} skills")


if __name__ == "__main__":
    main()
