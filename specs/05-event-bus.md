# Spec 05: Event Bus

基于 blinker 轻量级事件库（不自写），实现模块间解耦。

```bash
pip install blinker
```

## 事件定义

| 事件 | 触发时机 | 监听方 |
|------|---------|--------|
| nav_updated | 基金净值更新 | Risk模块(检查) / Analyzer(解释) / Memory(存储) |
| holdings_updated | 大佬持仓更新 | Scoring(重新评分) / Rules(重算信号) |
| signal_created | 新决策信号 | Feishu(推送) / Pipeline(触发后续task) |
| risk_alert | 风控预警 | Decision Engine(重新评估) / Feishu(紧急通知) |
| quarterly_report | 季报发布 | RAG(索引) / Analyzer(解读) |

## 使用方式

```python
from blinker import signal

nav_updated = signal('nav_updated')
holdings_updated = signal('holdings_updated')

# 注册监听器
@nav_updated.connect
def on_nav_updated(sender, **kwargs):
    fund_code = kwargs.get('fund_code')
    nav = kwargs.get('nav')
    # ...

# 发布事件
nav_updated.send(self, fund_code="006105", nav=1.234)
```

## 参考项目可复用模式
| 来源 | 模式 | 复用方式 |
|------|------|---------|
| AI-Trader-main | Redis PubSub | publish + create_pubsub 进程间通信 |
| quantdinger | Circuit Breaker 事件 | OPEN→HALF_OPEN 状态变更可发布为事件 |
| tradingagents | Analyst 执行跟踪 | AnalystWallTimeTracker 执行时间事件 |