# Spec 04: Decision Engine

## 目标
建立"AI建议→规则校验→评分验证→Risk Check→Backtest→最终决策"的五步决策管线。

## 流程

```
AI建议(文本，仅供参考)
    │
    ▼
Step 1: Rules Engine (fund_rules.py)
  - weighted_clear() → 硬性清仓? 强制输出
  - buy_shield() → 买入护盾激活? 跳过卖出
  - swap_cost() → 调仓成本 > 超额收益30%? 不调仓
    │
    ▼
Step 2: Scoring Engine (fund_scorer.py)
  - 5维评分: total >= 4.0 优秀 / >= 3.3 及格 / < 3.0 回避
  - 各维度分供AI解释用
    │
    ▼
Step 3: AI Interpretation (FundAnalyzer)
  - LLM 解释评分结果(只解释不决策)
  - 记录AI建议与程序评分的分歧
    │
    ▼
Step 4: Risk Check
  - 单只仓位 > MAX_SINGLE_PCT(15%)?
  - QDII总仓位 > MAX_QDII_PCT(30%)?
  - 该基金当前可操作?(非节假日/15:00前)
  - 持有期 < 7天? 禁止卖出
    │
    ▼
Step 5: Backtest Validate (Phase7完成前跳过)
  - 回测该策略过去3年表现
  - 年化 < 基准? 拒绝
  - 最大回撤 > 阈值? 拒绝
    │
    ▼
最终输出: {action, fund_code, amount, reason, backtest_result}
```

## DecisionEngine 接口

```python
class DecisionResult:
    action: str          # buy/hold/reduce/sell/switch
    fund_code: str
    amount: float        # 0表示不操作
    priority: str        # 强制/建议/参考
    reason: str
    steps: List[dict]    # 五步每步的结果日志
    backtest: dict = None  # 回测结果(可选)
    ai_suggestion: str = None  # AI原始建议

class DecisionEngine:
    def evaluate(self, fund_code: str, cash: float,
                 ai_suggestion: str = None) -> DecisionResult:
        """五步决策，返回最终结果"""

    def evaluate_portfolio(self, holdings: List[dict], cash: float) -> List[DecisionResult]:
        """全组合评估，按优先级排序"""

    def _validate_suggestion(self, ai_suggestion: str, score: FundScore):
        """记录AI建议与程序评分的分歧，只记录不阻止"""

## 参考项目可复用模式
| 来源 | 模式 | 复用方式 |
|------|------|---------|
| daily-stock-analysis | DecisionSignalService | 状态机(active→expired/invalidated/closed)、对冲失效、TTL过期 |
| daily-stock-analysis | PortfolioRiskService | 5维风险模型(集中度/回撤/止损/行业/信号) |
| tradingagents | parse_rating | 两遍策略：标签查找+关键词回退 |
| AI-Trader-main | 风险调整评分 | final_score = return - max(0, drawdown - allowed)*penalty |
```