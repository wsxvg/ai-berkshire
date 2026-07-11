# Spec 09: 全市场扫描引擎

## 目标
自动从 10000+ 公募基金中筛选候选池，替代人工选基。

## 9a: 全量列表采集

天天基金 API 获取全市场基金列表。

```python
class FundScanner:
    def fetch_all_funds(self) -> List[FundProfile]:
        """采集全市场基金列表"""
        # 过滤: 排除货币基金/ETF联接/C类份额
        # 按类型分组: 股票型/混合型/债券型/指数型/QDII

    def quick_score(self, profile: FundProfile) -> float:
        """用3个轻量维度粗筛(只调API不调fund_scorer)
           cost + 成立年限 + 规模稳定性"""

    def filter_pool(self, funds: List[FundProfile], top_pct: float = 0.3) -> List[str]:
        """粗筛后取top30%"""
```

## 9b: 候选池管理

```python
class CandidatePool:
    watch_list: List[str]       # 重点观察池(top20)
    candidates: List[str]       # 候选池(top200)
    eliminated: List[str]       # 淘汰池

    def refresh(self, scanner: FundScanner):
        """每日/每周更新"""

    def on_enter_top20(self, fund_code: str):
        """新进观察池→触发EventBus.emit('signal_created')"""

    def on_exit_top50(self, fund_code: str):
        """掉出候选池→标记关注"""

## 参考项目可复用模式
| 来源 | 模式 | 复用方式 |
|------|------|---------|
| quantdinger | DataSourceFactory | 多数据源故障转移，扫描不同数据源获取全量基金列表 |
| daily-stock-analysis | 18个数据源适配器 | 替换股票数据源为基金数据源 |
| quantdinger | 熔断器 | 扫描过程中的 API 保护 |
| quantdinger | 日志降噪 | 相同基金不在扫描期内重复打印日志 |
```