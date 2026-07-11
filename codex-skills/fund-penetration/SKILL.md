---
name: fund-penetration
description: "AI Berkshire skill: 场外基金持仓穿透分析. Source: skills/fund-penetration.md."
---

## Codex adapter note

This skill is generated from `skills/fund-penetration.md` so Claude Code and Codex users share one canonical workflow.

- Treat `$ARGUMENTS` as the user's request in the current Codex thread.
- When the source mentions Claude-only surfaces such as Task, Agent, WebSearch, Bash, Read, or Write, use the closest Codex capability available in this session: subagents when available, web search when needed, shell commands for local tools, and normal file edits for workspace files.
- Use shared project tools from `tools/` in this repository. Commands that reference `~/ai-berkshire/tools/...` assume the repo is checked out at `~/ai-berkshire`; if needed, prefer the current workspace path.
- Preserve the research quality rules from `AGENTS.md`: cross-check financial data, use exact arithmetic tools for valuation/math, and clearly label uncertainty and source gaps.


## 触发短语 (triggers)

以下自然语言/命令会自动触发本 SKILL:

- `穿透分析 {代码}`
- `底层资产 {代码}`
- `fund-penetration`

# 场外基金持仓穿透分析

对 $ARGUMENTS 基金执行持仓穿透分析，评估底层重仓股质量。

**支持输入格式**：单个或多个基金代码，用逗号/顿号/空格分隔。例如：`006105` 或 `006105, 000216`

**核心逻辑**：基金质量 = Σ(重仓股权重 × 个股评分) × 基金经理能力系数

## 执行流程

### 第一步：获取基金持仓分布

```bash
python3 tools/jd_finance_api.py --fund-holdings {基金代码}
```

获取前10大重仓股及其持仓占比。

如果包含 `--quarter {YYYY#Q}` 参数，获取指定季度的持仓：
```bash
python3 tools/jd_finance_api.py --fund-holdings {基金代码} --quarter 2025#4
```

### 第二步：对每只重仓股执行分析

对每只重仓股，调用现有的投研框架进行评估：

1. **快速评估**：调用 `/investment-checklist` 获取个股评分
2. **深度评估**（可选）：调用 `/investment-research` 获取详细分析

评估维度：
- 商业模式清晰度
- 财务健康度（ROE、现金流、负债）
- 竞争优势（护城河）
- 估值合理性

### 第三步：获取基金经理能力系数

```bash
python3 tools/jd_finance_api.py --fund-manager {基金代码}
```

从API获取基金经理雷达评分，计算能力系数：

```
系数 = (收益能力×0.3 + 选股能力×0.3 + 避险能力×0.2 + 机会把握×0.2) / 5
修正：任职>5年 → ×1.1，<2年 → ×0.8
最终范围：0.5 ~ 1.5
```

### 第四步：计算基金综合评分

```
基金质量 = Σ(重仓股权重 × 个股评分) × 基金经理能力系数
```

其中：
- 重仓股权重 = 该股票占基金净值比例（从API获取）
- 个股评分 = /investment-checklist 的综合评分（★1-5）
- 基金经理能力系数 = 从雷达评分计算（0.5~1.5）

### 第五步：输出穿透分析报告

报告保存到 `reports/{基金名}/` 目录：

```
reports/{基金名}/{基金名}-fund-penetration-{YYYYMMDD}.md
```

#### 报告格式

```markdown
# {基金名称} 持仓穿透分析

> **基金代码**：{代码}
> **分析日期**：{日期}
> **持仓数据截至**：{invest_date}
> **数据来源**：京东金融API + /investment-checklist

---

## 一、基金概况

| 项目 | 数值 |
|------|------|
| 基金全称 | {full_name} |
| 基金类型 | {type} |
| 资产规模 | {scale} |
| 基金经理 | {manager_name}（任职 {tenure}） |
| 基金经理能力系数 | {coefficient}（范围0.5~1.5） |

---

## 二、资产配置

| 类别 | 占比 | 说明 |
|------|------|------|
| 股票 | {stock_pct}% | |
| 债券 | {bond_pct}% | |
| 现金 | {cash_pct}% | |

---

## 三、重仓股穿透评估

| # | 股票 | 代码 | 持仓占比 | Checklist评分 | 核心理由 |
|---|------|------|---------|--------------|---------|
| 1 | {stock_1} | {code_1} | {ratio_1}% | {score_1}/5 | {reason_1} |
| 2 | {stock_2} | {code_2} | {ratio_2}% | {score_2}/5 | {reason_2} |
| ... | ... | ... | ... | ... | ... |

**前10重仓股加权平均评分**：{weighted_avg}/5

---

## 四、基金经理评估

| 维度 | 评分 | 权重 |
|------|------|------|
| 收益能力 | {return_score} | 30% |
| 选股能力 | {stock_pick_score} | 30% |
| 避险能力 | {risk_score} | 20% |
| 机会把握 | {opportunity_score} | 20% |
| 投资经验 | {experience_score} | — |

**能力系数**：{coefficient}
- 计算公式：(收益×0.3 + 选股×0.3 + 避险×0.2 + 机会×0.2) / 5
- 任职修正：{tenure_modifier}

---

## 五、基金综合评分

```
基金质量 = {weighted_avg}（重仓股加权） × {coefficient}（经理系数） = {final_score}
```

| 维度 | 评分 | 权重 | 加权 |
|------|------|------|------|
| 重仓股质量 | {weighted_avg}/5 | 60% | {weighted_60} |
| 基金经理能力 | {coefficient}×5/5 | 25% | {mgr_25} |
| 基金透明度 | {transparency}/5 | 15% | {trans_15} |

**最终评分**：{final_score}/5

---

## 六、穿透结论

### 优势
{strengths}

### 风险
{risks}

### 与其他基金对比
| 对比维度 | 本基金 | 同类均值 | 判断 |
|---------|--------|---------|------|
| 重仓股质量 | {score} | {avg} | |
| 基金经理能力 | {coefficient} | 1.0 | |
| 费率 | {fee}% | {avg_fee}% | |

### 建议
{recommendation}
```

---

## 降级模式

使用 `--offline` 参数时：
- 仅使用 `data/fund_cache/` 中的本地缓存数据
- 重仓股评估跳过API调用，使用已有的本地报告（如有）
- 报告中标注"数据截至 {缓存日期}，未联网更新"

---

## 注意事项

- 持仓数据是季度更新的（基金季报），最新开仓数据可能有1-3个月延迟
- 基金经理能力系数从API实时计算，不使用固定值
- 重仓股评估复用现有的 `/investment-checklist` 框架
- 穿透分析是**参考**，不是**决策依据**——基金表现还受择时、仓位管理等因素影响
