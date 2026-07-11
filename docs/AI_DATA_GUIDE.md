# AI 数据入口清单 (AI_DATA_GUIDE.md)

> 给 IDE (Claude Code / OpenCode) 中 AI 看的"数据地图"。
> 触发条件: 用户说"审计 / 看看 / 分析 / 跑 SKILL" 时, AI **必须先读此文档**。
> 然后按下面的"按 SKILL 入口"找具体数据。

## 全局数据

| 数据 | 路径 | 大小 | 用途 |
|------|------|------|------|
| SKILL 源 (29 个) | `skills/*.md` | ~150KB | 工作流定义 (用户写) |
| 机器日报 | `reports/sim/YYYY-MM-DD.md` | 5-20KB | 当日实盘推荐 + AI 审计入口 |
| 机器报告 (结构化) | `reports/sim/YYYY-MM-DD.json` | 10-50KB | 买入/卖出/拦截清单 |
| 实时状态 | `data/auto/status.json` | 500KB | 大佬持仓/交易/市场状态 |
| 实盘虚拟持仓 | `reports/sim/virtual_portfolio.json` | 5KB | 模拟持仓 + PnL |
| SKILL 依赖图 | `docs/SKILL_GRAPH.md` | ~5KB | 哪个 SKILL 调哪个 |

## 按 SKILL 入口

### `fund-monitor` (大佬持仓监控)
**数据**:
- `data/auto/status.json` → 当前所有大佬持仓快照
- `backtest/data/trading_by_date_fixed.json` → 按日聚合交易 (448 交易日)
- `backtest/data/trading_history_fixed.json` → 全部交易记录 (8856 条)
- 关注人列表: `tools/jd_finance_api.py: FOLLOWED_USERS` (11 人)
- 净值数据: `data/fund_charts_meta.json` (273 只) + `data/fund_charts/<code>.json` (每只独立)
- 名称映射: `data/fund_name_map.json` (433 条 name → code)
- 评分: `data/cache/scores.json` (30 只预计算)
- 排行: `data/cache/ranking.json` (271 只 sharpe/vol/回撤)

**API (实时)**:
- `python tools/jd_finance_api.py --batch-holdings` → 大佬持仓
- `python tools/jd_finance_api.py --trading-records <uid>` → 交易流水
- `python tools/jd_finance_api.py --save-snapshot` → 存快照

**输出**:
- 报告: `reports/大佬持仓监控/monitor-YYYYMMDD.md`

---

### `fund-checklist` (买入前六关)
**数据** (按代码):
- `data/fund_cache/fund_profile_<code>.json` — 基金档案
- `data/fund_cache/fund_perf_<code>.json` — 业绩
- `data/fund_cache/fund_holdings_<code>.json` — 持仓分布
- `data/fund_cache/trade_rules_<code>.json` — 交易规则
- `data/fund_cache/fund_manager_<code>.json` — 基金经理
- `data/fund_cache/fund_notices_<code>.json` — 公告
- `data/fund_charts/<code>.json` — 净值曲线 (用于 RSI/择时)
- `data/cache/scores.json` — 评分结果

**API**:
- `python tools/jd_finance_api.py --fund-profile <code>`
- `python tools/jd_finance_api.py --fund-perf <code>`
- `python tools/jd_finance_api.py --fund-holdings <code>`
- `python tools/jd_finance_api.py --trade-rules <code>`
- `python tools/jd_finance_api.py --fund-manager <code>`
- `python tools/jd_finance_api.py --fund-notices <code>`

**输出**:
- 报告: `reports/{基金名}/fund-checklist-YYYYMMDD.md`
- 买入记录 (YAML frontmatter): 同上, 供 fund-sell 读取

---

### `fund-sell` (卖出决策)
**数据**:
- 持仓: `reports/sim/virtual_portfolio.json` (虚拟) 或 用户提供的真实持仓
- 买入记录: `reports/{基金名}/fund-checklist-YYYYMMDD.md` (YAML frontmatter)
- 量化信号: `python tools/fund_rules.py --analyze <code>`
- 缓存: `data/trading_records_cache.json`, `data/holdings_diff_cache.json`
- 状态: `data/auto/status.json`

**API**:
- `python tools/jd_finance_api.py --my-holdings`
- `python tools/jd_finance_api.py --holdings <uid>`

**输出**:
- 报告: `reports/卖出建议/sell-YYYYMMDD-{frequency}.md`

---

### `fund-penetration` (穿透持仓)
**数据**:
- 基金持仓: `data/fund_cache/fund_holdings_<code>.json`
- 重仓股市值: 需在线查 (`getStockQuotes`)
- 行业估值: `data/industry_valuation.json` (来自 `getIndexBlockInfo`)

**API**:
- `python tools/jd_finance_api.py --fund-holdings <code>` (拉最新)
- `python tools/jd_finance_api.py --stock-quotes <code1,code2>`

---

### `fund-analyze` (综合分析)
**数据**: 同 fund-checklist + fund-penetration
- 也读 `data/cache/scores.json` (评分引擎结果)

---

### `fund-compare` / `fund-debate`
**数据**:
- 多只基金: 并发读 `data/fund_cache/*_<code>.json`
- 净值对比: `data/fund_charts/<code>.json` (取最近 90 天)

---

### `fund-scan` (全市场扫描)
**数据**:
- 排行: `data/cache/ranking.json` (271 只预计算)
- 官方精选: `data/fund_cache/featured_rankings_main.json` (26 榜 TOP20, 由 `get_featured_rankings` 生成)
- 名称映射: `data/fund_name_map.json`

**API**:
- `python tools/jd_finance_api.py --featured-rankings` (京东官方 26 榜)

---

### `industry-funnel` / `industry-research`
**数据**:
- 行业估值: `data/industry_valuation.json` (PE/PB 百分位 + 10 年历史)
- 三维共振: `signal_score` (0-100)
- 行业指数: `python tools/jd_finance_api.py --index-detail <code>`

---

### `news-pulse` (新闻快讯)
**数据**:
- `data/fund_cache/daily_news_main.json` (基金报/财联社/格隆汇 资讯)

**API**:
- `python tools/jd_finance_api.py --daily-news` (实时)

---

### `earnings-review` / `earnings-team` (财报)
**数据**:
- 季度业绩: 在线查 (`getFundHistoryProfitPageInfo`)
- 财务三表: `python tools/jd_finance_api.py --fund-detail-pin <code>` (含完整数据)

---

### `portfolio-review` (组合复盘)
**数据**:
- 虚拟持仓: `reports/sim/virtual_portfolio.json`
- 实际持仓: 用户提供 / `data/jd_auth/` cookies 拉自选
- 交易历史: `data/auto/status.json`

---

## 数据新鲜度标记

| 数据 | 新鲜度 | 检查方法 |
|------|--------|----------|
| 净值 (fund_charts) | 1 天 | `last_date` 字段 |
| 持仓快照 | 1 天 | 文件 mtime |
| 交易流水 | 1 天 | 文件 mtime |
| 公告 (notices) | 7 天 | 文件 mtime (公告不会每天变) |
| 评分 (scores) | 1 天 | 文件 mtime |
| 排行 (ranking) | 1 天 | 文件 mtime |
| 行业估值 | 1 天 | 文件 mtime |
| 新闻 | 1 天 | 文件 mtime |

> **数据陈旧警告**: 如果 mtime > 7 天, AI 必须在 SKILL 输出里标注"⚠️ 数据陈旧, 结论仅供参考"。

---

## 数据获取的 3 种方式 (按优先级)

1. **读预计算缓存** (最快, 50-200ms)
   - `data/cache/*.json` — daily_live.py 每天 14:30 生成
   - `data/fund_cache/*_<code>.json` — jd_finance_api.py 拉过即存

2. **调 jd_finance_api 拉新** (中速, 1-5s)
   - 所有数据都可现拉, 但需要 cookie (offline 时返回 None)

3. **fallback** (兜底)
   - 数据不全时, 用同类基金的近似值
   - 必须明确标注"估算值, 非精确"

---

## AI 工作流模板 (给 IDE AI 复制用)

```markdown
你是 AI 投研助手。用户给了 {SKILL} + {ARGUMENTS}。请按以下流程:

1. **读入口**: `docs/AI_DATA_GUIDE.md` (这个文件)
2. **找数据**: 按 "{SKILL}" 章节列出的文件路径读取 (优先缓存)
3. **执行 SKILL**: 按 `skills/{SKILL}.md` 的步骤
4. **数据陈旧检查**: mtime > 7 天要警告
5. **输出报告**: 保存到 `reports/{SKILL}/{YYYYMMDD}.md`
6. **不确定性标注**: 标 "⚠️" + 原因 (数据缺失/评分边界/信号冲突)
```
