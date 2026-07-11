#!/usr/bin/env python3
"""生成 SKILL 依赖图 + 触发场景示例

输出: docs/SKILL_GRAPH.md
"""
from __future__ import annotations
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / "skills"
OUT = ROOT / "docs" / "SKILL_GRAPH.md"

# 显式声明的依赖 (skill name -> [依赖的 skill name])
# 从 SKILL 内容里看: "依赖" / "前置" / "调用" / "触发" / "由 X 输出"
DEP_HINTS = {
    "fund-monitor": ["fund-checklist", "fund-analyze"],
    "fund-checklist": ["fund-penetration", "fund-sell"],
    "fund-sell": ["fund-checklist"],
    "fund-penetration": ["investment-checklist"],
    "fund-analyze": ["fund-checklist", "fund-sell"],
    "fund-compare": ["fund-checklist", "fund-penetration"],
    "fund-debate": ["fund-checklist", "fund-penetration"],
    "fund-scan": ["fund-monitor", "fund-checklist"],
    "fund-quarterly": ["fund-checklist", "fund-penetration"],
    "portfolio-review": ["fund-sell", "fund-checklist"],
    "fund-strategy-d-review": ["fund-monitor", "fund-sell", "fund-scan"],
    "fund-trade": ["fund-monitor"],
    "thesis-tracker": ["fund-checklist"],
    "investment-checklist": ["management-deep-dive", "industry-funnel"],
    "investment-research": ["investment-checklist", "industry-research", "management-deep-dive"],
    "investment-team": ["investment-research", "earnings-review"],
    "earnings-review": ["earnings-team", "financial-data"],
    "earnings-team": ["earnings-review"],
    "industry-research": ["industry-funnel"],
    "industry-funnel": ["investment-checklist"],
    "management-deep-dive": ["earnings-review"],
    "private-company-research": ["management-deep-dive", "industry-research"],
    "deep-company-series": ["investment-research", "earnings-review", "management-deep-dive"],
    "wechat-article": ["investment-research", "fund-checklist"],
    "news-pulse": ["earnings-review"],
    "quality-screen": ["fund-checklist"],
    "bottleneck-hunter": ["industry-research", "investment-research"],
    "dyp-ask": ["fund-checklist", "investment-checklist"],
    "financial-data": ["earnings-review"],
    "investment-memo-craft": ["investment-research"],
}


def main() -> None:
    skills = sorted([p.stem for p in SKILLS.glob("*.md")])
    # Build graph
    md = ["# SKILL 依赖图与触发场景\n",
          "> 自动生成自 `scripts/gen-skill-graph.py`。修改 `DEP_HINTS` 字典后重跑。\n",
          "## 依赖关系总览\n",
          "```mermaid"]
    md.append("graph TD")
    # 节点
    for s in skills:
        md.append(f"    {s}[{s}]")
    # 边
    for src, deps in DEP_HINTS.items():
        for d in deps:
            if d in skills:
                md.append(f"    {src} --> {d}")
    md.append("```\n")

    # 按场景分组
    md += ["## 典型触发场景\n"]
    scenarios = [
        ("📊 每日 14:30 实盘", [
            "**触发**: GitHub Actions 14:30 自动",
            "**链路**: `daily_live.py` → 抓取数据 → 五维评分 → 生成 `reports/sim/YYYY-MM-DD.md`",
            "**用户动作**: 打开日报，AI 自动读取 `AI 审计入口` 区块 → 调用 `fund-checklist` / `fund-sell`",
        ]),
        ("🆕 看到大佬新买入一只基金", [
            "**触发**: 用户问 `“蓝鲸跃财今天买了什么”`",
            "**调用链**: `fund-monitor` → 输出新买入清单 → `fund-checklist {code}` → 必要时 `fund-penetration {code}`",
        ]),
        ("💰 持仓要不要卖", [
            "**触发**: 用户问 `“我这只基金该不该卖”`",
            "**调用链**: `fund-sell {code}` → 读 `fund-monitor` 输出 → `fund-checklist` (复查买入逻辑是否还成立)",
        ]),
        ("🔍 主动找新机会", [
            "**触发**: 用户问 `“帮我扫一下最近的好基金”`",
            "**调用链**: `fund-scan` → 多维度筛选 → `fund-checklist` 深度审计 → `fund-penetration` 穿透",
        ]),
        ("📈 行业/主题研究", [
            "**触发**: 用户问 `“半导体现在能买吗”`",
            "**调用链**: `industry-funnel` → 选股 → `industry-research` 行业 → `investment-checklist` 单只 → 必要时 `management-deep-dive`",
        ]),
        ("📰 季报 / 新闻", [
            "**触发**: 用户问 `“腾讯 Q2 财报怎么样”`",
            "**调用链**: `earnings-review` → `earnings-team` (团队视角) → `financial-data` (三表)",
        ]),
        ("✍️ 写文章 / 备忘", [
            "**触发**: 用户说 `“写一篇关于 XX 的公众号文章”`",
            "**调用链**: `investment-research` 准备素材 → `wechat-article` 编排 → 输出 `articles/` 目录",
        ]),
    ]
    for title, lines in scenarios:
        md.append(f"### {title}\n")
        for line in lines:
            md.append(f"- {line}")
        md.append("")

    # 单 SKILL 速查表
    md += ["## 单 SKILL 速查表\n",
           "| SKILL | 一句话 | 触发短语 | 依赖 |",
           "|-------|--------|----------|------|"]
    for s in skills:
        deps = DEP_HINTS.get(s, [])
        path = SKILLS / f"{s}.md"
        # 找 trigger 行
        triggers = []
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                m = re.match(r"^- `(.+)`$", line.strip())
                if m and triggers and len(triggers) < 3:
                    triggers.append(m.group(1))
                elif triggers:
                    break
        title = ""
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.startswith("# "):
                    title = line[2:].strip()
                    break
        md.append(f"| `{s}` | {title} | {' / '.join(triggers[:2]) or '-'} | {', '.join(deps) or '-'} |")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(md), encoding="utf-8")
    print(f"Wrote {OUT.relative_to(ROOT)} ({len(md)} lines)")


if __name__ == "__main__":
    main()
