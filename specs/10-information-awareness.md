# Spec 10: 最新信息感知

## 目标
自动监测基金相关的最新信息，不依赖用户通知。

## 10a: 基金公告监测

| 事件类型 | 数据来源 | 触发动作 |
|---------|---------|---------|
| 基金经理变更 | 天天基金/京东API | 重置 Manager 维度分数 |
| 基金分红 | 天天基金 | 调整回测 NAV 数据 |
| 大额赎回/暂停申购 | 基金公告 | 标记"关注" |
| 清盘预警 | 基金公告 | 自动建议卖出 |
| 基金转型 | 基金公告 | 重新 Profile |

```python
class FundEventMonitor:
    def check_manager_change(self, fund_code: str) -> bool:
        """对比缓存中的经理信息，发现变更→EventBus.emit"""
    def check_dividend(self, fund_code: str) -> Optional[dict]:
        """发现分红→调整回测数据"""
```

## 10b: 宏观因子

| 指标 | 数据来源 | 影响 |
|------|---------|------|
| 利率(MLF/LPR) | 央行 | 利率↑→债券型Quality↓ |
| PMI | 统计局 | PMI<50→降低偏股仓位上限 |
| 社融 | 央行 | 社融持续↓→市场情绪偏弱 |
| CPI/PPI | 统计局 | CPI>3%→偏防御配置 |

```python
class MacroFactorMonitor:
    def get_interest_rate(self) -> float
    def get_pmi(self) -> float
    def adjust_portfolio_limit(self, fund_type: str) -> float
        """根据宏观因子调整不同类型基金的仓位上限"""
```

## 10c: 自动通知

```python
# EventBus 联动
@EventBus.on('risk_alert')
def on_risk_alert(sender, **kwargs):
    feishu_push.send_alert(kwargs['message'])

@EventBus.on('manager_change')
def on_manager_change(sender, **kwargs):
    # 触发DecisionEngine重新评分
    decision_engine.evaluate(kwargs['fund_code'])
```

## 参考项目可复用模式
| 来源 | 模式 | 复用方式 |
|------|------|---------|
| quantdinger | Circuit Breaker | API连续失败3次→冷却5分钟→半开试探 |
| quantdinger | 指数退避重试 | API调用保护 |
| AI-Trader-main | Worker 后台任务 | 定时抓取基金公告的后台循环 |
| AI-Trader-main | Cache 降级 | Redis 挂了不阻塞业务流程 |