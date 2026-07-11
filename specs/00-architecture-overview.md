# Spec 00: 整体架构（IDE 原生版）

## 架构变化

去掉"LLM 客户端 API 调用层"，全部改为 Claude Code Skill。

```
之前(API模式):
  Layer 5: AI 解释层 → tools/llm/ + DeepSeek/OpenAI API

现在(IDE模式):
  Layer 5: AI 解释层 → skills/ (Claude Code 原生 Skill)
  Layer 3: 评分+规则 → 输出 JSON 供 Skill 读取
```

## 6 层架构（IDE 原生版）

```
┌──────────────────────────────────────────────────────────────┐
│    Layer 6: Skills 交互层 (Claude Code 原生 LLM)              │
│  skills/fund-analyze → fund-debate → fund-compare            │
│  skills/fund-checklist → fund-sell → fund-trade              │
│  skills/news-pulse → investment-research → earnings-review   │
│  所有 LLM 推理通过 Skill 在 Claude Code IDE 中运行            │
│  不调用外部 API，不消耗额外 token 费用                          │
├──────────────────────────────────────────────────────────────┤
│    Layer 5: Pipeline 编排层 (Python)                         │
│  scripts/pipeline/engine.py + 10个task                       │
│  生成结构化数据 → Skill 消费                                   │
├──────────────────────────────────────────────────────────────┤
│    Layer 4: 决策引擎 + 风控 (Python)                         │
│  tools/decision_engine.py                                    │
│  5步：Rules→Scoring→Risk Check→Backtest→决策                 │
├──────────────────────────────────────────────────────────────┤
│    Layer 3: 评分 + 规则 + 信号 (Python)                      │
│  fund_scorer.py(5维程序评分) → 输出 JSON                     │
│  fund_rules.py(规则引擎) → 输出 JSON                         │
│  数据供 Layer 6 Skill 读取解释                                 │
├──────────────────────────────────────────────────────────────┤
│    Layer 2: 数据层 + RAG (Python)                            │
│  tools/data_provider/ (标准化接口+多数据源)                   │
│  tools/rag/ (chromadb向量库)                                  │
│  tools/memory/ (FundMemoryLog分析历史)                        │
├──────────────────────────────────────────────────────────────┤
│    Layer 1: 基础设施 (Python)                                │
│  jd_finance_api.py / backtest/engine/                        │
│  EventBus(blinker) / Worker(后台任务)                        │
└──────────────────────────────────────────────────────────────┘
```

## 数据流（IDE 原生模式）

```
jd_finance_api → IFundDataProvider → 标准化models
    → Pipeline(tasks依次执行)
        → fund_scorer 计算5维评分 → 输出JSON
        → fund_rules 规则引擎 → 输出JSON
        → DecisionEngine 5步决策
        → 结果存入 FundMemoryLog
        → 用户运行 /fund-analyze 查看AI解释（IDE内）
        → 用户运行 /fund-debate 查看辩论（IDE内）
```

## 从参考项目复用的内容（不复制代码，只取设计思路）

| 项目 | 复用内容 | 实现方式 |
|------|---------|---------|
| tradingagents | Agent辩论模式 | 改为fund-debate skill |
| tradingagents | 结构化输出设计 | 改为fund_scorer的JSON输出 |
| daily-stock-analysis | 信号生命周期管理 | 增强fund_rules |
| daily-stock-analysis | 组合风控模型 | 参考实现Python版本 |
| quantdinger | 策略编译思路 | 改为策略基因定义 |
| AI-Trader-main | Worker后台任务 | 直接参考Python实现 |
| ai-berkshire自有skills | 25个投研Skill | 已有，新增3个辅助skill |