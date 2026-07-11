# Spec 11: 绩效归因与复盘

## 目标
定期分析"为什么赚/亏了"，归因结果反哺策略进化。

## 11a: Brinson 归因

```python
class PerformanceAttribution:
    def brinson_attribution(self, portfolio: dict, benchmark: str) -> dict:
        """分解超额收益来源:
           - 配置效应: 重配某类基金带来的超额
           - 选择效应: 选对了某只基金带来的超额
           - 交互效应: 配置+选择的协同效果"""

    def style_attribution(self, holdings: List[dict]) -> dict:
        """风格暴露分析:
           大盘/小盘/价值/成长 各风格占比"""

    def sector_attribution(self, portfolio: dict) -> dict:
        """行业暴露分析(穿透到持仓股票):
           穿透持仓后的实际行业分布"""
```

## 11b: 自动复盘报告

```python
class ReviewReport:
    def weekly(self, portfolio: dict) -> str:
        """每周自动生成归因报告"""

    def monthly(self, portfolio: dict) -> str:
        """每月自动生成归因报告"""

    def generate(self, attribution: dict) -> str:
        """AI解读归因数据:
           "本月收益主要来自XX基金的XX行业配置，拖累来自..."
           结果→存入FundMemoryLog"""

    def trigger_evolution(self, attribution: dict) -> bool:
        """连续3个月某维度负贡献→降低该维度权重
           例如动量维度持续负贡献→momentum_weight -= 0.05"""
```

## 11c: 归因→进化闭环

```
归因分析 → 发现动量维度连续负贡献
  → 自动降低 momentum_weight (0.20 → 0.15)
  → 下期进化锦标赛用新权重范围
  → 下月归因检查变化效果
  → 持续优化 → 收敛到最优配置
```

## 参考项目可复用模式
| 来源 | 模式 | 复用方式 |
|------|------|---------|
| AI-Trader-main | 多维度加权评分 | signal_quality.py 加权求和+_clamp_score 归一化 |
| AI-Trader-main | 评分排名算法 | rank_scored_results 过滤+降序排列+rank |
| daily-stock-analysis | 分析报告工作流 | 自动生成分析报告格式 |
| tradingagents | 报告树生成 | 归因结果写为结构化Markdown |