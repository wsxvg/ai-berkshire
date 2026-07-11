---
name: fund-compare
description: "以下自然语言/命令会自动触发本 SKILL:"
user-invocable: true
# Original frontmatter from skills/fund-compare.md:
#   name: fund-compare
#   user-invocable: true
#   description: "对比多只基金的5维评分差异——指出各自的优劣势"
---
## OpenCode adapter note

This skill is generated from `skills/fund-compare.md` — the canonical source.

- Treat `$ARGUMENTS` as the user's request in the current session.
- When the source references Claude-only tool names (Task, Agent, etc.), use the closest capability available in your environment.
- Commands reference `python3 tools/...` — use the correct Python path for your shell.
- Preserve the research quality rules from `AGENTS.md`: cross-check financial data, use exact arithmetic, label uncertainty.

## 触发短语 (triggers)

以下自然语言/命令会自动触发本 SKILL:

- `基金对比 {代码1,代码2}`
- `基金 PK`


## 必读数据

| 文件 | 用途 |
|------|------|
| `data/fund_cache/fund_profile_<code1,code2>.json` | 多只基金档案 |
| `data/fund_charts/<code>.json` | 净值曲线 (算相关/对比) |
| `data/cache/scores.json` | 评分对比 |

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
