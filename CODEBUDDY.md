# CODEBUDDY.md This file provides guidance to CodeBuddy when working with code in this repository.

## 常用命令

```bash
# 一键监控（每日运行，输出持仓择时分析）
py -3.10 run.py

# 每日自动管道（抓取JD数据+评分+生成报告）
py -3.10 scripts/auto-pipeline.py
py -3.10 scripts/auto-pipeline.py --offline  # 仅用缓存

# 回测验证
py -3.10 scripts/validate_backtest.py --quick

# 单次回测（自定义参数）
py -3.10 -c "from backtest.engine.backtest import run_backtest; run_backtest({...})"

# 安装ML依赖
py -3.10 -m pip install lightgbm scikit-learn numpy chinese_calendar
```

Python 必须用 3.10（`py -3.10`），不要用系统默认的 3.14。

## 核心架构

### 数据流

```
京东金融API → holdings_snapshot.json (大佬持仓)
           → trading_records_*.json (大佬交易流水)
           → fund_charts.json (273只基金累计收益率曲线)

auto-pipeline.py → 聚合交易信号 → 五维评分 → 生成MD/HTML报告

backtest/engine/backtest.py → 回测引擎 → 评分+择时+止盈止损 → 验证策略
```

### 关键数据文件

| 文件 | 说明 | 位置 |
|------|------|------|
| `holdings_snapshot_YYYY-MM-DD.json` | **大佬持仓快照**（非用户自己的持仓） | `data/` |
| `trading_history_fixed.json` | 所有大佬交易记录（8856条，2024-03~2026-07） | `backtest/data/` |
| `trading_by_date_fixed.json` | 按日聚合的交易记录（448个交易日） | `backtest/data/` |
| `fund_charts.json` | 273只基金累计收益率曲线，yAxis=自成立来累计收益率% | `backtest/data/` |
| `fund_name_map.json` | 基金名→代码映射（433条，81.2%覆盖） | `data/` |
| `data/fund_cache/` | 基金详情缓存（profile/rules/manager/holdings） | `data/` |

**关键区分**：`holdings_snapshot` 存的是京东金融上大佬的持仓和收益率（如蓝鲸跃财、招财小猫等），**不是用户自己的持仓**。用户自己的实盘持仓记录在 `reports/auto/strategy_d_*.md` 或 `实盘记录/` 中。`profit_rate` 字段是大佬从买入到现在的总收益，不是用户的收益。

### 五维评分系统 (`tools/fund_scorer.py`)

| 维度 | 权重 | 数据来源 | 函数 |
|------|------|---------|------|
| Quality | 25% | chart/perf | `score_quality` — 1年排名、3年排名、回撤、夏普、估值 |
| Cost | 20% | trade_rules | `score_cost` — 管理费+托管费+申购费 |
| Manager | 20% | fund_manager | `score_manager` — 任职年限、历史业绩 |
| Momentum | 15% | chart | `score_momentum` — 20日均线、60日斜率、回撤恢复 |
| Smart Money | 20% | trading_history | `score_smart_money` — 大佬买入数、频率、一致性 |

回测版在 `backtest/engine/backtest.py` 中有对应的 `_backtest` 后缀函数，使用日期截断防止未来函数。

### 技术择时模块 (`tools/technical_indicators.py`)

融合 QuantDinger 开源项目的算法，**这是防止高位接盘的核心模块**：

- `compute_rsi(nav_values, period=14)` — RSI指标，>70超买，<30超卖
- `compute_overbought_score(nav_values)` — 综合超买评分（RSI+布林带+涨幅），返回负数扣分值
- `compute_mean_reversion_score(nav_values)` — 均值回归评分，RSI 30-50且趋势向上时给奖励
- `compute_entry_timing_score(chart_points, cutoff_date)` — 综合择时评分，返回dict含rsi/overbought_penalty/mean_reversion_bonus/trend/entry_score/should_warn

在回测引擎中通过 `timing_filter: True` 启用，RSI>75扣1.0分，RSI>80扣1.5分。

### 回测引擎 (`backtest/engine/backtest.py`)

入口：`run_backtest(config)` (约第900行)

**数据加载**(第904-960行)：
1. `trading_by_date_fixed.json` → 按日聚合交易
2. `trading_history_fixed.json` → 全部交易记录
3. `fund_charts.json` → 基金净值曲线
4. `fund_cache/*.json` → 费率/经理/持仓缓存
5. `fund_name_map.json` → 名称映射 + 三步模糊匹配

**每日循环**(第1060行起)：
1. `detect_market_state()` — 用沪深300(110020)判断牛/熊/中性
2. 动态评分门槛 — 牛市min_score=2.5，熊市=3.5
3. 熊市过滤 — `bear_market_no_buy=True`时跳过所有买入
4. 候选评分 — 五维评分 + 技术择时 + ML信号
5. 相关性过滤 — 与已持仓基金相关系数>0.85则排除
6. 卖出逻辑 — 止损/止盈/移动止盈/动量崩溃/仓位过重
7. 冷却期 — 止盈卖10天后可重新买入，止损卖30天

**Portfolio类**：管理持仓、T+N确认、申购费/赎回费、滑点模拟。

### ML信号增强 (`tools/ml_signal.py`)

LightGBM分类器，16维特征（五维评分+近期收益+回撤+波动率+规模+费率+共识+市场状态+基金年龄），标签为30日前瞻收益>3%。Walk-forward训练，每30天重训，`pretrain`方法严格检查前瞻数据不超过截止日（防前视偏差）。

### auto-pipeline.py

105KB，有重复的`_generate_report`函数（已知问题）。流程：
1. 加载cookies → 调JD API抓取大佬持仓和交易记录
2. `_aggregate_trading_signals` — 聚合买卖信号（买入=+1，卖出=-1）
3. 五维评分 → 生成MD报告（`reports/auto/daily-YYYY-MM-DD.md`）
4. 生成HTML报告（`reports/auto/scan-YYYY-MM-DD.html`）

**已知缺陷（初始版ai-berkshire-main的问题，本项目已修复）**：
- 初始版仅凭2人买入就生成"买入信号"，不检查RSI/超买/估值
- 导致用户在高位跟买华夏全球科技先锋(024239)，亏损-15.87%
- 本项目增加了 `timing_filter` 和 `block_overbought` 参数解决此问题

### JD金融API (`tools/jd_finance_api.py`)

42个API封装，关键接口：
- `get_user_holdings(uid)` — 获取指定大佬的持仓列表
- `get_trading_records(uid, page)` — 获取交易流水
- `get_fund_chart_data(code)` — 获取基金累计收益率曲线
- `get_fund_detail(code)` — 获取基金详情（费率/经理/规模）
- Cookies从 `data/jd_auth/cookies.json` 或 `JD_COOKIES` 环境变量加载

## 重要注意事项

1. **回测数据已验证正确**：fund_charts的yAxis是基金自成立来累计收益率%，不是用户个人收益。024239在2026-06-29的yAxis=123.40表示该基金从成立到那天涨了123%，用户当时买入后跌到101才导致-15%亏损。

2. **用户买入日RSI验证**：024239买入日RSI=62.7（未超买），013841买入日RSI=98.4（极端超买，系统会拦截），012922买入日RSI=64.4（未超买）。RSI择时能拦截部分但非全部高位买入。

3. **市场状态检测的局限**：`detect_market_state`用沪深300基准判断牛熊，但科技/QDII板块可能在"牛市"中独立回调。需要增加行业级市场状态检测。

4. **AGENTS.md** 已存在，包含兼容性规则和研究质量规则。CODEBUDDY.md补充技术架构信息。

5. **ai-berkshire-main是初始基准版本，不要修改**。所有改进只在当前项目(基金)中进行。
