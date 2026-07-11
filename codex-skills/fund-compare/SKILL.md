---
name: fund-compare
user-invocable: true
description: "对比多只基金的5维评分差异——指出各自的优劣势"
---

## Codex adapter note

This skill is generated from `skills/fund-compare.md` so Claude Code and Codex users share one canonical workflow.

- Treat `$ARGUMENTS` as the user's request in the current Codex thread.
- When the source mentions Claude-only surfaces such as Task, Agent, WebSearch, Bash, Read, or Write, use the closest Codex capability available in this session: subagents when available, web search when needed, shell commands for local tools, and normal file edits for workspace files.
- Use shared project tools from `tools/` in this repository. Commands that reference `~/ai-berkshire/tools/...` assume the repo is checked out at `~/ai-berkshire`; if needed, prefer the current workspace path.
- Preserve the research quality rules from `AGENTS.md`: cross-check financial data, use exact arithmetic tools for valuation/math, and clearly label uncertainty and source gaps.

## 触发短语 (triggers)

以下自然语言/命令会自动触发本 SKILL:

- `基金对比 {代码1,代码2}`
- `基金 PK`

# 基金对比分析

对比 $ARGUMENTS 中多只基金的评分差异。

## 输入

运行评分获取数据：

```bash
python tools/fund_scorer.py --score CODE1
python tools/fund_scorer.py --score CODE2
python tools/fund_rules.py --analyze CODE1
python tools/fund_rules.py --analyze CODE2
```

## 执行流程

1. **质量分对比**——同类排名、最大回撤、Sharpe比率差异
2. **成本分对比**——管理费/托管费差异，哪个更划算
3. **经理分对比**——任期、任职回报差异
4. **动量分对比**——近期趋势谁的更强
5. **聪明钱分对比**——大佬更看好哪个
6. **规则对比**——各有何风险和机会

## 输出格式

```
基金A vs 基金B 对比总结：
- 质量：A更优（原因：...）
- 成本：B更优（原因：...）
- 经理：各有优势（A任期长，B回报高）
- 建议场景：保守选A，进取选B
```

## 约束
- 不输出排名分数
- 不直接说"买A卖B"
- 给出对比依据让用户自己决策
