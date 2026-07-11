---
name: fund-investment-team
user-invocable: true
description: "4 大师并行分析基金: 段永平(产品/规模) + 巴菲特(费率/回报) + 芒格(赛道/风险) + 李录(经理/团队)"
---

## Codex adapter note

This skill is generated from `skills/fund-investment-team.md` so Claude Code and Codex users share one canonical workflow.

- Treat `$ARGUMENTS` as the user's request in the current Codex thread.
- When the source mentions Claude-only surfaces such as Task, Agent, WebSearch, Bash, Read, or Write, use the closest Codex capability available in this session: subagents when available, web search when needed, shell commands for local tools, and normal file edits for workspace files.
- Use shared project tools from `tools/` in this repository. Commands that reference `~/ai-berkshire/tools/...` assume the repo is checked out at `~/ai-berkshire`; if needed, prefer the current workspace path.
- Preserve the research quality rules from `AGENTS.md`: cross-check financial data, use exact arithmetic tools for valuation/math, and clearly label uncertainty and source gaps.

## 触发短语 (triggers)

以下自然语言/命令会自动触发本 SKILL:

- `基金投研团队`
- `4 大师分析基金`
- `fund-investment-team`


## 必读数据 (先读这)

| 文件 | 用途 |
|------|------|
| `data/fund_cache/fund_profile_<code>.json` | 基金档案 (规模/类型/成立日) |
| `data/fund_cache/fund_manager_<code>.json` | 经理任职 |
| `data/fund_cache/trade_rules_<code>.json` | 费率 |
| `data/fund_cache/holdings_<code>.json` | 持仓行业/股票 |
| `backtest/data/fund_charts.json` | 净值曲线 (按日期) |
| `data/cache/scores.json` | 30 只预计算评分 |
| `data/fund_cache/daily_news/{asof}.json` | 截至 asof 的新闻 (按日期, 修复未来函数) |
| `backtest/data/trading_history_fixed.json` | 大佬交易 (8856 条) |


# 基金投研团队：4 大师并行分析

对 $ARGUMENTS 基金进行**4 角色并行**深度分析。模仿 `investment-team.md` 框架但适配基金。

**关键差异 (vs 股票版)**：
- 段永平视角：股票看"商业模式" → 基金看"**产品定位 + 规模效应 + 品牌**"
- 巴菲特视角：股票看"财务" → 基金看"**费率 + 长期回报 + 夏普比率**"
- 芒格视角：股票看"行业格局" → 基金看"**赛道景气度 + 政策风险 + 同类对比**"
- 李录视角：股票看"管理层" → 基金看"**经理任职 + 团队稳定 + 投研体系**"

**与 `fund-debate` 的区别**：
- `fund-debate`：3 视角（看多/看空/中立），**顺序**执行，单一结论
- `fund-investment-team`：4 视角（4 大师），**并行**（需要 TeamCreate），各自独立报告，team-lead 综合

## 输入

- 基金代码（6 位）或名称
- 可选: `--asof YYYY-MM-DD` (回测某天的决策)

## 4 角色分工

### 角色 1: 段永平视角 — 产品/规模/品牌分析师

**核心问题**:
- 基金的产品定位是否清晰？（指数/主动/QDII/行业主题）
- 规模是否在"甜蜜区"？(< 1 亿 清盘风险 / > 100 亿 灵活性差)
- 基金公司品牌如何？（头部/腰部/小型）
- 同类产品中是否有差异化？

**必读数据**:
- `fund_profile_<code>.json` (规模/类型/管理人/成立日)
- `data/fund_cache/fund_holdings_<code>.json` (前 10 大持仓集中度)
- `fund_scorer.py --code` 的 quality/momentum 维度

**输出** (写到 `reports/team/dyp-<date>.md`):
```markdown
## 段永平视角分析

### 产品定位
- 类型: {类型}
- 跟踪标的: {...}
- 目标客户: {...}

### 规模甜蜜区
- 当前规模: {X} 亿
- 评估: [过小/甜蜜区/过大]
- 建议: ...

### 同类对比
- 同类 TOP3: ...
- 差异化: ...
```

### 角色 2: 巴菲特视角 — 费率/回报/估值分析师

**核心问题**:
- 总费率（管理费+托管费+销售服务费）多少？是否在甜蜜区？
- 申购费/赎回费结构？T+N 后的真实成本？
- 长期回报（1/3/5 年）排名百分位？
- 夏普比率？最大回撤？回撤恢复时间？
- 业绩比较基准跑赢多少？

**必读数据**:
- `trade_rules_<code>.json` (申购/赎回/管理费率)
- `fund_charts.json` (历史净值)
- `fund_scorer.py --code` 的 cost / quality 维度
- 同类平均费率（从排行榜 cache 拿）

**输出** (写到 `reports/team/buffett-<date>.md`):
```markdown
## 巴菲特视角分析

### 费率结构
| 项目 | 数值 | 行业平均 | 评价 |
|------|------|---------|------|
| 申购费 | X% | 1.0% | ✅ 低于平均 |
| 管理费 | X% | 1.2% | ✅ |
| 托管费 | X% | 0.2% | ✅ |
| 销售服务费 | X% | 0.4% | ✅ |
| **总费率** | **X%** | **2.8%** | **✅** |

### 长期回报
- 1 年: +X% (排名 TOP X%)
- 3 年: +X% (年化 X%, TOP X%)
- 5 年: +X% (年化 X%, TOP X%)

### 风险调整回报
- 夏普: X
- 最大回撤: -X%
- 回撤恢复: X 天
```

### 角色 3: 芒格视角 — 赛道/政策/同类对比分析师

**核心问题**:
- 基金跟踪的赛道/行业当前景气度？
- 政策风险？（教育/互联网/医药/半导体 等历史教训）
- 同类基金中此基金的"非共识"优势？
- 持有人结构（机构占比/散户占比）的暗示？

**必读数据**:
- `holdings_<code>.json` (前 10 大持仓 → 行业归属)
- `data/industry_valuation.json` (行业 PE 百分位)
- `data/fund_cache/daily_news/{asof}.json` (近期政策/行业新闻)
- 政策风险关键词清单 (教育/反垄断/集采/出口管制)

**输出** (写到 `reports/team/munger-<date>.md`):
```markdown
## 芒格视角分析

### 赛道景气度
- 行业 TOP3: 半导体 (X%) / 消费电子 (X%) / 计算机 (X%)
- 整体 PE 百分位: X%
- 行业政策: ✅/⚠️/🔴

### 政策风险扫描
- {关键词1}: ✅ 无近期政策
- {关键词2}: ⚠️ 关注中

### 同类对比非共识点
- 此基金与同类最大差异: ...
- 是否优势: ...
```

### 角色 4: 李录视角 — 经理/团队/投研体系分析师

**核心问题**:
- 基金经理任职年限？管理过几只产品？
- 经理历史业绩 vs 任职以来市场基准？
- 投研团队人数？稳定性？
- 经理是否同时管多只？（精力分散风险）
- 公司治理（股东/激励机制）？

**必读数据**:
- `fund_manager_<code>.json` (任职/业绩/履历)
- `data/fund_cache/fund_profile_<code>.json` (管理人/团队)
- 经理名下其他产品（看是否有"挂名"嫌疑）

**输出** (写到 `reports/team/liulu-<date>.md`):
```markdown
## 李录视角分析

### 经理稳定性
| 指标 | 数值 | 评价 |
|------|------|------|
| 任职年限 | X 年 | ✅ > 3 年 |
| 任职回报 | 年化 X% | ✅ 跑赢基准 |
| 管理产品数 | X 只 | ⚠️ 过多 (精力分散) |

### 团队
- 投研团队: X 人
- 平均从业: X 年
- 团队稳定性: 1 年内离开 X 人

### 治理
- 基金公司: {公司名}
- 股东背景: {...}
- 激励机制: ✅/⚠️
```

## Team Lead 综合 (汇总到 `reports/team/decision-<date>.md`)

### 综合评分卡

| 维度 | 段永平 | 巴菲特 | 芒格 | 李录 | 加权 |
|------|--------|--------|------|------|------|
| 产品/规模 | X/5 | - | - | - | X/5 |
| 费率/回报 | - | X/5 | - | - | X/5 |
| 赛道/政策 | - | - | X/5 | - | X/5 |
| 经理/团队 | - | - | - | X/5 | X/5 |
| **总分** | | | | | **X/5** |

### 买入/不买的"镜子测试"

> "5 句话说不完整为什么不该买 = 不买, 没有例外"

1. ... (5 句话理由)

### 最终建议

- **操作**: 买入 / 观望 / 减仓 / 止损
- **建议仓位**: X% (在组合内)
- **触发条件**:
  - 买入: 评分 ≥ 4.0, 4 关全过
  - 减仓: 任一维度 < 2.0
  - 止损: 经理离职 OR 政策黑天鹅

### 数据时点
- 行情: {asof} 收盘
- 新闻: {asof} 前 7 天
- 大佬交易: {asof} 前 30 天

## 降级模式

- 没有 Claude Code Team 工具？用 `fund-debate` 替代（3 视角顺序执行）
- 没有 `daily_news/{date}.json`？用 `data/fund_cache/daily_news_main.json` 但**显式标注"新闻时点不明, 可能有未来函数"**

## 与现有 SKILL 的关系

| SKILL | 关系 |
|-------|------|
| `fund-checklist` | 本 SKILL 的 4 角色包含了 checklist 的 6 关, 但更深入 |
| `fund-debate` | 顺序 vs 并行, 3 vs 4 视角 |
| `fund-sell` | 本 SKILL 输出"买卖建议", 但 `fund-sell` 专门做卖出决策 |
| `fund-monitor` | 李录视角会参考 monitor 的大佬信号 |

## 注意事项

- 4 角色**必须独立分析**（不能互相看对方的报告, 避免锚定偏误）
- Team Lead 综合时**显式标注**"X 维度的论据来自 Y 角色"
- 数据陈旧 > 7 天必须 ⚠️ 警告
- **严格反未来函数**: 决策时只用 <= asof 的数据
