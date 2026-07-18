# 长周期辅助策略设计

日期：2026-07-18
状态：已批准，实现中

## 背景

现有 19 个策略全部基于日线（每天跟随大佬信号决策）。长周期指标（周线 MACD、年线、月线布林带）用于**市场状态判断**和**仓位调节**，不干预每日买入卖出决策。

- 现有短线策略 → 决定"今天买哪只基金"
- 长周期策略 → 决定"今天该重仓还是轻仓"

两者互补，不冲突。

## 新增函数（tools/technical_indicators.py）

全部接收 `nav_values`（净值序列，与现有函数约定一致），无依赖纯 Python：

1. `compute_weekly_rsi(nav_values, period=14)` — 每5天取1点重采样为周线，复用 `compute_rsi`
2. `compute_weekly_macd(nav_values, fast=12, slow=26, signal=9)` — 周线重采样后复用 `compute_macd`，返回 `(macd_line, signal_line, histogram)`
3. `compute_macd_divergence(nav_values)` — 对比近2个价格高点与 MACD 高点，返回 `"top"`/`"bottom"`/`None`
4. `compute_weekly_bollinger(nav_values, period=20, std_mult=2.0)` — 周线重采样后复用 `compute_bollinger_bands`，返回 `(upper, middle, lower, %b)`
5. `compute_ma_250(nav_values)` — 返回 `(current_nav, ma_250, above_ma)`

## 引擎集成（backtest/engine/backtest.py）

### kelly_allocate 改动

新增可选参数 `market_discount=1.0`，在 `available = total_cash * (1 - cash_reserve)` 后乘 `available *= market_discount`。默认 1.0 不影响现有策略。

### 每日循环集成（detect_market_state 之后）

计算 `_market_discount`（默认 1.0）：
- 顶背离 → `_market_discount *= 0.7`
- 布林带 %b > 0.8 → `_market_discount *= 0.8`
- 布林带 %b < 0.2 → `_market_discount *= 1.2`

年线过滤单独处理：跌破年线时 `_dyn_max_pos` 减半，重回年线恢复。

### CSI300 净值获取

复用 `detect_market_state` 已用的 `benchmark_code="110020"`，从 `fund_charts` 取数据转 nav_values，不新增数据依赖。

## 策略定义

等 19 策略跑完选 baseline 后跑：

- **策略18**：`{baseline, weekly_macd_divergence=true}` — 顶背离仓位×0.7
- **策略19**：`{baseline, yearly_ma_filter=true}` — 跌破年线仓位减半
- **策略20**：`{baseline, weekly_bollinger_adjust=true}` — %b>0.8×0.8, %b<0.2×1.2
- **策略21**：`{baseline, 三合一全开}`

## 铁律

1. 不停当前正在跑的 19 策略
2. 不改 `backtest/data/` 原始数据
3. 长周期函数仅在 config 开启时生效，不影响现有策略
4. 临时文件用完即删
