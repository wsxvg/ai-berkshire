# 项目全景地图与 Bug 审计报告

> **目的**: 供 AI 助手随时查阅的项目地图 + 回测引擎/实盘模拟 Bug 审计
>
> **最后审计**: 2026-07-18
>
> **审计范围**: 回测引擎 6 个已修复 Bug 复验 + 实盘模拟系统对照 + RSI 策略对比

---

## 一、项目一句话定位

**这是一个「京东金融数据 + 五维评分 + 严格回测 + SKILL 工作流」的场外基金智能投资系统**。核心是「抓数据→评分→规则→决策→回测→进化」闭环，目标是实现场外基金的自动化投资决策。

---

## 二、核心架构（6 层）

```
┌─────────────────────────────────────────────────────────────┐
│  Layer 6: SKILL 交互层（30 个 .md，用户在 IDE 触发）       │
├─────────────────────────────────────────────────────────────┤
│  Layer 5: Pipeline 编排                                    │
│  - scripts/daily_live.py        ← 每日实盘模拟（GitHub Actions）│
│  - scripts/auto-pipeline.py     ← 每日数据抓取+评分+报告    │
│  - scripts/generate_report.py   ← 深度 Checklist            │
├─────────────────────────────────────────────────────────────┤
│  Layer 4: 决策引擎                                          │
│  - tools/decision_engine.py     ← 5 步决策                  │
├─────────────────────────────────────────────────────────────┤
│  Layer 3: 评分 + 规则 + 信号                                │
│  - tools/fund_scorer.py         ← 五维评分 (40K/1105 行)    │
│  - tools/fund_rules.py          ← 规则引擎                  │
│  - tools/technical_indicators.py ← RSI/MACD/布林带          │
│  - tools/ml_signal.py           ← LightGBM 增强             │
├─────────────────────────────────────────────────────────────┤
│  Layer 2: 数据层                                            │
│  - tools/jd_finance_api.py      ← 42 个 JD API 封装 (75K)   │
│  - tools/data_provider/         ← 数据抽象                  │
├─────────────────────────────────────────────────────────────┤
│  Layer 1: 回测引擎                                          │
│  - backtest/engine/backtest.py  ← 核心回测 (100K/2250 行)   │
└─────────────────────────────────────────────────────────────┘
```

---

## 三、关键文件清单

### 3.1 核心库（`tools/`）

| 文件 | 大小 | 用途 |
|------|------|------|
| `jd_finance_api.py` | 75K/2876 行 | 京东金融 42 个 API 封装（心脏） |
| `fund_scorer.py` | 40K/1105 行 | 五维评分（质量/成本/经理/动量/聪明钱） |
| `fund_rules.py` | 10K/237 行 | 规则引擎（清仓/护盾/止盈/调仓） |
| `fund_planner.py` | 6K/165 行 | Kelly 仓位分配 |
| `technical_indicators.py` | 12K/376 行 | RSI/MACD/布林带/均值回归 |
| `ml_signal.py` | 8K/217 行 | LightGBM walk-forward 信号 |

### 3.2 回测引擎（`backtest/engine/`）

| 文件 | 用途 |
|------|------|
| `backtest.py` | 核心回测引擎（Portfolio 类 + run_backtest） |
| `sector_valuation.py` | 行业估值过滤 |
| `notice_signal.py` | 公告信号（经理变更/估值调整） |
| `fundamental_momentum.py` | 基本面动量 |
| `speedup.py` | 速度优化 |

### 3.3 实盘模拟（`scripts/`）

| 文件 | 用途 |
|------|------|
| `daily_live.py` | **每日实盘模拟入口**（GitHub Actions 14:30） |
| `auto-pipeline.py` | 每日数据抓取 + 评分 + 报告（107K） |
| `generate_report.py` | 深度 Checklist 生成 |
| `generate_html.py` | HTML 报告 |

### 3.4 数据文件

| 文件 | 用途 |
|------|------|
| `data/evolution/best_config.json` | **冠军策略参数**（回测+实盘共用） |
| `data/fund_charts.json` | 273 只基金 1 年净值（实盘用） |
| `backtest/data/fund_charts.json` | 回测版净值数据 |
| `backtest/data/trading_by_date_fixed.json` | 448 天大佬交易 |
| `backtest/data/trading_history_fixed.json` | 8856 笔大佬交易 |
| `reports/sim/virtual_portfolio.json` | 实盘虚拟持仓 |
| `reports/sim/YYYY-MM-DD.md` | 每日实盘模拟日报 |

---

## 四、回测引擎 6 个 Bug 修复状态复验 ✅

> 根据 [[memory:17843767377360431421]] 记录的 6 个 bug，逐一在 `backtest/engine/backtest.py` 中复验

### Bug 1: get_fee 申购费率放大 100 倍 — ✅ 已修复

**位置**: `backtest.py` L869-879

```python
def get_fee(self, code, default_purchase_fee=0.0015):
    rules = self.fund_rules.get(code, {})
    pf = rules.get("purchase_fee", default_purchase_fee * 100)
    ...
    return float(pf) / 100  # 0.15→0.0015, 1.5→0.015
```

**验证**: 京东 API 返回 `purchase_fee=0.15` 表示 0.15%，除以 100 转为 0.0015 小数。✅ 正确

### Bug 2: get_redeem_fee interval 格式解析失败 — ✅ 已修复

**位置**: `backtest.py` L881-926

```python
def get_redeem_fee(self, code, days_held):
    ...
    nums = [int(x) for x in _re.findall(r'\d+', interval)]
    has_dash = "-" in interval and len(nums) == 2
    if has_dash:
        low, high = nums[0], nums[1]
        if low <= days_held < high: return rate
    ...
```

**验证**: 用正则提取数字，支持 `<7天` / `7-365天` / `≥365天` / `7天≤持有期限<365天` 四种格式。✅ 正确

**小瑕疵**: L906 `["≥", ">", "≥"]` 有重复的 `≥`，但无害（不影响逻辑）

### Bug 3: score_cost 双重打折 — ✅ 已修复

**位置**: `tools/fund_scorer.py` L548-560

```python
def score_cost(rules: dict, discount: float = PURCHASE_DISCOUNT) -> DimensionScore:
    ...
    # 京东API: purchase_fee 是渠道打折后的实际费率，purchase_fee_original 是原费率
    # 评分时用实际费率（已是打折值），不再重复打折
    purchase = _float(rules.get("purchase_fee", 0))
```

**验证**: 函数签名保留 `discount` 参数但函数体内未使用（避免破坏向后兼容）。✅ 正确

### Bug 4: max_yearly_trades 硬编码且从未执行 — ✅ 已修复

**位置**: `backtest.py` L833, L984-987, L1384

```python
# 类默认值
self.max_yearly_trades = 50  # 原来是 6

# buy() 中检查
if self.yearly_trades.get(_yr, 0) >= self.max_yearly_trades:
    return False

# 从 config 读取
portfolio.max_yearly_trades = config.get("max_yearly_trades", 50)
```

**验证**: 默认 50（可配置），在 `buy()` 中实际执行检查。✅ 正确

### Bug 5: get_t_plus_n 跨月计算错误 — ✅ 已修复

**位置**: `backtest.py` L928-952

```python
def get_t_plus_n(self, code):
    ...
    _year = datetime.now().year
    b_str = buy_date.split(" ")[0]  # "07-06"
    b_dt = datetime.strptime(f"{_year}-{b_str}", "%Y-%m-%d")
    c_dt = datetime.strptime(f"{_year}-{confirm}", "%Y-%m-%d")
    diff = (c_dt - b_dt).days
```

**验证**: 用完整日期解析（补全年份），避免跨月错误。✅ 正确

**潜在问题**: 用 `datetime.now().year` 而非回测当前年份——若回测跨年数据可能偏差 1 年，但 T+N 通常 ≤7 天，影响极小

### Bug 6: sell_price 用前一天净值 — ✅ 已修复（回测引擎）

**位置**: `backtest.py` L1823

```python
sell_price = current_nav  # 用当天净值（与买入一致，实盘T日赎回按当日净值）
```

其中 `current_nav = (100 + y) / 100`，`y = valid[-1].get("yAxis")`，`valid = _bisect_valid(pts, cutoff_full)` —— 取截止到当天的最新净值。✅ 正确

---

## 五、🚨 实盘模拟系统 Bug 审计（daily_live.py）

> **关键发现**: 回测引擎的 6 个 bug 已修复，但 `daily_live.py` 实盘模拟系统中 **bug #6 仍然存在**，且新增了 2 个严重 bug

### 🚨 Bug A: 卖出价格硬编码为 1.0（严重）

**位置**: `scripts/daily_live.py` L357, L371, L377, L387

```python
# 止盈
if actual_pnl >= GENE.get("take_profit_pct", 80):
    portfolio.sell(code, h["cost"], 1.0, TODAY, "take_profit", False)  # ← price=1.0!

# 动态止损
elif GENE.get("dynamic_stop_loss") and actual_pnl > 20:
    ...
    portfolio.sell(code, h["cost"], 1.0, TODAY, "dyn_stop_loss", False)  # ← price=1.0!

# 止损
elif actual_pnl <= GENE.get("stop_loss_pct", -15):
    portfolio.sell(code, h["cost"], 1.0, TODAY, "stop_loss", True)  # ← price=1.0!

# 动量崩溃
elif day_ret < -8 and market != "bull":
    ...
    portfolio.sell(code, h["cost"], 1.0, TODAY, "momentum_crash", True)  # ← price=1.0!
```

**影响**:
- `Portfolio.sell()` 用 `price` 计算卖出收入：`proceeds = h["shares"] * price`
- 当 `price=1.0` 时，卖出收入 = 持有份额 × 1.0 = 成本（忽略实际净值）
- 若基金涨了 20%（实际 NAV=1.2），应得 1.2× 份额的钱，但实盘只记 1.0× 份额
- **卖出后现金错误，后续所有 PnL 计算全错**

**当前状态**: `sell_history` 为空（`virtual_portfolio.json` L202），尚未触发卖出（60 天最低持有期，7 月 1 日开始至今仅 17 天）。**一旦触发卖出，PnL 将完全失真**

**修复方案**:
```python
# 应改为（与回测引擎一致）
portfolio.sell(code, h["cost"], latest_nav, TODAY, "take_profit", False)
```
其中 `latest_nav` 已在 L347 计算：`latest_nav = (100 + latest_yaxis) / 100`

---

### 🚨 Bug B: 持仓恢复丢失份额和买入净值（严重）

**位置**: `scripts/daily_live.py` L239-244

```python
for code, h in vp.get("holdings", {}).items():
    cb = h.get("cost_basis", 5000)
    portfolio.holdings[code] = {
        "name": h["name"], "shares": cb, "cost": cb,        # ← shares=cost_basis（错误!）
        "buy_date": h.get("buy_date", TODAY), "buy_nav": 1.0,  # ← buy_nav=1.0（错误!）
    }
```

**影响**:
- `shares` 应为实际份额（如 18000元 ÷ 1.05净值 ≈ 17143 份），但被设为 `cost_basis`（如 100）
- `buy_nav` 应为实际买入净值，但被设为 `1.0`
- 卖出时 `proceeds = shares * price = 100 * 1.0 = 100`（应为 `17143 * current_nav`）
- PnL 计算也错误：`mv = h["cost"] * (latest_nav / buy_nav) = 100 * (latest_nav / 1.0)`

**验证**: `virtual_portfolio.json` 显示
- 016664: `cost_basis=100`（实际买入 ¥18,000，被 day_limit 限制为 ¥100）
- 024239: `cost_basis=1000`（实际买入 ¥18,000，被 day_limit 限制为 ¥1,000）
- 013841: `cost_basis=17500`（无 day_limit 限制，全额买入）

**修复方案**: 在 `virtual_portfolio.json` 中保存 `shares` 和 `buy_nav`，恢复时使用实际值

---

### ⚠️ Bug C: trade_log 记录意图金额而非实际金额

**位置**: `scripts/daily_live.py` L456

```python
amount = min(per_position, available * kelly)  # = 18000
...
if portfolio.buy(c["code"], c["name"], amount, buy_price, TODAY):
    daily_trades.append({..."amount": amount})  # ← 记录 18000
```

但 `Portfolio.buy()` 内部会 `amount = min(amount, day_limit)`，实际买入可能只有 ¥100

**验证**: `virtual_portfolio.json` trade_log 显示 4 笔 ¥18,000，但现金只减少 ¥2,600（实际 4×¥650 左右）

**影响**: trade_log 误导分析，看起来买入了很多钱，实际没有

---

### ⚠️ Bug D: RSI 逻辑比回测简化

**位置**: `scripts/daily_live.py` L280-285

```python
# 实盘：只做硬拦截
if len(pts) >= 60:
    timing = compute_entry_timing_score(pts, TODAY)
    if timing.get("should_warn"):
        continue  # RSI>80 直接跳过
```

**对比回测**（`backtest.py` L1645-1662）:
```python
if config.get("timing_filter", False):
    _timing = compute_entry_timing_score(...)
    raw_score += _timing["overbought_penalty"]      # RSI 70-80 扣分
    raw_score += _timing["mean_reversion_bonus"]    # 均值回归奖励
    if _timing["trend"] < 0:
        raw_score -= config.get("downtrend_penalty", 0.5)  # 下降趋势扣分
    if config.get("block_overbought", False) and _timing["should_warn"]:
        continue  # RSI>80 拦截
```

**差异**:
| 行为 | 回测引擎 | 实盘模拟 |
|------|---------|---------|
| RSI 70-80 扣分 | ✅ `overbought_penalty` | ❌ 无 |
| 均值回归奖励 | ✅ `mean_reversion_bonus` | ❌ 无 |
| 下降趋势扣分 | ✅ `downtrend_penalty` | ❌ 无 |
| RSI>80 硬拦截 | ✅ 需要 `block_overbought=True` | ✅ 始终启用 |

**影响**: 实盘比回测更保守（始终拦截 RSI>80），但又更粗糙（无梯度扣分）

---

### ⚠️ Bug E: 买入逻辑不用 kelly_allocate

**位置**: `scripts/daily_live.py` L438-443

```python
# 实盘：简单 min(per_position, available * kelly)
available = portfolio.cash * (1 - cash_reserve)
per_position = available * max_pos / 100
kelly = GENE.get("kelly_cap", 0.2)
amount = min(per_position, available * kelly)
```

**对比回测**（`backtest.py` L2050-2056）:
```python
to_buy = kelly_allocate(candidates, portfolio.cash + ...,
    kelly_cap=_dyn_kelly, cash_reserve=_dyn_cash_reserve,
    max_pos=_dyn_max_pos / 100, market_discount=_market_discount)
```

**差异**:
- 回测用 `kelly_allocate()`：半凯利公式 + 硬上限 + 板块 bonus + market_discount
- 实盘用简单 `min(per_position, available * kelly)`：无板块 bonus、无 market_discount、无半凯利

**影响**: 实盘仓位分配与回测不一致，无法复现回测收益

---

## 六、RSI 策略对比分析（回测 vs 实盘）

### 6.1 回测结果（2023-07-17 ~ 2026-07-17，3 年）

| 排名 | 策略 | 全周期收益 | 段A(熊市) | 段B(震荡) | 段C(牛市) | 回撤 | 夏普 |
|------|------|----------|----------|----------|----------|------|------|
| 🥇 | **策略11_RSI拦截** | **37.80%** | 0.71% | 4.0% | 31.33% | 6.79% | 1.08 |
| 🥈 | 策略10_PE过滤 | 30.33% | 0.94% | 7.72% | 19.42% | 5.55% | 0.82 |
| 🥉 | 策略14_熊市不买 | 29.34% | -0.23% | 0.98% | 28.34% | 6.81% | 0.82 |
| 4 | 策略2_Champion | 26.07% | -0.15% | 2.16% | 23.55% | 7.51% | 0.67 |
| 5 | 策略3_Champion+dynSL | 23.49% | -0.15% | 2.16% | 21.03% | 8.32% | 0.58 |
| 6 | 策略12_ML信号 | 21.76% | -0.15% | 2.24% | 19.16% | 7.82% | 0.51 |

### 6.2 🚨 策略标签误导性分析

**关键发现**: 策略11「RSI拦截」的标签具有误导性

查看 `_run_3y_master.py` 中的策略定义：
```python
BASE = dict(_cfg.get('config', {}))  # 从 best_config.json 加载

"策略2_Champion": dict(BASE,
    dynamic_stop_loss=False, pyramiding_enabled=False)

"策略11_RSI拦截": dict(BASE,
    timing_filter=True, block_overbought=True)  # ← 这两个参数 BASE 已有!

"策略3_Champion+dynSL": dict(BASE)  # ← 纯 BASE，无覆盖
```

而 `best_config.json` 的 `config` 字段已包含：
- `"timing_filter": true`
- `"block_overbought": true`
- `"dynamic_stop_loss": true`

**因此**:
- 策略3 = BASE（含 RSI 拦截 + dynSL）
- 策略11 = BASE + RSI 拦截（无变化）= BASE = 策略3
- 策略2 = BASE 关闭 dynSL

**但结果差异巨大**:
- 策略3: 23.49%（regime_recover 批次，2026-07-18 20:27 跑）
- 策略11: 37.80%（newparams 批次，2026-07-18 22:04 跑）

**根本原因**: `best_config.json` 的 `note` 字段确认——"**修复 min_consensus 后** RSI 因避免追高胜出"。即代码在两次批次运行之间被修改（修复了 `min_consensus` 相关逻辑），导致同配置不同结果。

**结论**: ⚠️ **37.80% 的收益不是 RSI 拦截的功劳，而是代码修复 + dynSL 的综合结果**。回测不可复现，策略标签需要更正

### 6.3 实盘模拟现状（2026-07-01 ~ 2026-07-18，17 天）

| 指标 | 值 |
|------|------|
| 总资产 | ¥99,830.13 |
| 现金 | ¥79,800（80% 闲置） |
| 持仓 | 6 只（市值 ¥20,030） |
| 收益率 | -0.17% |
| 卖出次数 | 0（60 天最低持有期未到） |

**问题**:
1. 80% 现金闲置——day_limit 限制 + kelly_cap=0.20 + cash_reserve=0.10 导致单笔买入过小
2. 013841（银华集成电路）占比 87.5%（¥17,500 / ¥20,030）——过度集中
3. trade_log 显示买入 ¥106,500，实际只买入 ¥20,200——日志误导

### 6.4 回测 vs 实盘对照表

| 维度 | 回测引擎 | 实盘模拟 | 一致性 |
|------|---------|---------|--------|
| 评分函数 | `score_fund_backtest` | `score_fund_backtest` | ✅ 一致 |
| 市场状态 | `detect_market_state` | `detect_market_state` | ✅ 一致 |
| RSI 拦截 | 配置驱动 + 梯度扣分 | 始终启用 + 硬拦截 | ⚠️ 不一致 |
| 仓位分配 | `kelly_allocate`（半凯利+板块bonus） | 简单 `min(per_position, available*kelly)` | ⚠️ 不一致 |
| 卖出价格 | `current_nav`（当天净值） | **`1.0`（硬编码）** | 🚨 严重不一致 |
| 持仓恢复 | 不需要（单次运行） | `shares=cost_basis, buy_nav=1.0` | 🚨 错误 |
| T+N 确认 | `Portfolio.settle_pending` | `Portfolio.settle_pending` | ✅ 一致 |
| 费率计算 | `get_fee / get_redeem_fee` | `get_fee / get_redeem_fee` | ✅ 一致 |
| 冷却期 | `is_in_cooldown` | `is_in_cooldown` | ✅ 一致 |

---

## 七、其他设计问题

### 7.1 best_config.json 参数问题

```json
{
  "min_score": 0.0,
  "min_score_bull": 0.0,
  "min_score_neutral": 0.0,
  "min_score_bear": 0.0,
  "fund_type_filter": "active",
  "max_sector_pct": 40,
  "kelly_cap": 0.20
}
```

**问题**:
- `min_score=0.0` 意味着任何正分基金都买——过于激进
- `fund_type_filter="active"` 排除指数基金——可能错过低成本指数机会
- `kelly_cap=0.20` 单笔上限 20%——结合 day_limit 导致大量现金闲置

### 7.2 回测过拟合风险

**段A（熊市 2023-07-17 ~ 2024-06-30）表现**:
- 最优: 策略10_PE过滤 0.94%
- 多数策略为负值
- **所有策略在熊市几乎不赚钱**

**段C（牛市 2025-07-01 ~ 2026-07-17）表现**:
- 策略11: 31.33%
- 策略14: 28.34%

**结论**: 策略主要在牛市赚钱，熊市/震荡期收益极低。**37.80% 的三年收益主要来自段C牛市**，存在过拟合风险

### 7.3 18 月窗口 vs 3 年窗口

根据 [[memory:17843767377360431421]] 记录：
- 18 月窗口 K 跟投 = +82.64%（已过拟合）
- 3 年窗口 K 跟投 = +22.83%（更真实）
- 3 年窗口 RSI 拦截 = +37.80%（当前最优，但需警惕代码变更影响）

### 7.4 数据时点风险

- `data/fund_charts.json`（实盘用）vs `backtest/data/fund_charts.json`（回测用）——不同文件
- `data/fund_cache/trade_rules_*.json` 30 天有效——费率/限额可能过期
- 大佬交易数据 `trading_by_date_fixed.json` 是静态快照，不更新

---

## 八、修复优先级建议

### P0（立即修复——影响实盘正确性）

1. **修复 daily_live.py 卖出价格**: `1.0` → `latest_nav`
   - 位置: L357, L371, L377, L387
   - 风险: 一旦触发卖出，PnL 完全失真

2. **修复 daily_live.py 持仓恢复**: 保存并恢复 `shares` 和 `buy_nav`
   - 位置: L239-244（恢复）+ L484-489（保存）
   - 风险: 每次重启都丢失实际份额

### P1（尽快修复——影响分析准确性）

3. **修复 trade_log 记录实际金额**: 在 `portfolio.buy()` 返回后记录实际扣款
   - 位置: L456
   - 风险: 日志误导分析

4. **统一 RSI 逻辑**: 实盘对齐回测的 `timing_filter` 配置驱动 + 梯度扣分
   - 位置: L280-285
   - 风险: 实盘比回测更保守/更粗糙

### P2（改进——提升一致性）

5. **实盘采用 `kelly_allocate`**: 与回测一致的资金分配
   - 位置: L438-443
   - 风险: 仓位分配不一致

6. **策略标签更正**: 策略11 应命名为「dynSL+RSI」或「代码修复版」
   - 位置: `_run_3y_master.py` L233
   - 风险: 误导决策

7. **min_score 调高**: 0.0 → 2.5（牛市）/ 3.0（震荡）/ 3.5（熊市）
   - 位置: `best_config.json`
   - 风险: 过于激进，买入垃圾基金

---

## 九、常用命令速查

```bash
# === 实盘模拟 ===
py -3.10 scripts/daily_live.py                          # 当日实盘模拟
py -3.10 scripts/daily_live.py --simulate-date 2026-06-15  # 模拟历史日

# === 回测 ===
py -3.10 _run_3y_master.py --batch core                 # 核心策略对比
py -3.10 _run_3y_master.py --batch newparams            # 新参数策略
py -3.10 _run_3y_master.py --batch all                  # 全部策略

# === 数据 ===
py -3.10 tools/jd_finance_api.py --test                 # Cookie 测活
py -3.10 scripts/auto-pipeline.py                       # 每日数据管道
py -3.10 scripts/generate_report.py                     # 深度 Checklist

# === 前端 ===
cd fund-ui && npm run dev                               # 本地前端
```

**Python 版本**: 必须 `py -3.10`（lightgbm/numpy 在 3.14 上不稳定）

---

## 十、审计结论

### 回测引擎
✅ **6 个 bug 全部修复**，回测引擎本身可信

### 实盘模拟
🚨 **存在 2 个严重 bug + 3 个中等问题**:
- 卖出价格硬编码 1.0（未触发但一旦触发 PnL 失真）
- 持仓恢复丢失份额（每次重启都错误）
- trade_log 记录意图金额（误导分析）
- RSI 逻辑简化（与回测不一致）
- 仓位分配简化（与回测不一致）

### RSI 策略
⚠️ **37.80% 收益不可完全归因于 RSI**:
- 策略11 与策略3 配置相同，但结果差 14.31pp
- 差异来自代码修复（min_consensus）而非 RSI 拦截
- 回测不可复现（代码在批次间被修改）

### 建议
1. **立即修复 P0 bug**——否则实盘模拟结果无意义
2. **重跑回测验证**——修复 min_consensus 后统一跑一次所有策略
3. **实盘对齐回测**——RSI 逻辑 + kelly_allocate + 卖出价格
4. **调高 min_score**——0.0 过于激进

---

**最后更新**: 2026-07-18
**审计人**: AI Berkshire 投研助手
