# Spec 90: 参考项目可复用模式总表

汇总 tradingagents / daily-stock-analysis / quantdinger / AI-Trader-main 四个项目中可用于场外基金投资系统的模式。

## tradingagents（1401节点）

### 可直接复用的 Python 模块

| 模式 | 文件 | 复用方式 |
|------|------|---------|
| 结构化输出调用链 | `agents/utils/structured.py` | bind_structured + invoke_structured_or_freetext 跨Provider降级机制 |
| 信号提取 | `agents/utils/rating.py` | parse_rating() 两遍策略（标签+关键词回退） |
| 检查点系统 | `graph/checkpointer.py` | SqliteSaver 持久化+断点续跑 |
| Vendor 路由 | `dataflows/interface.py` | route_to_vendor 多数据源故障转移 |
| TradingMemoryLog | `agents/utils/memory.py` | 追加写/原子更新/容量控制/延迟闭环 |
| 报告树生成 | `reporting.py` | 结构化 Markdown 文件树 |
| AgentState 黑板模式 | `agents/utils/agent_states.py` | 所有 Agent 共享上下文的 state 设计 |
| 分析师执行计划 | `analyst_execution.py` | AnalystNodeSpec 动态生成执行计划 |

### 需适配的架构模式

| 模式 | 文件 | 适配方式 |
|------|------|---------|
| 辩论状态管理 | `agents/utils/agent_states.py` | InvestDebateState → FundDebateState |
| Agent 类型体系 | `agents/analysts/*` | 4个分析师改为基金维度（业绩/持仓/经理/市场） |
| 风险管理辩论 | `agents/risk_mgmt/*` | 激进/保守/中立辩论→基金配置风险 |
| LangGraph 工作流 | `graph/setup.py` | 图结构完全一致，替换节点 Prompt 和 Schema |
| 结构化 Schema | `agents/schemas.py` | PortfolioRating→FundRating |

## daily-stock-analysis（16849节点）

### 可直接复用的 Python 模块

| 模式 | 文件 | 复用方式 |
|------|------|---------|
| DecisionSignalService 信号管理 | `src/services/decision_signal_service.py` | 状态机（active→expired/invalidated/archived）、对冲失效、TTL过期 |
| PortfolioRiskService 风控 | `src/services/portfolio_risk_service.py` | 5维风险模型（集中度/回撤/止损/行业/信号） |
| BaseFetcher 数据抽象 | `data_provider/base.py` | _fetch_raw_data→_normalize_data→_calculate_indicators 模板方法 |
| GenerationBackend | `src/services/generation_backend.py` | LLM 调用协议封装+结构化输出+流式支持 |

### 需适配的架构模式

| 模式 | 文件 | 适配方式 |
|------|------|---------|
| Pipeline 双架构 | `src/services/pipeline*.py` | 传统流水线→基金净值处理；多Agent→基金分析 |
| 信号提取器 | `decision_signal_extractor.py` | 从分析报告提取决策信号→从评分结果提取投资建议 |
| 分析报告工作流 | `src/analyzer/*` | 股票分析改为基金分析 |
| LLM 集成层 | `src/llm/*` | （注意：你的系统用Skill替代API调用） |
| 18个数据源适配器 | `data_provider/*_fetcher.py` | 替换股票数据源为基金数据源 |

## quantdinger（7860节点）

### 可直接复用的 Python 模块

| 模式 | 文件 | 复用方式 |
|------|------|---------|
| safe_exec 安全沙箱 | `utils/safe_exec.py` | 三层防御（regex→AST→运行时），完整 COPY |
| 熔断器 | `data_sources/circuit_breaker.py` | CLOSED→OPEN→HALF_OPEN 状态机 |
| 指数退避重试 | `data_sources/rate_limiter.py` | User-Agent 轮换 + 退避策略 |
| 日志降噪 | `data_sources/factory.py` | _log_limited 相同错误60s内只打一次 |
| 费率归一化 | `utils/risk_guard.py` | coerce_fee_rate 自动识别 0.1 与 0.001 两种格式 |
| 配置加载 | `utils/config_loader.py` | 三层 env 加载+类型安全转换+缓存 |
| 模式映射 | `services/trading_execution_modes.py` | normalize_trading_execution_modes 严格/激进切换 |
| Kline 轮询调度 | `services/trading_execution_modes.py` | next_kline_boundary_poll_ts 精确计算下次轮询时间 |

### 需适配的架构模式

| 模式 | 文件 | 适配方式 |
|------|------|---------|
| DataSourceFactory | `data_sources/factory.py` | get_kline→get_nav_series |
| StrategyCompiler | `services/strategy_compiler.py` | K线指标→基金指标，核心循环→定投调度器 |
| GridEngine | `services/grid/engine.py` | 限价单网格→净值区间定投/止盈 |
| Backtest 持久化 | `services/backtest.py` | 三表结构（runs/trades/equity_points）→基金版本 |
| ScriptPosition | `strategy_script_runtime.py` | 对冲式仓位管理→多基金组合管理 |
| 网格配置清洗 | `services/grid/config.py` | GridBotConfig.from_trading_config → 定投策略配置 |

## AI-Trader-main（156节点）

### 可直接复用的 Python 模块

| 模式 | 文件 | 复用方式 |
|------|------|---------|
| 投资组合回放引擎 | `service/server/challenge_scoring.py` | score_agent_trades 顺序回放+权益曲线（buy/sell→申购/赎回） |
| 稳定分桶算法 | `service/server/experiments.py` | SHA256 确定性分桶用于 A/B 测试 |
| Worker 注册表 | `service/server/worker.py` | BACKGROUND_TASK_REGISTRY 按 env 控制启动 |
| Worker 单例锁 | `service/server/worker.py` | Redis锁+文件锁双防止重复启动 |
| 数据库双后端适配 | `service/server/database.py` | SQLite/PG 自动占位符转换+事务管理 |
| Redis 降级 | `service/server/cache.py` | get_redis_client 不可用时返回 None 静默跳过 |
| 分布式锁 | `service/server/cache.py` | acquire_lock Redis 锁自动超时释放 |
| 发布订阅 | `service/server/cache.py` | publish + create_pubsub |
| 多维度加权评分 | `service/server/signal_quality.py` | 加权求和 + _clamp_score 归一化 |
| 配置分类 | `service/server/config.py` | 按 Database/Cache/API Keys/Market 分组+dotenv |

### 需适配的架构模式

| 模式 | 文件 | 适配方式 |
|------|------|---------|
| 路由注册 | `service/server/routes*.py` | 子路由拆分模式复用，鉴权替换 |
| 实验生命周期 | `service/server/experiments.py` | create→assign→refresh→update 替换策略实验 |
| 定价异常检测 | `service/server/scripts/*.py` | repair_challenge_trade_prices 等数据修复脚本思路 |
| 服务层事务 | `service/server/services.py` | cursor 事务边界控制模式复用 |

## 各 Spec 的模式引用索引

| Spec | 主要参考项目 | 核心模式 |
|------|------------|---------|
| 01 数据层 | daily-stock-analysis(数据抽象) + quantdinger(工厂+熔断器) + AI-Trader(缓存) | BaseFetcher / DataSourceFactory / Circuit Breaker / Redis降级 |
| 02 Pipeline | daily-stock-analysis(双重编排) + AI-Trader(Worker) | Pipeline 双架构 / 任务注册表 / 单例锁 |
| 03 LLM层 | tradingagents(辩论+结构化+记忆) + daily-stock-analysis(GenerationBackend) | 辩论模式 / structured.py / TradingMemoryLog |
| 04 决策引擎 | daily-stock-analysis(信号管理) + tradingagents(AgentState) + AI-Trader(评分) | DecisionSignalService / 信号生命周期 / 评分框架 |
| 05 EventBus | quantdinger(熔断器检测) + AI-Trader(PubSub) | blinker |
| 06 RAG+Memory | tradingagents(TradingMemoryLog) | 追加写/闭环/容量控制 |
| 07 回测 | quantdinger(回测引擎) + AI-Trader(回放引擎) | 持久化三表 / 预热机制 / 风险调整评分 |
| 08 进化 | quantdinger(策略编译) + AI-Trader(实验管理) | StrategyCompiler / 稳定分桶 |
| 09 扫描 | quantdinger(数据源工厂) + daily-stock-analysis(数据适配器) | 多数据源故障转移 |
| 10 信息感知 | quantdinger(熔断器) + AI-Trader(Worker) | 冷却/重试 / 后台任务 |
| 11 归因 | AI-Trader(评分) + daily-stock-analysis(分析器) | 多维度加权 / 分析报告流程 |
| 12 Skills | tradingagents(Agent体系) | 多Agent辩论+报告树