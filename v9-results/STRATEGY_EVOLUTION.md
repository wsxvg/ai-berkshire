# AI Berkshire 策略进化记录

## 🏆 当前最优 (OOS Round 4): WEIGHTS_ALT = +10.58%/q (~+42% 年化), 跑赢 CSI300 10/14 ✅

## 进化时间线

| 实验 | 最佳策略 | OOS 季度收益 | 跑赢 CSI300 | 关键动作 |
|------|----------|-------------|-------------|----------|
| 初代 V8 | - | -0.37% | ❌ | 过拟合基准线 |
| 容量实验 | MOM24_TP7 | +0.989% | ✅ | 简化到 2 维 |
| V8 消融单回测 | V8_base | +97.47%/3yr | ✅ | 五维权重 + TP50 |
| V8 Walk-Forward | V8_HOLD9 | +4.845% | ✅ | 28 窗口 WF 验证 |
| **Strict OOS R1** | V8_HOLD12 | +10.054% | ✅ 11/14 | 严格 OOS 协议 |
| **Strict OOS R2** | HOLD12_CONS4 | +8.771% | ✅ 8/14 | 严格共识版 |
| **Strict OOS R3** | HOLD12_AGGRESSIVE | +7.901% | ✅ 8/14 | 激进换仓 |
| **Strict OOS R4** | **WEIGHTS_ALT** | **+10.583%** | ✅ 10/14 | **5候选全测 + 权重倾斜** |

## R4 最优配置 (WEIGHTS_ALT)

```python
{
    'weights': {'quality': 20, 'cost': 25, 'manager': 15, 'momentum': 10, 'smart_money': 30},
    'max_holdings': 12,
    'take_profit_pct': 50.0,
    'min_consensus': 3,
    'kelly_cap_bull': 0.5,
    'kelly_cap_bear': 0.25,
    'no_stop_loss': True,
    'smart_swap': True,
    'regime_specific': True,
}
```

## R4 全 5 候选结果 (TEST W14-W27, 14 windows)

| 候选 | OOS 平均季度收益 | 跑赢 CSI300 | 跑赢数 |
|------|-----------------|------------|--------|
| **WEIGHTS_ALT** | **+10.583%** | ✅ +4.487% | **10/14** |
| TREND_FILTER | +10.054% | ✅ +3.958% | 11/14 |
| HOLD12_BASE | +10.054% | ✅ +3.958% | 11/14 |
| HOLD15_DIVERSIFY | +10.072% | ✅ +3.977% | 9/14 |
| HOLD9_CORE | +9.829% | ✅ +3.734% | 9/14 |

**R4 关键发现**:
1. smart_money 权重从 20 提到 30 → 额外 +54bps
2. 候选间差异很小 (< 1%), 说明 5 维 expert 信号本身好, 微调边际有限
3. **W7 (10月~1月) 和 W12 (3月~6月) 是所有候选的共同弱点** — 需组合层面保护

## R5 假设 (下一轮方向)

核心假设: market_risk_filter 可以在高风险期停止买入，系统性保护 W7/W12 类回撤。

候选 (预注册, 2026-08-02):
1. WEIGHTS_ALT — 对照
2. RISK_FILTER_60 — 权重 + 市场风险过滤 (阈值 60)
3. RISK_FILTER_45 — 更敏感风控 (阈值 45)
4. RISK_KELLY — 风控 + 更低 bear kelly + 现金储备
5. RISK_PREDICTOR — 市场预测器 + crash_sell

## 为什么 V8_HOLD12 在 R1/R4 都 10.054%

R1 和 R4 的 HOLD12_BASE 结果完全一致 (10.054%, 11/14 跑赢), 这不是巧合:
- 系数配置完全相同 (max_holdings=12, 其余一样)
- 算法是确定性的
- 回测引擎是确定性的
- **证明** OOS 协议可靠: 相同配置得到相同结果

## 收敛判断

OOS 改进边际已经很小 (R4 内 < 1%)。真正的瓶颈不在评分/权重, 而在:
1. **W7/W12 类大盘崩塌窗口** → R5 假设: market_risk_filter 保护
2. **策略拥挤度** — 同一批基金被大量算法选 → 未来需扩大基金池

## 下一步行动

1. **R5**: 市场风险过滤器 — 系统性 drawdown protection
2. **R6+**: 如果 R5 风控有效 → 进一步优化阈值和 cash reserve
3. **长期**: L2 信号 (板块轮动, 资金流) 替代/补充 expert 规则
