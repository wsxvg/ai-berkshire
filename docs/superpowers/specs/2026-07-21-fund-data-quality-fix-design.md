# 基金数据质量修复与全策略回测重验证 — 设计规格

> **日期**: 2026-07-21
> **状态**: 已批准，待实现
> **背景**: 回测发现严重数据质量问题——2187只基金中2185只只有≤20天数据，五维评分实际未起作用

---

## 一、问题诊断

### 1.1 数据质量现状

| 数据集 | 基金数 | 数据点分布 | 问题 |
|--------|--------|-----------|------|
| `backtest/data/fund_charts.json` | 2187 | 2185只≤20天，1只≤252天，1只≤500天 | 99.9%基金数据不足 |
| `data/fund_charts.json`（实盘） | 273 | 平均1240天，最小44最大4113 | 数据良好但与回测不一致 |
| `data/fund_cache/fund_chart_full_*.json` | 273 | 全量历史 | 仅覆盖自选基金 |

### 1.2 影响分析

- `score_momentum_backtest`：需≥20天数据，60天MA需≥60天 → 99.9%基金只得默认分2.5
- `score_quality_backtest`：需≥20天数据，120天收益需≥120天 → 99.9%基金只得默认分2.5
- Y5冠军策略回测结果（58.94%/年化16.84%）**可能不可靠**——大部分基金评分未实际计算

### 1.3 根因

1. `daily_live.py` L155 使用已失效的 `eastmoney_api` 获取新基金历史
2. 回测 `fund_charts.json` 的2187只基金只做了增量更新（page_size=20），从未拉全量历史
3. 回测和实盘使用不同的数据文件，维护成本高且容易不一致

---

## 二、设计方案

### 2.1 统一数据存储架构

#### 存储结构

```
data/fund_charts/                    # 单一数据源（回测+实盘共用）
├── {code}.json                      # [{xAxis: "2024-01-15", yAxis: 5.23}, ...]
├── {code}.json
└── ...

data/fund_charts_index.json          # 轻量索引（~400KB）
# {
#   "110020": {
#     "name": "易方达沪深300ETF联接A",
#     "first_date": "2013-05-20",
#     "last_date": "2026-07-21",
#     "count": 3120,
#     "last_update": "2026-07-21"
#   }
# }
```

#### 设计决策

- **yAxis 格式不变**：保持 `[{xAxis: "日期", yAxis: 累计收益率%}, ...]`，与回测引擎完全兼容
- **索引文件**：快速判断基金是否已有数据、数据是否过期，无需打开每个文件
- **并发安全**：每日增量更新只重写有变化的基金文件

#### 迁移策略

1. 把 `data/fund_charts.json`（273只好数据）+ `backtest/data/fund_charts.json`（2187只差数据）合并到 `data/fund_charts/` 目录，同基金取数据更多的版本
2. 旧文件标记为 `.bak`，确认无误后清理
3. 回测引擎加载方式从读单文件改为读目录

### 2.2 新增 `tools/chart_loader.py` — 统一数据加载模块

```python
def load_all_charts(charts_dir="data/fund_charts") -> dict:
    """加载目录下所有基金chart数据，返回 {code: [{xAxis, yAxis}, ...]}"""

def load_single_chart(code, charts_dir="data/fund_charts") -> list:
    """加载单只基金chart数据（实盘按需读取）"""

def update_chart(code, points, charts_dir="data/fund_charts") -> None:
    """更新单只基金chart数据 + 索引"""

def get_chart_index(charts_dir="data/fund_charts") -> dict:
    """读取索引文件，返回元数据"""
```

回测和实盘都通过此模块访问数据，确保一致性。

### 2.3 批量历史数据拉取

#### 数据源

JD API `getFundHistoryNetValuePageInfo`（已验证无需 Cookie，可在 GitHub Actions 上运行）

#### 拉取范围

| 来源 | 基金数 | 说明 |
|------|--------|------|
| 现有回测 charts | 2187 | 全部重拉全量历史 |
| 交易记录中缺失 | 63 | 在交易记录但不在 charts 中 |
| 全市场 Top 2000 | ~2000 | eastmoney `get_all_funds(sort_by="1n")` |
| 去重合并 | ~3500-4000 | 三来源去重 |

#### 拉取流程

```
1. 合并三来源基金代码列表 → 去重
2. 对每只基金：
   a. JD API 拉全量净值（pageSize=2000，翻页直到无数据）
   b. 转换为 chart 格式（yAxis = 累计收益率%）
   c. 写入 data/fund_charts/{code}.json
   d. 更新索引
3. 每50只保存一次索引（防中断丢失）
4. 输出统计：成功/失败/总天数分布
```

#### 关键参数

- 速率控制：每次请求间隔 0.15 秒
- 分页：每页 2000 条，最多 10 页（≈20000 条，覆盖任何基金完整历史）
- 断点续传：已存在的基金文件跳过（除非 `--force`）
- 容错：JD API 返回空数据 → 记录失败列表不中断；网络超时 → 重试2次

#### 时间估算

- 每只基金：0.5-2 秒（1-10页 × 0.15秒 + 写文件）
- 4000只 × 平均1秒 ≈ **约1小时**

#### 基金类型策略

扩展阶段**不过滤**基金类型——全量拉取所有类型（主动型、指数型、QDII、债券型等）。过滤在回测时通过 `fund_type_filter` 参数控制，用数据说话。

### 2.4 daily_live.py 修复

#### 核心修改

将 L155-172 的 eastmoney_api 调用替换为 JD API：

```python
# 替换前 (L155)
from tools.eastmoney_api import get_fund_nav_history

# 替换后
from tools.jd_finance_api import get_fund_chart_data
chart = get_fund_chart_data(code, full_history=True)
pts = chart.get("chart_points_full", [])
if pts:
    # 写入按基金拆分文件
    update_chart(code, pts)
    fund_charts[code] = pts
```

#### 同时修复

1. `fund_charts` 加载逻辑：从读单文件改为 `load_all_charts()`
2. 新基金发现流程：发现新代码 → JD API 拉全量历史 → 写入 per-fund 文件 → 更新索引 → 继续评分
3. 增量更新：`update_fund_charts.py` 已用 JD API，只需改输出路径到 `data/fund_charts/`

### 2.5 回测引擎适配

#### 改动范围

`backtest/engine/backtest.py` 只改数据加载方式，核心逻辑零改动：

```python
# 当前
fund_charts = json.loads(
    (PROJECT / "backtest" / "data" / "fund_charts.json").read_text("utf-8")
)

# 改为
from tools.chart_loader import load_all_charts
fund_charts = load_all_charts()
```

#### 调用点

- `backtest/engine/backtest.py` 主入口
- `scripts/daily_live.py` 数据加载
- `backtest/run_strategies.py` / `backtest/run_fast.py` 等回测脚本

#### 性能

加载 ~2000 只基金文件约 3-5 秒，对分钟级回测完全可接受。可选 `concurrent.futures` 并行加载优化。

### 2.6 数据准确性预检（回测前必须通过）

#### 检查清单

| 数据类型 | 文件 | 检查内容 | 缺失时处理 |
|----------|------|----------|-----------|
| 基金净值 | `fund_charts/{code}.json` | ≥252天数据 | JD API 拉全量 |
| 交易规则 | `trade_rules_{code}.json` | 申购费/赎回费/T+N/限额 | JD API `getFundTradeRulesPageInfo` |
| 基金档案 | `fund_profile_{code}.json` | 规模/类型/成立日 | JD API `getFundDetailProfilePageInfo` |
| 基金经理 | `fund_manager_{code}.json` | 任职年限/历史业绩 | JD API `getFundManagerDetailPageInfo` |
| 持仓分布 | `fund_holdings_{code}.json` | 资产配置/重仓股 | JD API `getFundInvestmentDistributionPageInfo` |

#### 预检脚本 `scripts/preflight_check.py`

扫描所有交易记录涉及的基金，检查上述5类数据是否完整。缺失则自动批量拉取。全部就绪后才允许回测。

### 2.7 移除评分默认值

#### 当前问题

`score_momentum_backtest` 和 `score_quality_backtest` 在数据不足时返回 `DimensionScore(score=2.5)`，掩盖数据缺失。

#### 修改方案

- 数据不足时返回 `DimensionScore(score=-1, weight=0, insufficient_data=True)`
- 总分计算时只用有数据的维度加权（权重重新归一化）
- 回测日志中明确报告："X只基金因数据不足被降权处理"
- 不再用默认值2.5填充——让数据缺失可见、可追踪

### 2.8 全策略回测

#### 回测范围

项目中所有已定义的策略，按轮次分组：

| 轮次 | 策略数 | 目录 | 说明 |
|------|--------|------|------|
| Round 1-4 | ~61 | `backtest/results_round1-4/` | 基础策略+风控变体 |
| Matrix 8 (AA-AE) | ~38 | `backtest/results_m8/` | 动态排名+共识深挖 |
| Matrix 9 (BA-BE) | ~46 | `backtest/results_m9/` | 信号深挖 |
| Y 系列 (Y1-Y8) | ~8 | 含 Y5 冠军 | 加权共识变体 |
| Z 系列 (Z1-Z5) | ~5 | 风控变体 | 熊市/仓位控制 |
| **合计** | **~158** | 全部重跑 | |

#### fund_type_filter 对比测试

每个策略额外跑3个变体：

| 变体 | 配置 | 目的 |
|------|------|------|
| `_active` | `fund_type_filter=active` | 旧策略配置（排除指数+QDII） |
| `_all` | `fund_type_filter=all` | 不排除 |
| `_no_filter` | 无 fund_type_filter | 纯数据驱动 |

#### 执行方式

- 创建 GitHub Actions workflow `backtest-full-revalidation.yml`
- 使用 matrix 策略并行执行
- 回测期间：2023-07-17 ~ 2026-07-17（3年，与Y5冠军一致）
- 结果输出到 `backtest/results_m10/`
- 自动生成对比排行榜

#### 成功标准

- 数据准确性预检 100% 通过
- 所有策略跑完无崩溃
- 五维评分有真实区分度（非所有基金都得相同分）
- 排行榜清晰展示哪个策略收益最高
- Y5 策略年化收益 ≥ 10%（合理门槛，不要求保持 58.94%）
- 最大回撤 ≤ 20%
- 如果 Y5 不再是最优 → 诚实报告，重新调参

---

## 三、实现顺序

```
Phase 1: 数据基础设施
  1. 创建 tools/chart_loader.py（统一加载模块）
  2. 迁移现有数据到 data/fund_charts/ 目录
  3. 修改回测引擎加载方式

Phase 2: 数据补全
  4. 创建 scripts/bulk_fetch_charts.py（批量拉取脚本）
  5. 运行批量拉取（~4000只基金全量历史）
  6. 创建 scripts/preflight_check.py（数据预检脚本）
  7. 运行预检，补全缺失的费率/经理/持仓数据

Phase 3: 评分修复
  8. 修改 score_momentum_backtest / score_quality_backtest 移除默认值
  9. 修改总分计算逻辑（权重归一化）

Phase 4: daily_live.py 修复
  10. 替换 eastmoney_api 为 JD API
  11. 修改数据加载/存储路径
  12. 测试新基金自动发现流程

Phase 5: 全策略回测
  13. 创建 GitHub Actions workflow
  14. 运行全策略回测
  15. 生成排行榜和分析报告
```

---

## 四、不在范围内

- 修改回测引擎核心逻辑（Portfolio、T+N、费率计算等）
- 修改大佬交易记录数据
- 修改 fund_name_map.json 映射
- 新增策略（只重跑已有策略）
- 前端 UI 改动

---

## 五、风险与缓解

| 风险 | 缓解 |
|------|------|
| JD API 有速率限制 | 0.15秒间隔 + 重试机制 |
| 部分基金已清盘，API返回空 | 记录失败列表，不影响其他基金 |
| 回测结果大幅下降 | 诚实报告，这是数据修复后的真实结果 |
| GitHub Actions 超时（6小时限制） | 分批执行，每批~50个策略 |
| per-fund 文件过多影响性能 | 索引文件 + 按需加载 |
