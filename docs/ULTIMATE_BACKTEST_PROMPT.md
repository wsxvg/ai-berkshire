# 长周期辅助策略 — 新增回测方案

> **前提**：当前的 19 个策略回测不要动，等那批跑完选出最优配置作为 baseline。
> 下面的策略是新增的，用选出的 baseline 配置 + 新增参数对跑。

---

## 背景

现有策略全部基于**日线**（每天跟随大佬信号决策）。长周期指标（周线MACD、年线、月线布林带）可用于**市场状态判断**和**仓位调节**，不干预每日买入卖出决策。

**区别**：
- 现有短线策略 → 决定"今天买哪只基金"
- 长周期策略 → 决定"今天该重仓还是轻仓"

两者互补，不冲突。

---

## 需要改的代码

### 1. `tools/technical_indicators.py` 新增 4 个函数

```python
def compute_weekly_rsi(nav_values, period=14):
    """将日线NAV(每5天取1点)重采样为周线，再算RSI"""

def compute_weekly_macd(nav_values, fast=12, slow=26, signal=9):
    """周线MACD，返回 macd_line, signal_line, histogram"""

def compute_macd_divergence(nav_values):
    """检测周线MACD顶背离/底背离：
    顶背离 = 价格创新高但MACD未创新高 → 返回 "top"
    底背离 = 价格创新低但MACD未创新低 → 返回 "bottom"
    无背离 = 返回 None
    """

def compute_weekly_bollinger(nav_values, period=20, std_mult=2.0):
    """周线布林带（每5天1点），返回 (upper, middle, lower, %b)"""

def compute_ma_250(nav_values):
    """250日移动平均线（年线），返回 (current_nav, ma_250) 和 是否在年线上方"""
```

### 2. `backtest/engine/backtest.py` 新增配置项

在每日循环顶部（检测完 `_market_state` 后）加入：

```python
# ── 长周期辅助参数 ──
if config.get("weekly_macd_divergence", False):
    from tools.technical_indicators import compute_macd_divergence
    _div = compute_macd_divergence(_get_csi300_nav())  # 需要补充获取方法
    if _div == "top":
        _market_discount = 0.7   # 顶背离 → 仓位×0.7
    elif _div == "bottom":
        _market_discount = 1.0   # 底背离 → 仓位不变（让短线决定）

if config.get("yearly_ma_filter", False):
    from tools.technical_indicators import compute_ma_250
    _nav, _ma250 = compute_ma_250(_get_csi300_nav())
    if _nav < _ma250:
        _yearly_bear = True  # 跌破年线 → 强制防守

if config.get("weekly_bollinger_adjust", False):
    from tools.technical_indicators import compute_weekly_bollinger
    _, _, _, _bb_pct = compute_weekly_bollinger(_get_csi300_nav())
    if _bb_pct > 0.8:
        _bb_adjust = 0.8      # 接近上轨 → 仓位×0.8
    elif _bb_pct < 0.2:
        _bb_adjust = 1.2      # 接近下轨 → 仓位×1.2
```

然后在 `kelly_allocate` 的资金计算中，把 `_market_discount`、`_yearly_bear`、`_bb_adjust` 乘进去。

---

## 策略定义

### 策略18：周线MACD顶底背离辅助

```
config = {baseline, weekly_macd_divergence=true}
逻辑：
  周线MACD顶背离 → 买入金额×0.7
  底背离 → 正常（底背离不代表立刻涨，牛市底背离很少）
```

### 策略19：年线牛熊过滤

```
config = {baseline, yearly_ma_filter=true}
逻辑：
  CSI300在年线上方 → 正常
  跌破年线 → 仓位上限减半，开启金字塔补仓
  重回年线 → 恢复正常
```

### 策略20：周线布林带仓位调节

```
config = {baseline, weekly_bollinger_adjust=true}
逻辑：
  %b > 0.8 → 仓位×0.8
  %b < 0.2 → 仓位×1.2
```

### 策略21：三合一（全开）

```
config = {baseline, weekly_macd_divergence=true, yearly_ma_filter=true, weekly_bollinger_adjust=true}
```

---

## 跑法

只跑**三年全周期**（不需要分段），对比 baseline 即可。

```
4 个策略 × 约 50 分钟/个 ≈ 3.5 小时
```

模板：

```python
import json, sys
sys.path.insert(0, '.')
from backtest.engine.backtest import run_backtest

baseline = {}  # 从19个里选出的最优config
base = dict(baseline)
base['start_date'] = '2023-07-17'
base['end_date'] = '2026-07-17'
base['initial_cash'] = 100000

# 然后逐个加新增参数
# base['weekly_macd_divergence'] = True
# base['yearly_ma_filter'] = True
# ...
result = run_backtest(base)
```

---

## 铁律

1. `py -3.10`
2. 等当前 19 个跑完、选出 baseline，再跑这些
3. 不改 `backtest/data/` 原始数据
4. 长周期函数只在 config 开启时才生效，不影响现有策略