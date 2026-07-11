
## 触发短语 (triggers)

以下自然语言/命令会自动触发本 SKILL:

- `基金卖出检查 {代码}`
- `该卖了吗`
- `fund-sell {代码}`


## 必读数据

| 文件 | 用途 |
|------|------|
| `reports/sim/virtual_portfolio.json` | 虚拟持仓 + PnL |
| `data/trading_records_cache.json` | 交易记录 (供 fund_rules) |
| `data/holdings_diff_cache.json` | 持仓变化 (供 fund_rules) |
| `data/auto/status.json` | 实时状态 |
| `data/industry_valuation.json` | 行业估值 (供卖出择时) |

**输入**: 用户持仓代码 / `--my-holdings` 自动读

# 场外基金卖出决策

对 $ARGUMENTS 检查已持仓基金是否需要卖出/减仓。支持参数 `--my-holdings` 自动读取自身持仓，或传入基金代码列表手动指定。

**依赖**：`tools/fund_rules.py`（量化规则引擎）| `data/trading_records_cache.json` | `data/holdings_diff_cache.json` | `data/auto/status.json`

## 执行流程

**四级信号按频率执行**：每日🔴 → 每周🟡🟢 → 每月🔵。

### 步骤 A（每日）：读取输入 → fund_rules 分析 → LLM 判断

#### A1：读取持仓

```bash
python tools/jd_finance_api.py --my-holdings
```

读取 `data/holdings_diff_cache.json` + `data/trading_records_cache.json`。

#### A2：调用 fund_rules 获取量化信号

```bash
python tools/fund_rules.py --analyze {基金代码}
```

输出 JSON 格式：
```json
{
  "weighted_clear": { "weighted_clear": 3.0, "verdict": "red_clear" },
  "buy_shield": { "shield_active": true, "strength": "strong" },
  "take_profit": { "target_profit_pct": 50 },
  "swap_cost": { "should_swap": true },
  "suggestions": ["🔴 硬性清仓→执行"]
}
```

#### A3：LLM 判断（基于 fund_rules 输出做最终决策）

| fund_rules 信号 | LLM 判断要点 |
|----------------|-------------|
| `weighted_clear.verdict = "red_clear"` | ⚠️ 看 `buy_shield` 是否激活→分歧观察还是执行清仓 |
| `buy_shield.shield_active = true` | 大佬在买你的持仓→持有确认，跳过减仓 |
| `take_profit` 阈值 | LLM 结合当前收益率判断是否需要止盈 |
| `swap_cost.should_swap = false` | 调仓成本过高→不调仓 |

**输出格式**（与原来一致，只改数据源）：

```markdown
## 🔴 卖出建议：硬性卖出

### {基金名}（{代码}）
- **触发信号**：大佬集体清仓加权≥3 + 交易流水确认卖出
- **买入日期**：{日期} | **持有收益率**：{收益率}
- **建议操作**：立即清仓
- **理由**：...
```

### 步骤 B（每周）：减仓信号（🟡）

同样调用 `tools/fund_rules.py`，重点看 `weighted_clear` 的 `weighted_reduce` 字段。

| fund_rules 指标 | 含义 | 减仓比例 |
|----------------|------|:-------:|
| `weighted_clear.weighted_clear ≥ 3` | 🔴 硬性清仓 | 清仓 |
| `weighted_clear.weighted_clear ≥ 2` | 🟡 多人减仓 | 1/3 |
| `weighted_clear.weighted_reduce ≥ 2` | 🟡 减仓>50%加权人数 | 1/3 |
| `buy_shield.shield_active = true` | 买入护盾 | 跳过 |

**多个信号同时触发时取最大减仓比例，不叠加。**

### 步骤 C（每周/双周）：止盈（🟢）

`take_profit` 字段提供基金类型对应的止盈/止损阈值。LLM 结合当前收益率做最终判断：

- 收益达到 `target_profit_pct` → 止盈
- 亏损超过 `stop_loss_pct` → 止损（纯被动指数不设止损）

### 步骤 D（每月）：组合管理（🔵）

`swap_cost` 字段计算调仓成本。LLM 判断仓位过重或重复时是否调仓：

- 单只主动基金 > 15% → 减仓至 10%
- 跨基金持仓重叠度 > 50% → 减仓重复的
- `swap_cost.should_swap = true` → 可调仓；`false` → 不调

### 大佬卖出信号加权计算

不再手算。`python tools/fund_rules.py --analyze` 自动输出加权结果。

**LLM 只需注意**：交易流水 > 持仓快照。如果 `trading_records` 显示多人买入但 `holdings_diff` 显示清仓→分歧观察。

### 最终输出

报告保存到 `reports/卖出建议/sell-{YYYYMMDD}-{frequency}.md`，格式不变。

## 与 fund-monitor 的分工

| 分工 | fund-monitor | fund-sell |
|------|-------------|-----------|
| 数据采集 | 每日拉取持仓+交易流水 | 读取缓存 |
| 量化计算 | — | `fund_rules.py` 负责 |
| 最终判断 | — | LLM 负责 |