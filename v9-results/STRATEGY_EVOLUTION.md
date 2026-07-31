# AI Berkshire 策略进化记录

## 核心发现：专家信号 alpha

通过专家买入信号的 walk-forward 测试：

| 实验 | 最佳策略 | 季度收益 | 年化估算 | 8窗口平均 |
|------|----------|----------|----------|-----------|
| 初代 V8 | - | -0.37% | -1.5% | 严重过拟合 |
| EXP_MOM (min_consensus=2, SM70) | EXP_MOM_4 | +0.33% | +1.3% | 串行测试 |
| 扩大容量 (max_holdings) | EXP_MOM_8 | +0.61% | +2.4% | 7/8 窗口盈利 |
| 容量实验1 (12 slot, 过滤) | MOM_12_S0 | +0.79% | +3.2% | 7/8 盈利 |
| 容量实验2 (14-16 slot, TP调优) | 待定 | 待定 | 待定 | 进行中 |

## 关键洞察

1. **专家信号有真实 alpha**: +7天平均 +1.39%, t-stat +48
2. **7天红利是 margin killer**: 1.5% 赎回费 > 1.4% alpha
3. **max_holdings 是关键参数**: 从 4 增到 12 几乎 2x 收益
4. **min_score=0, min_consensus=2 是最佳过滤组合**
5. **单人士信号过于嘈杂**: MOM_10_C1 有 -6.5% 的灾难窗口
6. **momentum filter**: 30/70 Mo/SM 权重是必要的

## 下一步

- 完成容量实验2 (max_holdings 14-16)
- 测试 take_profit 5% vs 6% vs 8%
- 尝试完全关闭 momentum filter (Mo0/SM100)
- 测试不同市场 regime 下的表现
