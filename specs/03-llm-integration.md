# Spec 03: LLM 集成层（IDE 原生模式）

## 关键决策
**不调用外部 LLM API。** LLM 引擎就是 Claude Code 本身。所有 AI 解释/辩论/分析通过 Claude Code Skill 实现，不需要 DeepSeek/OpenAI API Key。

## 架构变化

```
之前(API模式):
  Python代码 → 调DeepSeek API → 返回文本解释

现在(IDE模式):
  Python代码 → 输出结构化数据 → 触发Claude Code Skill(如 /fund-analyze) → Claude Code读取数据做解释
```

## 新建 Skill 文件

在 `skills/` 目录新增 3 个 Skill，遵循已有 skills 的格式：

### skill: fund-analyze

```markdown
---
name: fund-analyze
description: 分析基金评分结果，输出文本解释
---
# Fund Analyze

## 输入
从 tools/fund_scorer.py 的输出读取评分数据（JSON格式）：
- tools/fund_rules.py 的 analyze_all() 输出
- fund_scorer.py 的 score_fund() 输出

## 职责
- 解释 5 维评分：为什么质量分高/低
- 指出规则引擎的结论：清仓/护盾/成本
- 不输出分数，不输出买卖建议
```

### skill: fund-debate

```markdown
---
name: fund-debate
description: 多视角基金辩论分析
---
# Fund Debate

## 输入
读取 fund_scorer 和 fund_rules 的输出数据

## 流程
1. 看多视角：强调超额收益、经理经验、行业景气度
2. 看空视角：强调回撤、风格漂移、费率过高
3. 中立视角：综合双方，给出平衡分析
```

### skill: fund-compare

```markdown
---
name: fund-compare
description: 对比多只基金的评分差异
---
# Fund Compare

## 输入
读取多只基金的评分数据

## 职责
- 对比各维度差异
- 指出各自优劣势
- 不输出排名分数
```

## Pipeline 联动

```python
# scripts/pipeline/tasks/task_ai_analysis.py
class TaskAIAnalysis(PipelineTask):
    name = "ai_analysis"

    def execute(self, context, offline=False):
        # 1. 读取评分数据
        scores = context.get('scores', {})
        rules = context.get('rules', {})

        # 2. 输出结构化数据供 Skill 读取
        output_path = DATA_DIR / "auto" / "ai_input.json"
        json.dump({"scores": scores, "rules": rules}, output_path)

        # 3. 提示用户可运行 Skill
        print(f"AI分析数据已写入 {output_path}")
        print("建议运行: /fund-analyze 查看评分解释")
        print("建议运行: /fund-debate 查看多视角分析")
```

## 参考项目模式复用（不复制代码）

从 tradingagents 复用的**不是 LLM 客户端代码**，而是：
1. **辩论模式思路**：Bull/Bear 辩论结构 → 改为 fund-debate skill
2. **结构化输出思路**：structured.py 的 Schema 设计 → 改为 fund_scorer 的 JSON 输出格式
3. **记忆思路**：TradingMemoryLog → 改为 FundMemoryLog（Python 实现，不需 LLM）

从 daily-stock-analysis 复用的：
1. **DecisionSignalService 的信号管理** → 改为 fund_rules 的增强版
2. **PortfolioRiskService 的风控** → 直接参考其 5 维风控模型

**核心原则：** 所有 Python 代码（评分/规则/风控/数据）用 Python 实现。所有 LLM 推理（解释/辩论/分析）用 Claude Code Skill 实现。不调用外部 API。