# Goal: 场外基金智能投资系统

构建一个"数据采集→指标计算→规则评分→AI解释→决策引擎→回测验证→自动进化"的场外基金智能投资系统。

**读取指引：** 本目录下 `GOAL.md` 定义目标，`specs/` 目录是各模块详细设计文档。每完成一个 spec 再读下一个，按编号顺序推进。

## 核心原则
- AI只做文本解释和辩论，不做计算和决策
- 所有评分/风控/仓位由程序计算
- 策略必须先通过回测验证
- 回测严格防作弊

## 已有代码（不要重复造）
- tools/jd_finance_api.py(75K) / fund_scorer.py(39K) / fund_rules.py(10K) / fund_planner.py(6K) / backtest/engine/backtest.py(9K) / scripts/auto-pipeline.py(107K)
- skills/ 有25个投研Skill（投资研究/财报分析/基金分析/新闻监测等）
- skills/ 25个投研Skill（invest-team/fund-checklist/news-pulse等）

## 参考项目（见 specs/90-reference-patterns.md 完整清单）
- tradingagents: Agent辩论+记忆+结构化输出+检查点+Vendor路由
- daily-stock-analysis: 信号生命周期+组合风控+数据抽象+双重Pipeline
- quantdinger: 安全沙箱+熔断器+策略编译+网格引擎
- AI-Trader-main: 回放引擎+挑战评分+Worker+Redis降级+实验管理

## 编码规则
1. 先设计后编码：每个 spec 读完确认后再实现
2. 检查已有代码后再写：优先复用，不重复造
3. fund_scorer/fund_rules/fund_planner/jd_finance_api 只新增不重构
4. 类型注解完整，pytest >= 80%，AAA模式
5. 每次一个子任务，完成即测

## 防作弊回测7铁律
1. 日期截断：T 日只用 T 日前数据
2. 无未来函数
3. T+n 确认：申购 T+1，赎回 T+3~7
4. 费率全计（申购+赎回+管理+托管）
5. 日限额约束
6. 冷却期 ≥ 7 天
7. 多权重对比

## 实施顺序
P1(数据层)+P3(LLM)+P4(决策引擎) → P2(Pipeline)+P7(回测加固) → P5(EventBus)+P6(RAG+Memory) → P8(进化)+P9(全市场扫描) → P10(信息感知) → P11(归因) → P12(Skills整合)