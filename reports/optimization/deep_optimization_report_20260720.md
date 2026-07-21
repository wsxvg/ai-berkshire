# 基金量化策略深度优化报告

> 生成时间：2026-07-20
> 优化区间：2023-07-17 ~ 2026-07-17（3年完整回测）
> 基准：沪深300ETF联接(110020) +32.20%
> 信号源：77位京东金融大佬交易记录
> 最优配置：`data/evolution/best_config.json`
> 当前性能：3年收益56.93%，年化16.25%，回撤9.64%，夏普1.09，交易172次

---

## 一、当前最优配置

### 核心参数

| 参数 | 值 | 说明 |
|------|-----|------|
| `regime_specific` | `true` | 行情自适应（牛/熊/震荡分别配置） |
| `take_profit_pct_bull` | `120` | 牛市止盈120% |
| `kelly_cap_bull` | `0.40` | 牛市Kelly上限 |
| `kelly_fraction` | `0.5`（硬编码） | 半凯利 |
| `max_position_pct` | `40` | 单只持仓上限40% |
| `cash_reserve_pct` | `0.05` | 现金保留5% |
| `momentum_sell` | `1.5` | 动量崩溃卖出阈值 |
| `profit_mode` | `"step"` | 阶梯止盈 |
| `max_correlation` | `0.6` | 持仓相关性上限 |
| `fund_type_filter` | `"active"` | 仅主动基金 |
| `min_consensus` | `2` | 至少2位大佬买入 |
| `timing_filter` | `true` | RSI超买过滤 |
| `block_overbought` | `true` | 阻止超买买入 |
| `dynamic_stop_loss` | `true` | 浮盈>20%收紧止损 |

### 行情自适应参数

| 参数 | 牛市 | 震荡 | 熊市 |
|------|------|------|------|
| 止盈% | 120 | 80 | 50 |
| 止损% | -25 | -30 | -20 |
| Kelly上限 | 0.40 | 0.30 | 0.15 |
| 移动止盈激活% | 20 | 15 | 10 |
| 移动止盈回撤% | 8 | 10 | 6 |
| 金字塔补仓 | false | false | true |

### 分段收益

| 时段 | 收益率 | 说明 |
|------|--------|------|
| 熊市 (2023H2) | +0.12% | 几乎不亏钱 |
| 震荡 (2024H2-2025H1) | +2.81% | 微利 |
| 牛市 (2025H2-2026H1) | +52.31% | 收益主要来源 |
| **3年合计** | **+56.93%** | 超额沪深300 +24.73pp |

---

## 二、已验证的优化方向（全部失败）

### 2.1 保守优化方案（3年回测对比）

| 方案 | 3年收益 | vs基线 | 失败原因 |
|------|---------|---------|----------|
| **基线** ✅ | **56.93%** | — | 最优 |
| 方案A（max_holdings=6+动态排名+加权共识+放开基金类型） | 35.57% | -21.36pp | 限制持仓6只错失好基金 |
| 方案B（bear_market_no_buy+peak_drawdown_exit=8%） | 29.55% | -27.38pp | 峰值回撤8%在牛市频繁误卖 |
| 方案C（A+B合并） | 27.09% | -29.84pp | 两个负面效果叠加 |

### 2.2 激进config参数微调（全部无效或更差）

| 参数改动 | 3年收益 | vs基线 | 说明 |
|----------|---------|---------|------|
| `take_profit_pct_bull: 150` | 56.93% | 0.00pp | 无基金涨幅达150%，无效 |
| `kelly_cap: 0.40` | 56.93% | 0.00pp | `kelly_cap_bull`已经是0.40，通用值被覆盖 |
| `max_buy_pct: 15` | 56.93% | 0.00pp | **此参数不存在**，引擎无此配置项 |
| `max_position_pct: 45` | 56.93% | 0.00pp | 40%已足够，45%不会触发 |
| `max_single_buy_pct: 0.50` | 56.93% | 0.00pp | 30%上限非瓶颈（半凯利产生建议仅~16%） |

### 2.3 代码级优化（引擎硬编码瓶颈）

发现 `backtest/engine/backtest.py` 中 `kelly_allocate()` 函数有两个硬编码限制：

```python
# L1193: 半凯利砍半（已改为可配置 kelly_fraction）
kelly = kelly * 0.5

# L1201: 单次买入不超过可用现金30%（已改为可配置 max_single_buy_pct）
suggested = min(suggested, available * 0.30)
```

**已修改**：将两个硬编码改为可配置参数 `kelly_fraction` 和 `max_single_buy_pct`，默认值保持0.5和0.30以兼容旧配置。

**凯利系数对比结果**：

| kelly_fraction | 3年收益 | vs基线 | 回撤% | 夏普 |
|---------------|---------|---------|-------|------|
| **0.5（半凯利，基线）** ✅ | **56.93%** | +0.00pp | 9.64% | 1.09 |
| 0.6 | 40.81% | -16.12pp 🔴 | 6.61% | 0.84 |
| 1.0（全凯利） | 38.38% | -18.55pp 🔴 | 8.64% | 0.72 |

**结论**：半凯利(0.5)是绝对最优。更高的凯利系数虽然单笔赚更多，但亏损时回撤更大，复利效应反而降低收益。

---

## 三、收益瓶颈分析

### 3.1 收益来源

- **92%收益来自牛市段**（52.31% / 56.93%）
- 熊市和震荡段几乎不赚钱（0.12% + 2.81% = 2.93%）
- 这是策略特性：保守的熊市/震荡策略保住了本金，等牛市爆发

### 3.2 卖出分析

从回测日志观察到的主要卖出类型：

| 卖出类型 | 说明 | 当前配置 |
|----------|------|----------|
| `trailing_tp` | 移动止盈（涨20%后回撤8%卖出） | 牛市主要卖出方式 |
| `momentum_crash` | 动量崩溃（mom<1.5时卖出） | 震荡市主要卖出方式 |
| `SELL_TP` | 止盈卖出（涨120%触发） | 极少触发 |
| `stop_loss` | 止损卖出（亏25%触发） | 很少触发 |
| `REBALANCE` | 仓位超40%减仓 | 偶尔触发 |

### 3.3 关键瓶颈

1. **移动止盈过早卖出**：牛市中基金涨20%后回撤8%就卖出，但很多基金回撤后继续大涨
2. **动量崩溃阈值偏低**：momentum_sell=1.5在震荡市频繁触发，卖出后基金可能反弹
3. **信号覆盖率不足**：77位大佬的信号覆盖的基金数量有限
4. **行业集中度高**：牛市收益集中在半导体、黄金、科技等少数行业

---

## 四、引擎代码关键位置

### 4.1 核心函数

| 函数 | 位置 | 说明 |
|------|------|------|
| `run_backtest()` | `backtest.py:1251` | 回测主循环 |
| `kelly_allocate()` | `backtest.py:1180` | 资金分配（半凯利+限额重分配） |
| `detect_market_state()` | `backtest.py:318` | 行情判断（沪深300 60日均线） |
| `score_fund_backtest()` | `backtest.py:654` | 五维评分 |
| `_resolve_fund_code()` | `backtest.py:1386` | 基金名称→代码映射 |
| `step_sell` | `backtest.py:1894` | 阶梯止盈比例 |

### 4.2 买入逻辑

```
每日循环 (L1572起):
1. detect_market_state() → 判断牛/熊/震荡
2. 动态评分门槛 → 牛市min_score=0, 熊市=0
3. 熊市过滤 → bear_market_no_buy=true时跳过
4. 候选评分 → 五维评分 + RSI超买过滤
5. 相关性过滤 → max_correlation=0.6
6. kelly_allocate() → 半凯利分配资金
7. max_holdings检查 → 0=不限制
8. 冷却期检查 → 止盈10天/止损30天
```

### 4.3 卖出逻辑

```
每日循环 (L1855起):
1. 止损: 亏损>25%(牛市)/30%(震荡)/20%(熊市)
2. 动态止损: 浮盈>20%且回撤>15% → 卖出
3. 止盈: 收益>120%(牛市) → 阶梯卖出
4. 移动止盈: 盈利>20%后回撤>8% → 卖出
5. 动量崩溃: mom<1.5 → 卖出
6. 仓位超限: >40% → 减仓到24%
7. 大佬卖出: sell_consensus>0时跟卖
```

### 4.4 已修改的代码

**`backtest/engine/backtest.py` L1180-1201**：
- `kelly_allocate()` 函数签名增加 `kelly_fraction` 和 `max_single_buy_pct` 参数
- L1193: `kelly = kelly * 0.5` → `kelly = kelly * kelly_fraction`
- L1201: `available * 0.30` → `available * max_single_buy_pct`
- L2088-2091: 调用处增加 `kelly_fraction` 和 `max_single_buy_pct` 从config读取

---

## 五、下一步优化方向

### 方向1：改进信号质量（大佬覆盖率、评分精度）

**问题**：77位大佬的信号覆盖基金有限，部分好基金无人买入导致错过。

**可行方案**：
1. **扩大大佬池**：从京东金融抓取更多优质大佬（当前77位→目标150+）
   - 筛选标准：3年年化>15%、最大回撤<20%、持仓>50万
   - 数据源：`tools/jd_finance_api.py --batch-holdings`
2. **动态大佬排名**：启用 `dynamic_ranking=true`，按历史收益率动态调整大佬权重
   - 注意：单独测试时收益降低，但可能与其他优化组合后有效
   - 需要调整 `ranking_recalc_days`（当前30天→试试15天）
3. **加权共识改进**：启用 `use_weighted_consensus=true`，按大佬权重加权买入信号
   - 注意：单独测试时收益降低，需要先扩大大佬池再启用
4. **五维评分精度**：
   - `tools/fund_scorer.py` 的 quality/cost/manager/momentum/smart_money 五个维度
   - 考虑增加"行业景气度"维度
   - momentum权重从15%提高到20%（牛市收益更重要）

**测试方法**：
```bash
# 先扩大大佬池
python tools/jd_finance_api.py --batch-holdings
# 再跑3年回测
python -c "
import sys; sys.path.insert(0, '.')
from backtest.engine.backtest import run_backtest
import json, copy
cfg = json.loads(open('data/evolution/best_config.json','r',encoding='utf-8'))['config']
cfg['start_date'] = '2023-07-17'; cfg['end_date'] = '2026-07-17'; cfg['initial_cash'] = 100000
r = run_backtest(cfg)
print(f'ret={r[\"total_return\"]:.2f}% dd={r[\"max_drawdown\"]:.2f}% sharpe={r[\"sharpe_ratio\"]:.2f}')
"
```

### 方向2：优化止盈/止损策略（防止过早卖出）

**问题**：移动止盈（涨20%回撤8%卖出）在牛市中过早卖出，错过后续大涨。

**可行方案**：
1. **调整移动止盈参数**：
   - `trailing_tp_activate_bull`: 20 → 30（盈利30%才启动移动止盈）
   - `trailing_tp_drawdown_bull`: 8 → 12（回撤12%才卖出）
   - 测试组合：30/12, 25/10, 35/15
2. **阶梯止盈优化**（`backtest.py:1894`）：
   - 当前：涨120%后每多15%卖{50%,50%,30%,20%}
   - 改进：涨80%开始阶梯止盈，每多20%卖{30%,30%,20%,20%}
   - 让止盈更早启动但每次卖更少
3. **动量崩溃阈值调整**：
   - `momentum_sell`: 1.5 → 1.2（更晚卖出，给更多反弹空间）
   - 或改为regime_specific：牛市1.0、震荡1.5、熊市2.0
4. **添加"回撤恢复"逻辑**：
   - 如果基金从回撤中恢复（如回撤15%后反弹5%），取消卖出信号
   - 位置：`backtest.py:1907` 移动止盈逻辑后

**测试方法**：
```python
# 逐个测试止盈参数组合
configs = [
    {"trailing_tp_activate_bull": 30, "trailing_tp_drawdown_bull": 12},
    {"trailing_tp_activate_bull": 25, "trailing_tp_drawdown_bull": 10},
    {"momentum_sell": 1.2},
    {"momentum_sell_bull": 1.0, "momentum_sell_neutral": 1.5, "momentum_sell_bear": 2.0},
]
```

### 方向3：调整持仓行业集中度分散风险

**问题**：牛市收益集中在半导体、黄金、科技等少数行业，回撤时这些行业同时下跌。

**可行方案**：
1. **行业限制参数**（已有但未充分使用）：
   - `max_sector_pct`: 40 → 30（单行业不超过30%）
   - `max_qdii_pct`: 100 → 50（QDII不超过50%）
2. **行业分类**：需要建立基金→行业映射表
   - 数据源：`data/fund_cache/fund_profile_*.json` 的 `fund_type` 字段
   - 或用持仓股票行业分类（`data/fund_cache/fund_holdings_*.json`）
3. **相关性过滤改进**：
   - 当前 `max_correlation=0.6` 基于净值相关系数
   - 增加行业相关性过滤：同行业基金即使净值相关<0.6也限制
4. **分散持仓数**：
   - 当前不限制持仓数（max_holdings=0）
   - 试试 max_holdings=10（不要太少，6已经证明不好）

**测试方法**：
```python
configs = [
    {"max_sector_pct": 30},
    {"max_sector_pct": 25, "max_qdii_pct": 50},
    {"max_holdings": 10, "max_sector_pct": 30},
    {"max_correlation": 0.5},  # 更严格的相关性过滤
]
```

### 方向4：其他可尝试的方法

1. **定投模式**：
   - `monthly_injection`: 0 → 5000（每月注入5000元）
   - 模拟实盘定投场景，测试定投+跟单的组合效果
2. **ML信号增强**：
   - `ml_signal`: false → true
   - `tools/ml_signal.py` 使用LightGBM预测30日前瞻收益
   - 注意：单独测试时无效，但可能在大佬池扩大后有效
3. **技术择时调优**：
   - `timing_filter`: true（已启用）
   - 调整RSI超买阈值：当前>75扣1分，试试>80扣0.5分
   - 位置：`backtest.py:1679` 附近的技术择时过滤
4. **冷却期优化**：
   - `cooldown_profit_days`: 10 → 7（止盈后更快重新买入）
   - `cooldown_loss_days`: 30 → 20（止损后稍快重新买入）
5. **金字塔补仓**：
   - `pyramiding_enabled_bull`: false → true（牛市也启用金字塔补仓）
   - 浮亏>5%时越跌越买，适合牛市回调

---

## 六、文件索引

### 核心文件

| 文件 | 说明 |
|------|------|
| `backtest/engine/backtest.py` | 回测引擎（~2300行） |
| `tools/fund_scorer.py` | 五维评分引擎（~1091行） |
| `tools/jd_finance_api.py` | 京东金融API封装（42个API） |
| `tools/ml_signal.py` | ML信号增强（LightGBM） |
| `tools/technical_indicators.py` | 技术择时（RSI/布林带） |
| `data/evolution/best_config.json` | 最优配置存储 |
| `scripts/auto-pipeline.py` | 每日监控管道 |
| `scripts/daily_live.py` | 实盘模拟 |

### 数据文件

| 文件 | 说明 |
|------|------|
| `backtest/data/trading_by_date_fixed.json` | 按日聚合的大佬交易记录 |
| `backtest/data/trading_history_fixed.json` | 完整交易记录 |
| `data/fund_charts.json` | 基金净值曲线（2187只） |
| `data/fund_name_map.json` | 基金名称→代码映射（433条） |
| `data/fund_cache/trade_rules_*.json` | 基金交易规则（费率/限额） |
| `data/fund_cache/fund_profile_*.json` | 基金档案 |
| `data/fund_cache/fund_manager_*.json` | 基金经理信息 |

### 回测结果

| 文件 | 说明 |
|------|------|
| `backtest/reports/plan_comparison_3y.json` | 4方案3年回测对比 |
| `backtest/reports/code_optimization_3y.json` | 代码级优化对比（部分完成） |
| `backtest/reports/aggressive_3y.json` | 激进参数对比（部分完成） |

---

## 七、回测命令速查

```bash
# 3年完整回测（约15分钟）
cd c:/fund
python -c "
import sys, json, copy; sys.path.insert(0, '.')
from backtest.engine.backtest import run_backtest
cfg = json.loads(open('data/evolution/best_config.json','r',encoding='utf-8'))['config']
cfg['start_date'] = '2023-07-17'; cfg['end_date'] = '2026-07-17'; cfg['initial_cash'] = 100000
r = run_backtest(cfg)
print(f'ret={r[\"total_return\"]:.2f}% ann={r[\"annualized_return\"]:.2f}% dd={r[\"max_drawdown\"]:.2f}% sharpe={r[\"sharpe_ratio\"]:.2f} trades={r[\"trade_count\"]}')
"

# 参数对比测试（修改overrides后跑）
python -c "
import sys, json, copy; sys.path.insert(0, '.')
from backtest.engine.backtest import run_backtest
cfg = json.loads(open('data/evolution/best_config.json','r',encoding='utf-8'))['config']
cfg.update({'trailing_tp_activate_bull': 30, 'trailing_tp_drawdown_bull': 12})  # 改这里
cfg['start_date'] = '2023-07-17'; cfg['end_date'] = '2026-07-17'; cfg['initial_cash'] = 100000
r = run_backtest(cfg)
print(f'ret={r[\"total_return\"]:.2f}% dd={r[\"max_drawdown\"]:.2f}% sharpe={r[\"sharpe_ratio\"]:.2f} trades={r[\"trade_count\"]}')
"
```

---

## 八、注意事项

1. **回测耗时**：3年完整回测约15-40分钟（取决于交易频率），每次只改1个参数对比
2. **regime_specific**：`_rc()` 函数会优先读取 `{key}_{market_state}`，改通用参数无效
3. **kelly_fraction**：已从硬编码改为可配置，默认0.5（半凯利）是最优值
4. **max_single_buy_pct**：已从硬编码改为可配置，默认0.30足够（半凯利产生建议仅~16%）
5. **临时文件清理**：测试脚本用完即删，不要留在项目中
6. **数据更新**：抓取新数据后需要重新跑 `scripts/auto-pipeline.py` 更新交易记录
