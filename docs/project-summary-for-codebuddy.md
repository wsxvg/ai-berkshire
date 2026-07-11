# AI Berkshire 基金监控项目 — 项目结构摘要

> 给CodeBuddy/其他AI工具使用的精简版项目地图。
> 用这个代替读代码，大幅减少token消耗。

## 一、项目架构

### 数据流
```
京东金融API → trading_history.json → trading_by_date.json → 回测引擎 → 评分 → 交易决策
                        ↑                                    ↑
                 小倍养基API → 摆动信号/热度排行 → 过度上涨扣分/广告基检测
```

### 关键目录
```
backtest/engine/backtest.py    — 回测引擎(1487行)
tools/fund_scorer.py           — 五维评分引擎(1091行)
tools/jd_finance_api.py        — 京东金融42个API封装
tools/xiaobeiyangji_api.py     — 小倍养基API(摆动信号/热度排行) [NEW]
scripts/auto-pipeline.py       — 每日监控管道(自动抓取+评分+报告)
scripts/validate_backtest.py   — 回测稳健性验证 [NEW]
scripts/build_fund_name_map.py — 基金名称→代码映射补全 [NEW]
data/fund_name_map.json        — 名称→代码映射表(81.2%覆盖率) [NEW]
data/trading_history.json      — 原始交易记录
data/trading_by_date.json      — 按日聚合的交易记录
data/fund_cache/               — 基金缓存(profile/perf/rules/holdings/manager)
```

## 二、已修复的重大问题

### 1. 日期Bug（2026-07-10修复）⭐ 最关键
- **问题**: 7929/8856条交易记录没有真实年份，日期被错误地标为前一年
- **表现**: 2026年的交易记录被标成2025年，导致回测看不到2026年的大佬买入信号
- **修复**: `scripts/auto-pipeline.py` 中 `_full_date` 赋值逻辑修正
- **影响**: 2026年华夏基金记录从30条→773条，回测从0笔交易→133笔交易

### 2. 基金名称映射补全
- **问题**: 462个基金名中只有216个(47%)能映射到代码
- **修复**: 用天天基金公开搜索API补全，覆盖率提升到81.2%
- **文件**: `data/fund_name_map.json` (433条映射)
- **回测引擎**: `backtest/engine/backtest.py` 第943-958行加载此映射

### 3. 建仓vs加仓区分
- **问题**: 每日管道把"买入""加仓""定投"全算成一个信号强度
- **修复**: `scripts/auto-pipeline.py` 的 `_aggregate_trading_signals` 中，买入=2分，加仓=1分，定投=0.5分

### 4. 过度上涨扣分（heat_penalty）
- **位置**: `backtest/engine/backtest.py` 第139-144行（`score_quality_backtest`）
- **逻辑**: 近3月涨超100%扣0.8分，涨超80%扣0.4分
- **同样**: `tools/fund_scorer.py` 第516-525行（`score_quality`）
- **注意**: 只在quality维度扣分，不要重复扣总分

### 5. 回测稳健性验证
- **脚本**: `scripts/validate_backtest.py` 
- **参数网格**: min_score=[2.5,3.0,3.3], dynamic_ranking=[false,true], max_position_pct=[15,20,25]
- **结果**: 修复后参数稳定性大幅提升

## 三、回测引擎核心逻辑

### 入口: `backtest/engine/backtest.py:890` `run_backtest(config)`

**数据加载**(第894-958行):
1. `trading_by_date_fixed.json` → 按日聚合的交易记录
2. `trading_history_fixed.json` → 所有交易记录
3. `fund_charts.json` → 273只基金的净值/收益曲线
4. `fund_cache/*.json` → 费率、经理、持仓等缓存
5. `fund_name_map.json` → 名称映射(外部补全)

**每日循环**(第977-1160行):
1. 获取该日交易记录 → 计算 `fund_signals` (按基金名聚合买入/卖出次数)
2. 对 `buy_count >= 2` 的基金依次评分
3. `score_fund_backtest()` → 五维评分
4. 总分 >= min_score(默认3.3) → 加入候选列表
5. 候选列表排序 → 按仓位限制买入

**评分函数**: `score_fund_backtest`(第415-585行)
```
momentum = score_momentum_backtest(chart_pts, cutoff_date)  # 动量(权重15%)
quality = score_quality_backtest(chart_pts, cutoff_date, scale, perf_data)  # 质量(权重25%)
cost = score_cost(rules)  # 成本(权重20%)
manager = score_manager(mgr)  # 经理(权重20%)
smart = score_smart_money_backtest(fund_name, cutoff_date, trading_by_date)  # 聪明钱(权重20%)
```
- 质量分内包含 heat_penalty（近3月涨超100%扣0.8分）
- 总分 = 加权平均 + 资产配置修正 + 规模修正

## 四、五维评分系统

### `tools/fund_scorer.py`

| 维度 | 权重 | 数据来源 | 关键指标 |
|:----|:---:|:---------|:---------|
| Quality | 25% | chart/perf | 1年排名30%, 3年排名20%, 回撤20%, 夏普10%, 估值10%, 机构15% |
| Cost | 20% | trade_rules | 管理费+托管费, 申购费, 3年总成本 |
| Manager | 20% | fund_manager | 任职年限, 历史业绩, 管理规模 |
| Momentum | 15% | chart | 20日均线25%, 60日均线斜率25%, 回撤恢复15% |
| Smart Money | 20% | trading_history | 大佬买入数量, 频率, 一致性 |

### 外部修正:
- **小倍养基摆动信号**: `get_swing_modifier(fund_code)` → highZone扣-0.8分
- **小倍养基热度排行**: `get_heat_modifier(fund_code)` → top5热度>500万扣分
- **估值修正**: `_valuation_modifier()` → PE百分位>90%扣分

## 五、数据文件说明

### `backtest/data/trading_by_date_fixed.json`
- 格式: `{"2026-01-05": [{"fund_name":"...","action":"买入/卖出","amount":"...","_user":"...","_uid":"..."}, ...], ...}`
- 448个交易日, 覆盖2024-03-11到2026-07-01
- 每个记录表示一个大佬的一次操作

### `backtest/data/fund_charts.json`
- 格式: `{"005698": [{"xAxis":"2026-01-05","yAxis":118.82}, ...], ...}`
- 273只基金, 每只约1915个数据点
- yAxis是累计收益率%（从基金成立算起）

### `data/fund_name_map.json`
- 格式: `{"华夏全球科技先锋混合(QDII)A": "005698", ...}`
- 433条映射, 覆盖率81.2%
- 来源: 天天基金公开搜索API

## 六、已知问题

1. **名称映射仍有18.8%缺失** — 主要是小众基金和不活跃基金
2. **回测只有2026H1数据** — 更早的数据需要重新抓取
3. **小倍养基API需要token** — 当前使用硬编码的unionId，可能过期
4. **经理数据缺失** — 部分基金没有 fund_manager 缓存，评分默认2.5分
5. **回测不包含手续费**（除了申购费）— 赎回费、管理费未计入回测成本

## 七、常用命令

```bash
# 跑完整回测
python -c "from backtest.engine.backtest import run_backtest; run_backtest({...})"

# 稳健性验证
python scripts/validate_backtest.py --quick

# 名称映射补全（需要重新跑）
python scripts/build_fund_name_map.py

# 测试小倍养基API
python tools/xiaobeiyangji_api.py --test

# 每日管道
python scripts/auto-pipeline.py
```