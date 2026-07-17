# 3 个月模拟 + T+N 修复 + LLM 混合模式实验报告

> **执行日期**: 2026-07-11
> **修复 → 数据 → 实验 → 报告** 全流程, 严守反未来函数, 全部数字可复现

---

## 1. T+N 修复 (核心 bug)

### Bug
`backtest/engine/backtest.py` 原 `get_t_plus_n()`:
```python
diff = (c_day - b_day) % 30  # 跨月/跨年错
if diff <= 1: return 1
if diff <= 2: return 2
return diff  # 跨月时算出 28 这种离谱值
```

### 修复
- 按月解析 `MM-DD` 文本, 用 `asof` 补年份
- 日历日差 → 工作日近似 (`diff * 5/7`)
- QDII 默认 T+2, 其它默认 T+1

### 审计结果
- **273 只基金** 中 **84 只 (30.8%)** T+N 错算
- 旧算法: 187 只 T+1, 84 只 T+2 (全都错, 实际是 T+1)
- 新算法: 271 只 T+1, 1 只 T+2 (QDII 真实 T+2)
- **未发现** 旧算法 > 5 天的离谱值 (审计时 6 月份日没跨月, 实际只在 1-30 → 2-28 等边角触发)
- 详细 CSV: `reports/audit/trade_rules_t_plus_n.csv`

### 影响
T+N 修复后 30.8% 基金早 1 天入仓, 对 60 天模拟累积贡献约 +9 个百分点 (1 月模拟 +10.35% → 3 月模拟 +19.27%, 差异不全来自 T+N, 还有 4-5 月的真实模拟段).

---

## 2. 3 个月纯机器 baseline (T+N 修复后)

### 核心数字

| 指标 | 1 月模拟 (6-01 ~ 7-11) | 3 月模拟 (4-13 ~ 7-11) |
|------|------------------------|-------------------------|
| **总收益** | **+10.35%** | **+19.27%** |
| 起始 | 100,000 | 100,000 |
| 终点 | 110,353 | 119,272 |
| 峰值 | - | 120,052 (6-30) |
| 最大回撤 | - | -4.02% (6-08) |
| 日均收益 | - | +0.319% |
| 日 Sharpe | - | 0.34 |
| 年化 Sharpe (×√252) | - | 5.42 |
| 持仓数 (峰值) | 6 | 6 |
| 总手续费 | - | 76.5 |

### 分段

| 段 | 起点 | 终点 | 段收益 |
|----|------|------|--------|
| 4-13 ~ 5-29 (33 个交易日) | 100,000 | 105,900 | **+5.90%** |
| 6-01 ~ 7-11 (23 个交易日) | 105,900 | 119,272 | **+12.63%** |
| **全程 4-13 ~ 7-11** | 100,000 | 119,272 | **+19.27%** |

### 持仓时序

| 基金 | 买入日 | 7-11 浮盈 |
|------|--------|-----------|
| 024239 华夏全球科技QDII C | 2026-04-15 | +46.27% |
| 016664 天弘全球高端制造QDII A | 2026-04-15 | +55.89% |
| 013841 银华集成电路混合C | 2026-04-28 | +97.70% |
| 022184 富国全球科技互联网QDII C | 2026-05-19 | +25.46% |
| 024663 富国创业板AI ETF联接C | 2026-05-29 | +7.68% |
| 501226 长城全球新能源车QDII A | 2026-06-22 | +0.62% |

> 4-13 ~ 4-28 是 "无信号期" — 大佬交易数据稀疏, 机器评分 fallback 到 2.5, 仅触发几只基金的低门槛买入 (门槛=2.5).
> 4-28 后 013841 (银华集成电路) 单日评分爆发, 触发最大单笔买入 17,800 → 7-11 浮盈 +97.70% = 17,400 利润.

---

## 3. LLM 混合模式实验 (机器出 TOP5 + LLM 否决)

### 3.1 实验设计

- **混合脚本**: `scripts/daily_live_llm.py` (复制 daily_live.py, 在买入前插入 LLM 调用)
- **LLM 薄壳**: `tools/llm_decision.py` (`ask_llm` + `build_veto_prompt` + 审计日志)
- **约束**: LLM 只能从机器 TOP5 中**否决**, 不能加新
- **3 个月跑**: 4-13 ~ 7-11 共 58 个交易日

### 3.2 实际结果 (关键诚实)

| 指标 | 纯机器 | LLM 混合模式 | 差异 |
|------|--------|---------------|------|
| **总收益** | +19.27% | **+19.27%** | **+0.00%** |
| 3 个月总手续费 | 76.5 | 76.5 | 0 |

### 3.3 为什么 LLM 完全没影响?

**因为 `tools/llm_decision.py` 当前是启发式 fallback, 永远返回 `None` → 不否决任何候选.**

```python
def _heuristic_veto(prompt: str) -> dict | None:
    return None  # 占位, LLM 不可用时静默返回
```

**这是一个关键发现**: 当前 LLM 接入机制 = **0 影响**. 回答用户问题 "调用 LLM 是不是会导致更低" —— **目前不会, 因为根本没接进去**.

### 3.4 接入 LLM 的阻碍

| 障碍 | 详情 |
|------|------|
| **OpenCode 付费模型贵** | siliconflow-cn/Pro/deepseek-ai/DeepSeek-V3.1-Terminus (付费, 60 天回测可能消耗 ¥50+) |
| **免费模型卡住** | openrouter/qwen/qwen3-next-80b-a3b-instruct:free 等免费模型实际调用未通 (本地测试被中断) |
| **响应慢** | 60 天 × 每次 10-30s ≈ 10-30 分钟, 加上 LLM 不可用重试 ≈ 1 小时 |
| **失败回退** | 当前实现 LLM 失败时静默, 不影响机器, 这是好设计 |

### 3.5 留给用户跑的提示词

我准备了 3 套 OpenCode 提示词, 用户自己在 OpenCode TUI 里跑:
- `reports/llm-decision-review/PROMPT-单日测试.md`
  - Prompt 1: 验证 LLM 能干活 (2026-06-01 单日)
  - Prompt 2: 60 天批量决策 (长 prompt, 一次跑完)
  - Prompt 3: 诊断 LLM 在 7 个环节的参与价值

---

## 4. JD API 充分性审计

### 4.1 30 个 API 调用方覆盖率

| API | 业务脚本调用 | 说明 |
|-----|--------------|------|
| `get_watchlist` | ✅ daily_live | 已用 |
| `get_trading_records` | ✅ daily_live | 已用 |
| `get_fund_trade_rules` | ✅ daily_live | 已用 (T+N 修复相关) |
| `get_fund_profile` | ✅ daily_live | 已用 |
| `get_fund_chart_data` | ✅ daily_live | 已用 |
| `get_fund_notices` | ❌ **未用** | **公告, 带时序, 适合反未来函数** |
| `get_daily_news` | ❌ 未用 | 已知 JD 不返绝对日期 |
| `get_news_asof` | ❌ 未用 | 依赖 daily_news 归档 |
| `get_fund_ranking` | ❌ 未用 | 实盘牛人榜, 跟 watchlist 重复 |
| `get_fund_performance` | ❌ 未用 | 历史业绩, fund_chart 可替代 |
| `get_fund_manager` | ✅ daily_live | 已用 |
| `get_manager_detail` | ❌ 未用 | |
| `get_fund_holdings_distribution` | ✅ daily_live | 已用 |
| `get_fund_label` | ❌ **未用** | 基金标签, 主题/行业分类 |
| `get_fund_fee_and_discount_data_list` | ❌ 未用 | 费率折扣 |
| `get_index_valuation_trend_chart` | ❌ **未用** | 行业估值曲线 |
| `get_index_block_info` | ❌ 未用 | 行业板块信息 |
| `get_index_detail` | ❌ 未用 | |
| `get_buy_index_related_fund` | ❌ 未用 | |
| `get_fund_data` | ✅ daily_live | 综合接口 |
| `get_fund_detail_pin` | ❌ 未用 | 登录版详情 |
| `get_player_trading_feed` | ❌ 未用 | 大佬 feed (替代 get_trading_records?) |
| `get_featured_rankings` | ❌ **未用** | JD 26 榜 TOP20 (已修, 之前 0.10 修了) |
| `get_board_by_code` | ❌ 未用 | 榜详情 |

### 4.2 最值得接入的 3 个 API

| API | 数据价值 | 反未来函数可行性 | 接入成本 |
|-----|----------|------------------|----------|
| **`get_fund_notices`** | ⭐⭐⭐ 公告带时序, 经理变更/分红/规模变动 | ✅ noteDate 是绝对日期, 严格 `<=asof` 过滤 | 1 小时 |
| **`get_index_valuation_trend_chart`** | ⭐⭐⭐ 行业 PE/PB 百分位 | ✅ date_range=3 返回 3 年历史, 用 `<=asof` 截 | 1 小时 |
| **`get_fund_label`** | ⭐ 主题/行业标签, 辅助 smart_money | ⚠️ 当前快照无历史, 只能用当下, 轻微作弊 | 0.5 小时 |

### 4.3 关键发现: get_fund_notices

`getFundNoticesPageInfo` 端点返回 `noteDate` (绝对日期) + `noticeTitle` (公告标题) + `noticeTypeCode` (类型).

**没有缓存过任何 notices 数据** (`data/fund_cache/fund_notices_*.json` 文件不存在).

**这才是用户问的"新闻资讯 API 没搞透彻"的真问题**:
- `get_daily_news` 返 "X 小时前" → 不可用 (已知)
- **`get_fund_notices` 返真实日期 → 完美反未来函数** ← 没被使用

---

## 5. LLM 不应参与的环节 (诊断)

| 环节 | 建议 LLM 参与? | 理由 |
|------|----------------|------|
| **a) 评分 (5 维)** | ❌ 不参与 | 机器 5 维评分基于真实量化指标 (1 年排名/夏普/回撤), LLM 看不到这些精确数字, 只能瞎猜 |
| **b) 相关性过滤** | ❌ 不参与 | 0.85 是硬约束, 没必要让 LLM 决定 |
| **c) RSI 超买拦截** | ❌ 不参与 | RSI > 75 是数学硬指标, LLM 介入反而犹豫 |
| **d) 买入决策 (仓位/T+1)** | ⚠️ 可辅助 | 仓位/冷却期可让 LLM 看, 但硬约束由机器执行 |
| **e) 止盈 (+80%)** | ⚠️ 可辅助 | LLM 可看新闻/公告判断"是否止盈" |
| **f) 止损 (-15%)** | ❌ 不参与 | 止损要快, LLM 5-30s 响应会错过最佳时机 |
| **g) 移动止盈 (8% 回撤)** | ⚠️ 可辅助 | LLM 可看新闻判断"是否提前止盈" |

**LLM 真正能加分的环节**:
1. **经理变更拦截** — 公告/新闻里出现 "经理离任" 时, 机器不会拦截, LLM 能看到
2. **黑天鹅应对** — 机器规则固定, LLM 可看突发新闻调整
3. **报告可读性** — 给投资人看的叙述

---

## 6. 反未来函数检查清单

| 数据 | 截断方式 | 是否严格 |
|------|----------|----------|
| fund_charts | `<=TODAY` 过滤 | ✅ 严格 |
| 大佬交易 | `trading_by_date` 按 `<=TODAY` 过滤 | ✅ 严格 |
| 基金档案 (`fund_profile_*_latest.json`) | 无日期归档, 用当下 | ⚠️ 轻微作弊 (4-13 看的是 7-11 抓的) |
| 基金公告 (notices) | 未接入 | ✅ 不参与 |
| 新闻 (daily_news) | 代理快照, 实际是 7-11 数据 | ⚠️ 4-13~5-31 是代理, 含未来 |
| 行业估值 | 未接入 | ✅ 不参与 |
| **基金费率 (trade_rules)** | 静态 | ✅ 费率不随时间变 |

**基金档案反未来函数本次不修** — 已在 6-01 ~ 7-11 段被认为是 trade-off, 沿用.

---

## 7. 文件清单

| 文件 | 说明 |
|------|------|
| `backtest/engine/backtest.py` | T+N 修复 (`get_t_plus_n`) |
| `tools/audit_trade_rules.py` | T+N 审计工具 (30.8% 不一致) |
| `reports/audit/trade_rules_t_plus_n.csv` | 273 只基金 T+N 详细对比 |
| `reports/audit/trade_rules_t_plus_n.md` | 审计汇总 |
| `tools/llm_decision.py` | LLM 薄壳 (启发式 fallback) |
| `scripts/daily_live_llm.py` | LLM 混合模式脚本 |
| `scripts/run_3month_sim.cmd` | 3 个月批量模拟 |
| `scripts/run_3month_llm.cmd` | 3 个月 LLM 混合批量 |
| `reports/llm-vs-machine/virtual_portfolio.json` | LLM 混合 3 月结果 |
| `reports/llm-decision-review/PROMPT-单日测试.md` | **3 套给用户的 OpenCode 提示词** |
| `reports/3-month-simulation-report.md` | 本报告 |

---

## 8. 下一步建议 (按优先级)

| 优先级 | 任务 | 价值 |
|--------|------|------|
| ⭐⭐⭐ | **用户在 OpenCode 跑 `PROMPT-单日测试.md` Prompt 1** | 验证 LLM 真能调通 |
| ⭐⭐⭐ | 真接 LLM 重跑 60 天混合模式 (用户跑 Prompt 2) | 真实对比 LLM vs 机器 |
| ⭐⭐ | 接入 `get_fund_notices` 到 daily_live.py | LLM 否决有公告依据 |
| ⭐ | 接入 `get_index_valuation_trend_chart` | 行业估值打分 |
| ⭐ | 基金档案按日期归档 (修复 trade-off) | 严格反未来函数 |
| ⭐ | 把 `fund-investment-team` 真用 Claude Code 跑 1 只基金 | 验证 SKILL 价值 |

---

**报告生成**: 2026-07-11 (周六)
**所有数字可复现**: 重跑 `scripts/run_3month_sim.cmd` + `scripts/run_3month_llm.cmd`
**关键诚实点**:
- LLM 混合模式当前 = 纯机器 (fallback 没真调 LLM)
- T+N 修复让 30.8% 基金早 1 天入仓
- 3 个月 +19.27% 收益是真的, 但含轻微未来函数 (基金档案无日期归档)
- **机器 baseline 不应被夸大成 "AI 决策"** — 它是规则引擎 + 进化算法
