# Spec 07: 回测防作弊加固

## 现有问题修复

### 1. 持仓数据全局加载未截断
**问题：** FUND_HOLDINGS_CACHE 在文件顶部全局加载一次，回测中任何日期都能访问未来持仓。
**修复：** 改为按季报公布日期过滤。给定 cutoff_date=T，只返回 publish_date ≤ T 的 holdings。

### 2. T+n 确认延迟
**问题：** T 日买入 T 日就开始算收益（作弊）。
**修复：** Portfolio.buy() 改为 T 日记录申购，T+1 确认份额，T+2 开始纳入净值计算。

### 3. 管理费/托管费验证
**问题：** 基金净值通常是费后净值（已扣管理费托管费），需要确认后再决定是否额外扣。
**修复：** 先从基金资料确认净值是否费后。若是则不再扣；若不是则按日计提。

### 4. 冷却期约束
**问题：** 没有显式限制两次操作间隔。
**修复：** 同基金两次操作间隔 < 7 天时直接拒绝（T+7 惩罚性赎回费约束）。

## 新增: 回测闭环验证

在 DecisionEngine 中加入回测步骤：

```
AI建议 → 规则引擎 → 评分验证 → 回测3年该策略
  → 年化收益 < 基准收益? 拒绝
  → 最大回撤 > 阈值(如25%)? 拒绝
  → 夏普比率 < 0.5? 警告
  → 通过 → 输出最终建议
```

## test_backtest_integrity.py

测试用例覆盖 7 条防作弊铁律：

```python
def test_date_cutoff_no_future_data():
    """验证 T 日评分只用 T 日前数据"""
def test_t_plus_1_confirm():
    """验证 T 日申购 T+1 才确认"""
def test_redemption_fee_scale():
    """验证 T<7天 赎回费1.5%"""
def test_cooling_period():
    """验证同基金7天内不可重复操作"""
def test_multi_weight_fairness():
    """验证多权重对比，不全展示最好看的结果"""
def test_daily_limit():
    """验证单只基金日申购上限约束"""

## 参考项目可复用模式
| 来源 | 模式 | 复用方式 |
|------|------|---------|
| quantdinger | Backtest 持久化 | 三表结构(runs/trades/equity_points) |
| quantdinger | 预热机制 | _estimate_warmup_bars 估算指标需要的最小历史期数 |
| quantdinger | _infer_candle_path | 推断K线内部价格路径→基金净值日内路径推断 |
| quantdinger | _signal_diagnostics | 信号诊断做调试和可视化 |
| AI-Trader-main | 投资组合回放引擎 | score_agent_trades 顺序回放+权益曲线，buy/sell→申购/赎回 |
| AI-Trader-main | 风险调整评分 | return_pct - max(0, max_drawdown - allowed_drawdown) * penalty |
```