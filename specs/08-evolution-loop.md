# Spec 08: 策略自动进化循环

## 目标
系统自动发现+验证+优化策略，不需要人工设计策略参数。

## 8a: 策略基因定义

```python
@dataclass
class StrategyGene:
    # 5维评分权重
    quality_weight: float      # 默认0.25
    cost_weight: float         # 默认0.20
    manager_weight: float      # 默认0.20
    momentum_weight: float     # 默认0.15
    smart_money_weight: float  # 默认0.20
    # 交易参数
    buy_threshold: float       # 默认4.0
    sell_threshold: float      # 默认3.0
    max_single_pct: float      # 默认0.15
    cooling_days: int          # 默认7
    cash_reserve_pct: float    # 默认0.20
```

## 8b: 锦标赛流程

```
1. 初始化: 50组随机基因 + 3组专家预设(保守/平衡/进取)
2. 每轮: 每组基因跑完整历史回测
3. 排序: 按夏普比率(60%) + 年化收益(20%) + 最大回撤(20%) 综合排名
4. 晋级: 前20% (约10组) 进入下一代
5. 变异: 晋级者随机扰动 ±10% 参数 → 生成10组
6. 杂交: 晋级者两两交叉取均值 → 生成10组
7. 补充: 新生成10组随机基因(保持多样性)
8. 重复: 跑5-10代直到收敛(前3名稳定)
```

## 8c: AI 知识提炼

```python
class EvolutionLoop:
    def run_generation(self, genes: List[StrategyGene]) -> List[StrategyGene]:
        """跑一轮锦标赛"""

    def analyze_winners(self, winners: List[StrategyGene]) -> str:
        """AI分析胜出基因特征:
           "为什么高quality_weight+低momentum_weight的策略胜出?"
           分析结果→写insight到RAG→下次决策参考"""

    def generate_evolution_report(self) -> str:
        """每月输出进化报告: 策略变化+收益提升+关键insight"""

    def inject_insight(self, decision_engine: DecisionEngine) -> None:
        """最优基因注入Decision Engine
           (仅注入参数，不跳过规则校验)"""
```

## 参考项目可复用模式
| 来源 | 模式 | 复用方式 |
|------|------|---------|
| quantdinger | StrategyCompiler | JSON配置→Python代码编译，基金策略配置同理 |
| AI-Trader-main | 稳定分桶算法 | SHA256确定性分桶，A/B测试基金策略 |
| AI-Trader-main | 实验生命周期 | create→assign→refresh→update实验管理 |
| AI-Trader-main | 实验变体机制 | DEFAULT_VARIANTS 权重比例分配到 variant |