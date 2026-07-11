---
name: codebuddy-fund-research
user-invocable: true
description: "CodeBuddy 专属: 一句话调全套基金 SKILL 并输出投资建议 (基金版 fund-investment-team)"
---


## 触发短语 (triggers)

以下自然语言/命令会自动触发本 SKILL:

- `codebuddy 基金研究`
- `codebuddy 投研`
- `codebuddy-fund-research`


## 必读数据 (先读这)

| 文件 | 用途 |
|------|------|
| `docs/AI_META_PROMPT.md` | Meta prompt 模板 |
| `docs/AI_DATA_GUIDE.md` | 数据地图 |
| `docs/AI_ACTIVE_AUDIT_GUIDE.md` | 主动调 SKILL 指南 |
| `docs/AI_AUDIT_PROMPT.md` | system prompt 模板 |
| `skills/fund-investment-team.md` | 4 大师基金版 (主流程) |


# CodeBuddy 基金投研: 一句话调全套 SKILL

> **专为本项目 CodeBuddy IDE 设计**。
> 用户输入: "CodeBuddy 投研 013841" 或 "codebuddy 研究 银华集成电路"
> AI 自动按 fund-investment-team 的 4 角色流程跑, 输出结构化建议.

## 与 Claude Code 版的差异

| 项 | Claude Code | CodeBuddy (本 SKILL) |
|---|---|---|
| 客户端 | `@anthropic-ai/claude-code` | CodeBuddy IDE (当前环境) |
| Team 工具 | ✅ `TeamCreate` | ❌ 无 (本 IDE 不支持) |
| 执行方式 | 4 角色并行 | **4 角色顺序** (模拟并行) |
| 输出位置 | 各自 .md | 合并到一份 `codebuddy-decision-<date>.md` |

## 工作流

### 步骤 1: 解析输入

用户输入示例:
- `codebuddy 投研 013841`
- `codebuddy 研究 银华集成电路`
- `codebuddy-fund-research 013841 --asof 2026-05-22`

提取:
- 基金代码 (6 位) 或 名称
- asof_date (默认今天)

### 步骤 2: 数据准备 (顺序读, 不 spawn python)

```python
# 读档案
profile = read_json(f"data/fund_cache/fund_profile_{code}.json")
manager = read_json(f"data/fund_cache/fund_manager_{code}.json")
rules = read_json(f"data/fund_cache/trade_rules_{code}.json")
holdings = read_json(f"data/fund_cache/fund_holdings_{code}.json")

# 读行情 (用 fund_charts.json)
charts = read_json("backtest/data/fund_charts.json").get(code, [])

# 截至 asof 的大佬交易
hist = read_json("backtest/data/trading_history_fixed.json")
recent = [r for r in hist if r.get("fund_code") == code and r.get("date", "") <= asof]

# 截至 asof 的新闻
news_files = glob(f"data/fund_cache/daily_news/*.json")
news = []
for f in sorted(news_files):
    if f.stem <= asof:
        d = read_json(f)
        news.extend(d.get("items", []))
```

### 步骤 3: 4 角色顺序分析

#### 角色 1: 段永平视角
模板见 `skills/fund-investment-team.md` "角色 1" 节.

#### 角色 2: 巴菲特视角
模板见同 SKILL "角色 2" 节.

#### 角色 3: 芒格视角
模板见同 SKILL "角色 3" 节.

#### 角色 4: 李录视角
模板见同 SKILL "角色 4" 节.

### 步骤 4: Team Lead 综合

汇总 4 角色结论到 `reports/codebuddy-decisions/<asof>-<code>.md`, 包含:
- 综合评分卡
- 镜子测试 5 句话
- 最终建议 (买/卖/持有 + 仓位)
- 数据时点
- 不确定性

### 步骤 5: 跑 daily_live (可选)

如果用户问"今天该买什么", 调:
```bash
py -3.10 scripts/daily_live.py
```

读生成的 `reports/sim/<date>.md` + `.json`, 跑 4 角色分析.

## 反未来函数

CodeBuddy 会话默认 asof=today. 如果用户**明确指定** asof, 必须:
- 只读 `<=asof` 的快照
- 读 `daily_news/{asof}.json` 或更早
- 不读 `trading_history_fixed.json` 中 `>asof` 的记录
- 不读 `fund_charts.json` 中 `>asof` 的点

## 一句话示例 (CodeBuddy 会话输入)

```
"CodeBuddy 投研 013841"
→ 自动: profile + manager + rules + holdings + charts + 大佬 + 新闻
→ 输出: reports/codebuddy-decisions/2026-07-11-013841.md (含 4 视角 + 综合)

"CodeBuddy 投研 013841 asof 2026-05-22"
→ 自动: 同上, 但只用 5-22 前数据
→ 输出: reports/codebuddy-decisions/2026-05-22-013841.md (反未来函数版)

"CodeBuddy 今天该买啥"
→ 自动: 跑 daily_live.py → 读 sim 日报 → 对每只买入推荐跑 4 角色
→ 输出: reports/codebuddy-decisions/2026-07-11-recommendations.md
```

## 输出模板

```markdown
# CodeBuddy 基金投研: {基金名} ({code}) — {asof}

> 数据截至 {asof} | 反未来函数 ✅

## 综合结论
- **建议**: 买入 / 持有 / 减仓 / 止损
- **置信度**: X.X / 1.0
- **目标仓位**: X% (组合内)
- **镜子测试**: 5 句话说完为什么不买 (见末尾)

## 4 角色评分卡

| 维度 | 评分 | 关键发现 |
|------|------|----------|
| 段永平: 产品/规模 | X/5 | ... |
| 巴菲特: 费率/回报 | X/5 | ... |
| 芒格: 赛道/政策 | X/5 | ... |
| 李录: 经理/团队 | X/5 | ... |
| **综合** | **X/5** | ... |

## 段永平视角
[~150 字]

## 巴菲特视角
[~150 字]

## 芒格视角
[~150 字]

## 李录视角
[~150 字]

## 镜子测试 (5 句话)
1. ...
2. ...
3. ...
4. ...
5. ...

## 触发条件
- 买入: 评分 ≥ 4.0
- 减仓: 任一维度 < 2.0
- 止损: 经理离职 / 政策黑天鹅

## 数据时点
- 行情: {asof} 收盘
- 持仓快照: {asof}
- 新闻: {asof} 前 7 天 ({N} 条)
- 大佬交易: {asof} 前 30 天 ({N} 笔)
```

## 与 fund-investment-team.md 的关系

**本 SKILL = CodeBuddy 适配层**, 内核调用 `fund-investment-team.md` 的 4 角色框架.
- 如果用户用 Claude Code, 直接用 `fund-investment-team.md` (支持 TeamCreate 并行)
- 如果用户用 CodeBuddy, 用本 SKILL (顺序执行, 合并到一份报告)
- 两者**结论应该一致** (因为用相同 4 视角)

## 故障排查

| 问题 | 解决 |
|------|------|
| 找不到基金档案 | `python tools/jd_finance_api.py --fund-profile {code}` 拉取 |
| 新闻时点不明 | 检查 `data/fund_cache/daily_news/` 是否有对应日期快照 |
| 行情数据不全 | 查 `data/fund_charts.json` 是否包含此 code |
| 大佬数据陈旧 | 跑 `scripts/auto-pipeline.py` 重新抓取 |
