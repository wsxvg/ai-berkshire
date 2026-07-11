---
name: fund-trade
user-invocable: true
description: "今日基金交易建议——基于大佬持仓和市场数据，给出买入/卖出/持有建议"
---

## Codex adapter note

This skill is generated from `skills/fund-trade.md` so Claude Code and Codex users share one canonical workflow.

- Treat `$ARGUMENTS` as the user's request in the current Codex thread.
- When the source mentions Claude-only surfaces such as Task, Agent, WebSearch, Bash, Read, or Write, use the closest Codex capability available in this session: subagents when available, web search when needed, shell commands for local tools, and normal file edits for workspace files.
- Use shared project tools from `tools/` in this repository. Commands that reference `~/ai-berkshire/tools/...` assume the repo is checked out at `~/ai-berkshire`; if needed, prefer the current workspace path.
- Preserve the research quality rules from `AGENTS.md`: cross-check financial data, use exact arithmetic tools for valuation/math, and clearly label uncertainty and source gaps.

## 触发短语 (triggers)

以下自然语言/命令会自动触发本 SKILL:

- `基金交易记录`
- `交易流水`
- `fund-trade`

# 今日基金交易建议

在交易日下午3点前使用，基于大佬持仓数据给出今日操作建议。

## 触发方式

"今天买什么" / "今天卖什么" / "我该怎么操作" / "基金建议" / "fund-trade"

## 执行流程

### 第一步：确认数据新鲜度

```bash
python scripts/auto-pipeline.py --offline
```

读取 `data/auto/status.json`，确认：
- `date` 是否是今天（如果不是，提示用户需要先运行 `python scripts/auto-pipeline.py` 获取最新数据）
- `cookie_ok` 是否为 true
- `holdings_ok` 是否为 true

如果数据不是今天的，告诉用户：
> 数据不是最新的，需要先运行 `python scripts/auto-pipeline.py` 获取今日数据。要我现在运行吗？

### 第二步：读取所有数据

读取以下文件：

1. `data/auto/status.json` — 信号汇总、用户排名、交叉验证
2. `data/holdings_snapshot.json` — 大佬最新持仓
3. `data/trading_records_cache.json` — 今日交易流水
4. `data/holdings_diff_cache.json` — 持仓变化
5. `reports/auto/latest.md` — 今日信号报告

### 第三步：分析并给出建议

**核心分析维度：**

1. **买入信号**（从 status.json 的 merged signals 中筛选）
   - strong_buy：≥3人同时买入 → 高置信度
   - buy：2人买入 → 中置信度
   - 考虑交叉验证：如果排名 Top10 大佬也持有 → 更强信号

2. **卖出信号**
   - weak_sell：有人清仓但无人买入
   - 考虑：是真卖出还是正常调仓？

3. **持有建议**
   - 用户当前持仓中，哪些有买入信号支撑 → 坚定持有
   - 哪些有卖出信号 → 考虑减仓
   - 哪些无信号 → 维持现状

4. **可买性检查**（关键！信号再好买不了也白搭）
   - QDII 基金：检查是否限购（很多纳指/标普基金经常限购）
   - C 类 vs A 类：短期持有选 C 类（无申购费），长期选 A 类
   - 最低申购金额：部分基金有高门槛

5. **市场环境**
   - 近期市场整体趋势（可从基金净值变化推断）
   - QDII 基金 vs A 股基金的表现差异

**输出格式：**

```
## 今日操作建议（2026-06-30）

### 🟢 建议买入
| 基金 | 理由 | 置信度 | 可买性 |
|------|------|--------|--------|
| XX基金A | 5位大佬同时买入，排名大佬也持有 | 高 | ✅ 可买 |
| YY基金C | 3位大佬买入，近期表现强势 | 中 | ⚠️ 限购1000元/日 |

### 🔴 建议卖出/减仓
| 基金 | 理由 | 操作 |
|------|------|------|
| ZZ基金C | 有人清仓，无买入 | 减仓50% |

### ⚪ 建议持有
| 基金 | 理由 |
|------|------|
| AA基金A | 多人持有，无卖出信号 |

### 📊 反事实对比（如果我不跟买）
- 跟买组合近期收益：+X.XX%
- 不跟买（维持原持仓）：+Y.YY%
- 差异：跟买是否真的更好？

### ⚠️ 风险提示
- QDII 基金：注意汇率风险 + 限购风险
- 债券基金：注意利率风险
- 行业主题基金：注意行业集中度风险

### 第四步：回答用户追问

用户可能会问：
- "XX基金怎么样？" → 查看该基金在大佬持仓中的情况
- "为什么推荐买这个？" → 解释信号来源和逻辑
- "我应该买多少？" → 根据用户资金量给出仓位建议
- "这个基金风险大吗？" → 查看波动率和回撤

## 关键原则

1. **不替用户做决定**：给建议，但最终决策权在用户
2. **说明风险**：每条建议都附带风险提示
3. **实事求是**：如果数据不支持强烈建议，就说"信号不明确，建议观望"
4. **考虑交易日**：非交易日不给出买入建议（T+1 规则）
5. **考虑时间**：下午3点后的买入建议会延迟到下一个交易日

## 数据不足时的处理

如果 pipeline 数据不完整（如某些大佬数据缺失）：
- 明确告知用户哪些数据缺失
- 基于可用数据给出建议，但降低置信度
- 不要猜测或编造数据

## 与其他 Skill 的关系

- `fund-scan`：全流程扫描（更重，生成完整报告）
- `fund-trade`：轻量级交易建议（本 skill，日常使用）
- `fund-sell`：专门的卖出决策分析
- `fund-checklist`：单只基金的深度分析

用户日常使用 `fund-trade`，需要深度分析时用 `fund-checklist` 或 `fund-scan`。
