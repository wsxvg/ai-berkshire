---
name: fund-quarterly
description: "AI Berkshire skill: 场外基金季度持仓变化追踪. Source: skills/fund-quarterly.md."
---

## Codex adapter note

This skill is generated from `skills/fund-quarterly.md` so Claude Code and Codex users share one canonical workflow.

- Treat `$ARGUMENTS` as the user's request in the current Codex thread.
- When the source mentions Claude-only surfaces such as Task, Agent, WebSearch, Bash, Read, or Write, use the closest Codex capability available in this session: subagents when available, web search when needed, shell commands for local tools, and normal file edits for workspace files.
- Use shared project tools from `tools/` in this repository. Commands that reference `~/ai-berkshire/tools/...` assume the repo is checked out at `~/ai-berkshire`; if needed, prefer the current workspace path.
- Preserve the research quality rules from `AGENTS.md`: cross-check financial data, use exact arithmetic tools for valuation/math, and clearly label uncertainty and source gaps.


## 触发短语 (triggers)

以下自然语言/命令会自动触发本 SKILL:

- `基金季报 {代码}`
- `季报点评 {代码}`

# 场外基金季度持仓变化追踪

对 $ARGUMENTS 基金追踪历史季度持仓变化，识别风格漂移和调仓趋势。

**支持输入格式**：
- 单个基金代码：`006105`
- 多个基金代码：`006105, 000216`
- `all`：追踪所有已知关注人持仓的基金

**数据来源**：`getFundInvestmentDistributionPageInfo`（支持 `reportDate` 参数查历史）

## 执行流程

### 第一步：确定追踪范围

- 如果输入是 `all`：从 `data/fund_snapshots/` 获取关注人持仓列表，提取所有基金代码
- 如果输入是基金代码：直接使用

### 第二步：遍历6个季度的持仓数据

对每只基金，遍历最近6个季度的持仓分布：

```bash
python3 tools/jd_finance_api.py --fund-holdings {基金代码}
```

季度格式：`2025#4`（2025年Q4）、`2025#3`（2025年Q3）...`2024#1`

### 第三步：对比相邻季度变化

对每对相邻季度，识别：

| 变化类型 | 说明 | 信号 |
|---------|------|------|
| 新进 | 上季不在，本季出现 | 🆕 关注 |
| 清仓 | 上季在，本季消失 | ⚠️ 警告 |
| 增持 | 持仓占比上升 | ↑ |
| 减持 | 持仓占比下降 | ↓ |
| 不变 | 持仓占比稳定 | = |

### 第四步：识别风格漂移

检查基金持仓是否发生重大风格变化：

| 漂移类型 | 判断标准 | 影响 |
|---------|---------|------|
| 行业集中度变化 | 前3大行业占比变化 > 10% | 风格可能转变 |
| 个股更换率 | > 30%重仓股变化 | 基金经理可能更换策略 |
| 市值风格变化 | 大盘/中小盘配比变化 | 风格漂移 |
| 持仓集中度变化 | 前10占比变化 > 15% | 风格变化 |

### 第五步：输出季度调仓报告

报告保存到 `reports/{基金名}/` 目录：

```
reports/{基金名}/{基金名}-fund-quarterly-{YYYYMMDD}.md
```

#### 报告格式

```markdown
# {基金名称} 季度持仓变化追踪

> **基金代码**：{代码}
> **追踪期间**：{起始季度} ~ {最新季度}
> **数据来源**：京东金融API（getFundInvestmentDistributionPageInfo）

---

## 一、持仓变化总览

### 最新季度（{最新季度}）前10重仓股

| # | 股票 | 代码 | 占比 | 较上季变化 | 连续持有季度数 |
|---|------|------|------|-----------|--------------|
| 1 | {stock_1} | {code_1} | {ratio_1}% | {change_1} | {quarters_1} |
| 2 | {stock_2} | {code_2} | {ratio_2}% | {change_2} | {quarters_2} |
| ... | ... | ... | ... | ... | ... |

---

## 二、季度调仓明细

### {季度1} → {季度2}

| 操作 | 股票 | 占比变化 | 说明 |
|------|------|---------|------|
| 🆕 新进 | {stock_a} | +{pct}% | |
| ⚠️ 清仓 | {stock_b} | -{pct}% | |
| ↑ 增持 | {stock_c} | +{pct}% | |
| ↓ 减持 | {stock_d} | -{pct}% | |

### {季度2} → {季度3}
...

---

## 三、风格漂移分析

| 维度 | {季度1} | {最新季度} | 变化 | 判断 |
|------|---------|-----------|------|------|
| 前3大行业占比 | {pct1}% | {pct2}% | {diff}% | {judgement} |
| 重仓股更换率 | — | {rate}% | — | {judgement} |
| 持仓集中度(前10) | {pct1}% | {pct2}% | {diff}% | {judgement} |

**风格漂移结论**：{conclusion}

---

## 四、调仓趋势

### 持续买入的股票（连续多季增持）
| 股票 | 连续增持季度数 | 累计增幅 |
|------|--------------|---------|
| {stock_1} | {n}季度 | +{pct}% |

### 持续卖出的股票（连续多季减持）
| 股票 | 连续减持季度数 | 累计降幅 |
|------|--------------|---------|
| {stock_1} | {n}季度 | -{pct}% |

---

## 五、结论

### 基金经理投资风格
{style_description}

### 调仓逻辑分析
{logic_analysis}

### 关注点
{attention_points}
```

---

## 降级模式

使用 `--offline` 参数时：
- 仅使用 `data/fund_cache/` 中的本地缓存数据
- 报告中标注"数据截至 {缓存日期}，未联网更新"

---

## 注意事项

- 季度持仓数据有1-3个月延迟（基金季报披露时间）
- 风格漂移分析仅供参考，不构成投资建议
- 基金经理可能在季报披露后调仓，实际持仓可能与报告不同
