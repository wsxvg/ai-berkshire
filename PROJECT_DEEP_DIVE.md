# 基金/股票智能投研系统 — 项目深度文档 (PROJECT_DEEP_DIVE)

> **目的**: 让任何 IDE AI（包括后续会话）**不需要**重新读项目每个文件，10 分钟内掌握全貌。
>
> **最后整理**: 2026-07-12
>
> **配套**:
> - `CODEBUDDY.md` (根目录) — CodeBuddy 简版
> - `CLAUDE.md` — Claude Code 简版
> - `AGENTS.md` — Codex 简版
> - `docs/AI_DATA_GUIDE.md` — 数据地图（必读）

---

## 一句话定位

**这是一个「四大师价值投资框架 + 京东金融数据 + 五维评分 + 严格回测 + SKILL 工作流」双轨制场外基金 & 美港 A 股投研系统**。代码图谱（`codegraph status`）显示：**190 文件 / 2,142 节点 / 4,216 边**。整体规模庞大但**架构已收敛**：回测引擎 + 五维评分 + 京东 API 三件套为心脏，30 个 SKILL 为四肢，2329 份报告为肌肉记忆。

---

## 一、目录全图（30 秒看完）

```
c:/项目/A基金/基金/
├── run.py                       # 一键监控入口（你的实盘持仓 + 11 大佬）
├── CLAUDE.md / AGENTS.md / CODEBUDDY.md  # IDE 集成文档
├── GOAL.md                      # 总体目标
├── K_STRATEGY_FINAL_REPORT.md   # 12 策略对比 + K 系变体结论
├── STRATEGY_FINAL_REPORT.md     # 动量/过夜/12 策略 三榜综述
│
├── skills/                      # 【30 个 SKILL】投研工作流（用户写）
│   ├── fund-*.md (13 个)        # 基金类
│   ├── investment-*.md (4 个)   # 股票深度
│   ├── earnings-*.md (2 个)     # 财报
│   ├── industry-*.md (2 个)     # 行业
│   ├── management-*.md (1 个)   # 管理层
│   ├── portfolio-*.md (1 个)    # 组合
│   ├── *.md (7 个辅助)          # bottleneck/dyp-ask/quality/news/private/thesis/wechat
│
├── codex-skills/                # 同样的 30 个 SKILL，codex 格式
├── codex-prompts/               # 同样的 30 个 prompt 入口
├── opencode-skills/             # 同样的 30 个 SKILL，opencode 格式
│   ▲ 三者由 scripts/sync-*.py 从 skills/ 同步
│
├── specs/                       # 【14 个模块设计文档】
│   ├── 00-architecture-overview.md  # 6 层架构总览
│   ├── 01-data-layer.md ~ 12-skills-integration.md  # P1-P12 设计
│   └── 90-reference-patterns.md     # 4 个参考项目可复用模式
│
├── docs/                        # 【22 个设计/审计/Roadmap 文档】
│   ├── AI_DATA_GUIDE.md         # 【最常被读】数据地图
│   ├── AI_AUDIT_PROMPT.md       # AI 投研开局 Prompt 模板
│   ├── AI_META_PROMPT.md        # 一句话调度多 SKILL
│   ├── AI_ACTIVE_AUDIT_GUIDE.md # AI 主动审计指南
│   ├── project-summary-for-codebuddy.md  # 项目结构摘要（已存在）
│   ├── demo.md                  # 【21KB】JD 金融 API 完整文档
│   ├── 回测对齐方案.md / 回测最终报告.md
│   ├── 评分反模式.md / 自主决策系统设计-v1.md
│   ├── ROADMAP.md / SKILL_GRAPH.md
│   ├── v2改进设计方案.md / improvement_plan_v2.md
│   ├── reference_projects_*.md  # 4 个参考项目分析
│   ├── 场外基金分析改进规划.md
│   ├── 基金场景下的AI-Berkshire适配分析.md
│   └── 大模型的下一战：多模态是必然还是过热的叙事.md
│
├── tools/                       # 【125 个 Python 文件】核心库
│   ├── jd_finance_api.py        # 【75K/2876 行】42 个 JD API 封装（心脏）
│   ├── fund_scorer.py           # 【40K/1105 行】五维评分（心脏）
│   ├── fund_rules.py            # 【10K/237 行】规则引擎（买卖信号量化）
│   ├── fund_planner.py          # 【6K/165 行】Kelly 仓位分配
│   ├── technical_indicators.py  # 【12K/376 行】RSI/MACD/布林带/均值回归
│   ├── ml_signal.py             # 【8K/217 行】LightGBM 增强信号
│   ├── xiaobeiyangji_api.py     # 小倍养基 API（摆动信号/热度）
│   ├── decision_engine.py       # 5 步决策引擎
│   ├── master_analysis.py       # 综合分析入口
│   ├── daily_report.py          # 机器日报生成
│   ├── build_*.py               # 缓存构建（ranking/scores/notices）
│   ├── expand_charts_jd.py      # 基金净值扩展（fund_charts_extended）
│   ├── *_experiments.py         # 大量实验脚本（exp_1y_*.py / _test_E2_*.py）
│   ├── _diag_*.py / _check_*.py # 诊断脚本（30+ 个）
│   ├── data_provider/           # 数据层抽象（factory/jd_finance_provider）
│   ├── rag/                     # 向量库
│   ├── memory/                  # 基金记忆
│   └── ......... 等等
│
├── scripts/                     # 【27 个脚本】自动管道
│   ├── auto-pipeline.py         # 【107KB】每日 14:30 自动抓数据+评分+报告
│   ├── daily_live.py            # 每日实盘模拟（GitHub Actions 14:30）
│   ├── validate_backtest.py     # 回测稳健性验证
│   ├── build_fund_name_map.py   # 基金名→代码映射补全
│   ├── generate_report.py       # 生成深度 checklist
│   ├── generate_html.py         # HTML 报告
│   ├── optimize_backtest.py / phase4_optimize.py / phase5_extreme.py  # 优化
│   ├── pipeline/                # 10 个 task 拆分的 pipeline（auth/holdings/trading/scoring/ai_analysis）
│   ├── sync-*.py                # SKILL 同步（codex/opencode/prompts）
│   └── install-*.sh             # 各 IDE 的安装脚本
│
├── backtest/                    # 【回测引擎 + 数据】
│   ├── engine/backtest.py       # 【100K/2250 行】核心回测引擎
│   ├── run.py / run_strategies.py  # 入口
│   ├── auto_optimize.py         # 4 阶段寻优
│   ├── analyze_big_players.py   # 大佬历史表现分析
│   ├── data/
│   │   ├── trading_history_fixed.json   # 8856 笔大佬交易
│   │   ├── trading_by_date_fixed.json   # 448 个交易日聚合
│   │   ├── fund_charts.json            # 273 只基金净值（基础 1 年）
│   │   ├── fund_charts_extended.json   # 扩展（部分 8 年）
│   │   └── fetch_historical.py         # 数据拉取
│   └── reports/                 # 28 份回测结果（strategy_comparison 等）
│
├── tests/                       # 【7 个测试文件】覆盖率 80%+
│   ├── test_fund_scorer.py      # 40 tests
│   ├── test_fund_rules.py       # 16 tests
│   ├── test_financial_rigor.py  # 18 tests
│   ├── test_backtest_integrity.py
│   ├── test_data_provider.py
│   ├── test_decision_engine.py
│   └── test_pipeline.py
│
├── data/                        # 【1967 文件，5MB+】
│   ├── jd_auth/cookies.json     # 京东金融登录态
│   ├── fund_cache/              # 【1616 个】基金详情/profile/rules/manager/holdings/notices
│   ├── fund_charts/             # 【273 个】每只基金独立净值曲线
│   ├── fund_snapshots/          # 持仓快照历史
│   ├── auto/status.json         # 实时状态（500KB）
│   ├── cache/                   # 预计算（ranking.json 51KB / scores.json）
│   ├── evolution/best_config.json  # 进化最优参数
│   ├── api_cache/  eastmoney/  scan/  memory/  monitor/  rag/
│   ├── holdings_snapshot_2026-07-0[1-9].json  # 每日持仓快照
│   ├── trading_records_YYYY-MM-DD.json         # 每日交易记录
│   ├── fund_charts.json / fund_charts_extended.json  # 汇总
│   ├── fund_name_map.json       # 433 条名称→代码映射
│   ├── industry_valuation.json  # 行业 PE 百分位
│   ├── strategy_D_config.json   # D 策略核心-卫星配置
│   ├── long_term_backtest_results.json  # 长期回测
│   ├── fundamentals.json        # NVDA/AMD/MU 财务
│   ├── watchlist.json
│   └── ranking_users.json / ranking_top10.json / dynamic_users.json
│
├── reports/                     # 【2329 份】报告（MD/JSON/HTML）
│   ├── auto/                    # 20 个 daily-YYYY-MM-DD.md + backtest_blended.json
│   ├── sim/                     # 115 个 2026-MM-DD.md/.json（实盘模拟）
│   ├── 大佬持仓监控/             # 每日 monitor
│   ├── llm-decision-review/     # 11 个 LLM 决策审计
│   ├── bottleneck-map/          # 4 个产业链瓶颈（master-map.md 259KB）
│   ├── fund-checklist/          # 0 个（待生成）
│   ├── 港股召回池/  美股召回池/  科创板召回池/  # 召回池
│   ├── 港股/ 美股/ A股/ 港股/ 美股/  美股/  # 公司研究
│   ├── 拼多多/  美团/  茅台/  腾讯/  阿里巴巴/  网易/  ...
│   ├── 《看懂XX》/               # 6 家长篇深度系列（百度/网易/美团/茅台/腾讯/英伟达/...)
│   ├── AI产业研究/  阿里云/ AI算力/  # AI 相关
│   └── portfolio-latest.md      # 组合报告（根目录）
│
├── skills/  codex-skills/  codex-prompts/  opencode-skills/  # SKILL 四端同源
│
├── 筛选公司/                    # 21 个 A 股筛选报告
│   ├── A股召回池/               # 12 行业
│   ├── 科创板股召回池/          # 4 报告
│   └── 一流公司-巴菲特持仓/ 好公司-去劣指标全通过/ ...
│
├── 实盘记录/                    # 3 个实盘笔记（PDD/美团 镜子测试）
├── 养基宝/                      # Playwright MCP 抓包缓存
├── assets/                      # 13 个图片/mmd
├── logs/                        # 3 个日志
│
├── reference_projects/          # 4 个参考项目（tradingagents / daily-stock-analysis 等）
└── fund-ui/                     # 【26277 文件】前端 UI（独立项目，不要改）
```

---

## 二、核心架构（一图流）

```
┌─────────────────────────────────────────────────────────────┐
│  Layer 6: SKILL 交互层（30 个 .md，用户在 IDE 触发）       │
│  fund-monitor / fund-checklist / fund-sell / investment-...│
│  ⬇ AI 读 docs/AI_DATA_GUIDE.md 找数据位置                  │
├─────────────────────────────────────────────────────────────┤
│  Layer 5: Pipeline 编排（Python）                           │
│  scripts/auto-pipeline.py (107K) + scripts/daily_live.py   │
│  scripts/pipeline/ (10 个 task) + scripts/generate_report  │
├─────────────────────────────────────────────────────────────┤
│  Layer 4: 决策引擎（Python）                                │
│  tools/decision_engine.py (5 步: Rules→Scoring→Risk→...)    │
│  tools/master_analysis.py (综合入口)                        │
├─────────────────────────────────────────────────────────────┤
│  Layer 3: 评分 + 规则 + 信号（Python）                     │
│  tools/fund_scorer.py (五维评分)                            │
│  tools/fund_rules.py (规则引擎: 清仓/护盾/止盈/调仓)        │
│  tools/technical_indicators.py (RSI/MACD/布林带)            │
│  tools/ml_signal.py (LightGBM walk-forward)                 │
├─────────────────────────────────────────────────────────────┤
│  Layer 2: 数据层 + RAG（Python）                           │
│  tools/data_provider/ (factory + 标准化 models)             │
│  tools/rag/vector_store.py (chromadb)                       │
│  tools/memory/fund_memory.py                                │
├─────────────────────────────────────────────────────────────┤
│  Layer 1: 基础设施（Python）                                │
│  tools/jd_finance_api.py (42 个 JD API 封装)                │
│  backtest/engine/backtest.py (回测引擎)                     │
│  tools/event_bus.py (blinker)                               │
└─────────────────────────────────────────────────────────────┘
```

**数据流闭环**:
```
京东金融 API ──┐
              ├──> data/fund_cache + data/auto/status.json
小倍养基 API ─┤                       │
              │                       ▼
eastmoney ────┘           scripts/auto-pipeline.py / daily_live.py
                              │ (每日 14:30 GitHub Actions)
                              ▼
              五维评分 + 规则引擎 + 技术指标 + ML 信号
                              │
                              ▼
              tools/decision_engine.py → 5 步决策
                              │
                              ├──> reports/auto/daily-YYYY-MM-DD.md (机器日报)
                              ├──> reports/sim/YYYY-MM-DD.md (实盘模拟)
                              └──> AI 审计入口（人开 IDE 触发 SKILL）
```

**回测闭环**:
```
backtest/data/trading_by_date_fixed.json (448 天大佬交易)
backtest/data/fund_charts.json (273 只基金净值)
backtest/data/fund_cache/*_*.json (费率/经理/持仓)
                            │
                            ▼
              backtest/engine/backtest.py: run_backtest()
              ── 每日循环：检测市场状态 → 评分 → 仓位管理 → T+N
                            │
                            ▼
              backtest/reports/strategy_comparison_v2.json
              K_STRATEGY_FINAL_REPORT.md / STRATEGY_FINAL_REPORT.md
```

---

## 三、关键模块深度说明

### 3.1 `tools/jd_finance_api.py` — 京东金融 API (75KB/2876 行)

**42 个 API 封装**，零外部依赖（纯 stdlib + 可选 playwright）。

**核心接口**:
- `get_fund_detail(code)` L805 — 单次调用聚合 profile/perf/holdings/manager/chart
- `get_user_fund_holding_info(target_uid)` L444 — 大佬持仓 + 期间收益率
- `get_trading_records(target_uid, max_pages, size)` L499 — 大佬交易分页（**API 1000 笔硬限**）
- `batch_get_fund_data(fund_codes)` L339 — 多基金并发（ThreadPoolExecutor）
- `get_fund_detail_pin(fund_code)` L1817 — 登录态详情含 Sharpe/回撤
- `get_index_block_info` L1733 / `get_watchlist` L2012 / `get_player_trading_feed` L2080
- `get_featured_rankings()` L2052 — 京东官方 26 榜 TOP20（用 `queryFullRanking` 端点，**实测可工作**）

**关键常量**:
- `FOLLOWED_USERS` — 11 个大佬 numeric_id 字典
  - 蓝鲸跃财 3546208 / Z 先生 14345330 / 王晴阳 16020895 / 黑夜银翼 2690580
  - 南山隐士 4063754 / 赚自己钱 3642504 / 晴空万里 3748946 / 小猫爱黄金 10458335
  - 家庭温暖 11979538 / 西西金算盘 4968958 / 招财小猫 11953905
- `_api_form` / `_api_post` — 通用 HTTP 调用（L100-180）
- `_ensure_cookies` — Cookie 加载/刷新（fan-in=17，被到处调）
- `_auto_login_with_playwright` L134 — 自动登录（可选）

**API 已知限制**（重要）:
- `get_trading_records` **单用户 1000 笔硬限** → 11 大佬 28 月窗口
- `getFundHistoryNetValuePageInfo` pageSize=2000 → 翻 3 页可拉 17 年沪深 300
- `getFollowUpdateCount` 返回 followUpdateCount 数字，但**不给用户列表**（关键缺口）
- 牛人榜 `queryFundFirmOfferMultiRank` 用 base64 pin（如 `IaQ-n2FA0j4yqOBFxX_jkg`），**和老 numeric_id 不同体系**
- IP 风控：连续 max_pages=10+ 触发，需 60-180 秒冷却

**Cookie 路径**: `data/jd_auth/cookies.json`（或 `JD_COOKIES` env var，GitHub Actions 用 base64）。

### 3.2 `tools/fund_scorer.py` — 五维评分 (40KB/1105 行)

**架构**（fan-in=74，核心模块）:
```
class FundScore (L118)        # 总分数据类
class compute (L153)          # 加权平均 + 估值修正 + 3 条 falsify 规则
score_fund(code)        L821  # 主入口（区分 主动/指数/指增）
score_quality(...)      L473  # 1y排名 30% + 3y排名 20% + 回撤 20% + Sharpe 10% + 估值 10% + 机构 15%
score_cost(rules)       L539  # 管理费+托管费+申购费
score_manager(mgr)      L594  # 任职年限 + 历史业绩 + 规模惩罚
score_momentum(chart)   L675  # MA20 25% + MA60 斜率 25% + 回撤恢复 15%
score_smart_money(...)  L723  # 建仓人数 + 加仓共识 + 持仓广度
batch_score             L908  # 批量
validate_scoring_predictive_power  L973  # 验证评分预测能力
```

**默认权重**: 25/20/20/15/20（质量/成本/经理/动量/聪明钱）
**falsify 规则**（自动否决）:
1. 规模 < 5000 万
2. 经理任职 < 1 年
3. 近 3 月涨幅 > 100% (heat_penalty)

**回测版**在 `backtest/engine/backtest.py` 里有 `_backtest` 后缀对应函数，全部带日期截断（防未来函数）。

### 3.3 `backtest/engine/backtest.py` — 回测引擎 (100KB/2250 行)

**入口**: `run_backtest(config)` L1259

**关键函数**:
- `score_fund_backtest(code, cutoff_date, ...)` L630 — 单基金五维评分（含 4433 + 行业估值 + 公告）
- `score_smart_money_backtest(...)` L163 — 聪明钱（建仓 vs 加仓 vs 清仓 + 14 天共识）
- `score_4433(...)` L561 — 4433 法则排名加分
- `compute_player_rankings(...)` L466 — 动态大佬权重（多因子 + 时间衰减）
- `detect_market_state(date)` — 用沪深 300(110020) 判断牛/熊/中性
- `compute_correlation_matrix(...)` — 相关性过滤（>0.85 排除）
- `class Portfolio` L806 — 组合管理（现金/持仓/确认/冷却/年交易上限）
- `run_backtest(config)` L1259 — 主循环，T+N 确认、相关性、ML 信号、行业再平衡

**输入**:
- `trading_by_date_fixed.json` (448 天)
- `trading_history_fixed.json` (8856 笔)
- `fund_charts.json` (273 只 1 年)
- `fund_cache/*_<code>.json` (费率/经理/持仓)
- `fund_name_map.json` (433 条名称→代码)

**输出**: `backtest/reports/backtest_*.json` 含 daily_values / trades / scores / Sharpe / Calmar / MaxDD

### 3.4 `backtest/run_strategies.py` — 12 策略对比

**STRATEGIES 列表 L17**（12 个）:

| 策略 | 关键参数 | 18月回测收益 | 夏普 | 回撤 |
|---|---|---|---|---|
| **K 无脑跟投** | min_score=0, 2人买就跟 | +82.64% | 19.01 | 4.35% |
| **I 优化器最优** | min_score=2.5, 浅止损 | +57.99% | 20.23 | 2.87% |
| **A 费用敏感** | cost_penalty=1.2, SL=-10% | +25.85% | 10.21 | 2.5% |
| **H 默认基准** | min_score=3.3, 标准参数 | +25.85% | 10.21 | 2.5% |
| **F 趋势跟踪** | 阶梯止盈, 无止损 | +38.84% | 5.65 | - |
| **B 指数优先** | fund_type=passive | (无成交) | - | - |
| **C 主动精选** | fund_type=active, 门槛 3.5 | (低) | - | - |
| **D 智能费用** | cost_penalty=1.0 | (中) | - | - |
| **E 分批建仓** | SL=-8%, profit_mode=quarter | (中) | - | - |
| **G 绝对收益** | SL=-5%, TP=15% | -0.66% | - | - |
| **J 买入持有** | 不止盈不止损 | (基线) | - | - |
| **L 月定投 2500** | monthly_injection=2500 | (基线) | - | - |

**K 系变体** (`backtest/reports/k_full_variants.json`):
- **M20+跟卖 2** = +160.53% / 夏普 26.59 / DD 6.04% （**当前最优**）
- 跟卖 2 人 / 买卖对称 -2 / 净信号+跟卖 2 = +156.40% (但 DD 27.4%)
- 严格 TP 30/50 反而降到 +65-95%

### 3.5 `scripts/daily_live.py` — 每日实盘模拟 (核心入口)

**触发**: GitHub Actions 14:30 / `py -3.10 scripts/daily_live.py --simulate-date YYYY-MM-DD`

**配置**: `data/evolution/best_config.json` 的 `gene` 字段（自动进化的最优参数）

**默认 GENE**:
```python
{
  "bear_market_no_buy": False,
  "take_profit_pct": 80, "stop_loss_pct": -15,
  "ml_weight": 1.5,
  "min_score_bull": 2.5, "min_score_neutral": 3.0, "min_score_bear": 3.5,
  "trailing_tp_activate": 15, "trailing_tp_drawdown": 8,
  "cooldown_days": 15, "cooldown_profit_days": 10, "cooldown_loss_days": 30,
  "max_correlation": 0.85, "dynamic_ranking": True,
  "momentum_sell": 2.0, "slippage_pct": 0.1, "cash_reserve_pct": 0.1,
  "max_position_pct": 20, "max_sector_pct": 50, "max_qdii_pct": 50
}
```

**数据加载**:
- `data/fund_cache/trade_rules_*.json` / `fund_manager_*.json` / `fund_profile_*.json`
- `data/fund_charts.json` (基础 1 年)
- `backtest/data/trading_by_date_fixed.json` (大佬交易)

**虚拟持仓**: `reports/sim/virtual_portfolio.json` (初始 ¥100,000)

**输出**:
- `reports/sim/YYYY-MM-DD.md` (人类日报)
- `reports/sim/YYYY-MM-DD.json` (机器报告)
- AI 审计入口在 MD 末尾

### 3.6 `scripts/auto-pipeline.py` — 每日 14:30 自动管道 (107KB)

**流程**:
1. 加载 cookies (从 env 或 `data/jd_auth/cookies.json`)
2. `get_user_holdings(uid=None)` 你的实盘 + `batch_get_holdings` 11 大佬
3. `get_trading_records(uid)` 11 大佬交易
4. `get_fund_performance / fund_detail / fund_chart_data` 补全数据
5. `get_daily_news` / `get_fund_ranking` 资讯和排行
6. `_aggregate_trading_signals` 聚合买卖信号（买入 +2 / 加仓 +1 / 定投 +0.5）
7. 五维评分 + 输出 `reports/auto/daily-YYYY-MM-DD.md`
8. HTML 报告 `reports/auto/scan-{date}.html`

**已知问题**: 有重复的 `_generate_report` 函数（首次跑可能打印两次）

### 3.7 `tools/technical_indicators.py` — 技术指标 (12K/376 行)

**融合 QuantDinger 算法**（防高位接盘核心模块）:
- `compute_rsi(nav, period=14)` L24 — RSI (>70 超买, <30 超卖)
- `compute_macd(nav, 12, 26, 9)` L53 — MACD
- `compute_bollinger_bands(nav, 20, 2.0)` L96 — 布林带
- `compute_atr(nav, period=14)` L122 — ATR
- `compute_overbought_score(nav)` L242 — 综合超买（RSI+布林+涨幅）
- `compute_mean_reversion_score(nav)` L279 — 均值回归（RSI 30-50 且趋势向上）
- `compute_entry_timing_score(chart_pts, cutoff_date)` L322 — **综合择时**（防未来函数关键）

**回测引擎调用**: `timing_filter: True` 时启用，RSI>75 扣 1.0 分，RSI>80 扣 1.5 分

### 3.8 `tools/fund_rules.py` — 规则引擎 (10K/237 行)

**4 个核心规则**:
- `weighted_clear(code, holdings_diff)` L28 — 加权清仓（持有>2年×2, 6月-2年×1, <6月×0.5）
- `buy_shield(code, my_holdings, trading_cache)` L64 — 买入护盾（≥2 大佬买则抵消减仓）
- `take_profit_level(fund_type, hold_days)` L107 — 止盈/止损阈值表
- `swap_cost(code, expected_excess_return)` L135 — 调仓成本（赎回+申购 vs 预期收益×30%）
- `analyze_all(code, fund_type)` L175 — 统一分析入口

**输入**: `data/holdings_diff_cache.json` / `data/trading_records_cache.json` / `data/auto/status.json`

### 3.9 `tools/ml_signal.py` — LightGBM 增强 (8K/217 行)

**`class MLSignalEnhancer` L42**:
- 16 维特征: 5 维评分 + 1m/3m/6m 收益 + 回撤 + 波动率 + 规模 + 管理费 + 买入数 + 市场状态 + 基金年龄 + 总分
- 标签: 30 日后收益 > 3% 则 1
- `pretrain(cutoff_date, training_data)` L165 — walk-forward 训练（**严格防前视偏差**）
- `predict(code, cutoff_date, ...)` L208 — 预测 P(盈利)

**依赖**: `lightgbm` + `numpy`（缺则降级到 0.5）

### 3.10 `tools/fund_planner.py` — 资金分配 (6K/165 行)

**Kelly 公式 + 风险平价**:
- 筛选 score≥3.3 且 buy_count≥2 的候选
- Kelly 公式 → 单只 ≤15% → 单日限额 → DCA 拆分
- CLI: `py -3.10 tools/fund_planner.py --cash 50000 --output data/auto/status.json`

### 3.11 `run.py` — 一键监控（用户最常用入口）

**用法**: `py -3.10 run.py`

**功能**:
1. Step 1: 你的实盘持仓（从 JD API 拉，含真实盈亏 + RSI + 趋势 + 风控建议）
2. Step 2: 大佬持仓监控（前 15 个的盈利 Top + 共识）
3. Step 3: 大佬交叉持仓（被 ≥2 大佬持有 = 共识信号）
4. Step 4: 风控摘要

**关键函数**: `risk_check(profit_pct, rsi, trend)` L56 — 9 种风控决策（强卖/止盈/减仓/加仓/持有/观望）

---

## 四、回测策略全景（已做完的所有实验）

| 报告 | 窗口 | 最佳 | 收益 | 夏普 | DD |
|---|---|---|---|---|---|
| **strategy_comparison.json** | 短 | A 费用敏感 | +41.19% | 6.56 | 6.28% |
| **strategy_comparison_v2.json** | 18 月 | I 优化器 / K 跟投 | +57.99% / +82.64% | 20.23 / 19.01 | 2.87% / 4.35% |
| **k_full_variants.json** | 18 月 | M20+跟卖2 | **+160.53%** | 26.59 | 6.04% |
| **momentum_hybrid.json** | 18 月 | 纯动量系列 | (Top1) | - | - |
| **overnight.json + final_best.json** | 18 月 | 65 变体扫 | (Top2) | - | - |
| **long_term_backtest_results.json** | 30 天 | 纯机器 | +3.68% / 年化 61.55% | 2.97 | 2.15% |

**基准**: 沪深 300 = +27.37%（18 月）

**关键发现**（`K_STRATEGY_FINAL_REPORT.md`）:
- K 跟投收益最高但回撤 4.35% — **回撤来自跟投对 2024 H2 低迷期**
- 加上 "动量崩溃卖出 + 跟卖信号" 后变成 M20+跟卖 2，**风险调整后最优**
- 严格止盈 (TP 30/50) 反而降低收益到 +65-95% — **过拟合的标志**

**未来函数/过拟合审计**:
- 18 月窗口只看到 2025-01-05 ~ 2026-07-01 高峰段
- 28 月窗口（`tmp_run_28m.py` 实测）K 跟投降到 +31.66% / 年化 12.51% / 超额 -12.54%
- 真正基准是**更长窗口 + 滚动切段**

---

## 五、30 个 SKILL 速查表

### 5.1 基金类（13 个，**核心**）

| SKILL | 一句话 | 触发 |
|---|---|---|
| `fund-monitor` | 11 大佬持仓+交易监控，识别 ≥3 人共识 | "今天大佬买了什么" |
| `fund-checklist` | 买入前 6 关（能力圈/质量/经理/费率/流动性/聪明钱） | "X 该不该买" |
| `fund-sell` | 4 级卖出信号（每日🔴/每周🟡/每周🟢/每月🔵） | "我持仓 X 该卖吗" |
| `fund-analyze` | 五维评分文本解读 | "解读 024239 评分" |
| `fund-penetration` | 穿透到底层重仓股 | "X 底层资产" |
| `fund-quarterly` | 6 季度持仓变化追踪 | "X 季报" |
| `fund-compare` | 多只五维横向对比 | "X vs Y" |
| `fund-debate` | 单只多空辩论（看多/看空/中立） | "X 辩论" |
| `fund-scan` | 端到端：抓数据→评分→HTML 报告 | "扫一下基金" |
| `fund-trade` | 今日(3 点前)交易建议 | "今天买什么" |
| `fund-investment-team` | 4 大师并行分析基金 | "4 大师分析 X" |
| `fund-strategy-d-review` | 策略 D 季度检视 | "D 策略复盘" |
| `codebuddy-fund-research` | CodeBuddy 一句话调全套 | "codebuddy 基金研究" |

### 5.2 股票类（10 个，**巴菲特框架**）

| SKILL | 一句话 |
|---|---|
| `investment-research` | 7 模块单 Agent 研究（偏见→数据→生意→护城河→风险→管理层→文明） |
| `investment-team` | 4 角色并行深度研究 |
| `investment-checklist` | 巴菲特 6 关 + 镜子测试 |
| `earnings-review` | 财报精读（一手资料） |
| `earnings-team` | 4 大师并行财报精读 + 公众号 |
| `management-deep-dive` | 管理层纵深（诚信+能力+治理） |
| `industry-research` | 行业产业链全景 + 全球扫描 |
| `industry-funnel` | 4 层漏斗筛 30-60 家到 3 家 |
| `private-company-research` | 未上市公司 6 Agent 研究 |
| `quality-screen` | 7 条去劣硬指标 |

### 5.3 辅助类（7 个）

| SKILL | 一句话 |
|---|---|
| `bottleneck-hunter` | 供应链瓶颈套利（AI/能源/国防/半导体） |
| `deep-company-series` | 8 篇长文拆一家公司（《看懂XX》系列） |
| `dyp-ask` | 扮演段永平回答投资/商业/人生 |
| `financial-data` | 财务数据获取+交叉验证规范 |
| `news-pulse` | 股价异动 10 分钟归因 |
| `portfolio-review` | 组合级审视（集中度+相关性+压力测试） |
| `thesis-tracker` | 买入后投资论文追踪+红线清单 |
| `wechat-article` | 公众号三 Agent 协作 |

**SKILL 依赖图**（`docs/SKILL_GRAPH.md`）:
```
fund-monitor → fund-checklist → fund-penetration → investment-checklist
            → fund-analyze → fund-sell → fund-checklist
fund-scan → fund-monitor + fund-checklist
investment-research → investment-checklist + industry-research + management-deep-dive
investment-team → investment-research + earnings-review
```

---

## 六、常用命令速查

```bash
# === 监控 ===
py -3.10 run.py                              # 一键监控（实盘持仓 + 11 大佬 + 共识 + 风控）
py -3.10 scripts/auto-pipeline.py            # 每日 14:30 抓数据 + 评分 + 报告
py -3.10 scripts/auto-pipeline.py --offline  # 离线模式（仅用缓存）
py -3.10 scripts/daily_live.py               # 实盘模拟
py -3.10 scripts/daily_live.py --simulate-date 2026-06-15  # 模拟历史日

# === 回测 ===
py -3.10 backtest/run.py                     # 完整回测（拉数据 + 跑 + 权重对比）
py -3.10 backtest/run.py --skip-fetch        # 跳过数据拉取
py -3.10 backtest/run.py --start 2025-01-05 --end 2026-07-01
py -3.10 backtest/run_strategies.py          # 12 策略对比
py -3.10 scripts/validate_backtest.py --quick  # 稳健性验证

# === 工具 ===
py -3.10 tools/jd_finance_api.py --test                       # Cookie 测活
py -3.10 tools/jd_finance_api.py --batch-holdings             # 11 大佬持仓
py -3.10 tools/jd_finance_api.py --trade-rules 110020         # 费率/限额
py -3.10 tools/jd_finance_api.py --fund-profile 110020        # 基金档案
py -3.10 tools/jd_finance_api.py --login                      # Playwright 登录
py -3.10 tools/fund_scorer.py 110020                          # 单基金五维评分
py -3.10 tools/fund_rules.py --analyze 110020                 # 规则引擎分析
py -3.10 tools/fund_planner.py --cash 50000                   # Kelly 分配
py -3.10 tools/expand_charts_jd.py                            # 扩展净值到 extended
py -3.10 tools/build_ranking_cache.py                         # 构建 ranking 缓存
py -3.10 tools/build_score_cache.py                           # 构建 scores 缓存

# === 报告 ===
py -3.10 scripts/generate_report.py        # 深度 checklist
py -3.10 scripts/generate_html.py          # HTML 报告

# === SKILL 同步 ===
py -3.10 scripts/sync-codex-skills.py      # skills/ → codex-skills/
py -3.10 scripts/sync-codex-prompts.py     # → codex-prompts/
py -3.10 scripts/sync-opencode-skills.py   # → opencode-skills/

# === 进化 / 优化 ===
py -3.10 backtest/auto_optimize.py         # 4 阶段寻优
py -3.10 scripts/optimize_backtest.py
py -3.10 scripts/phase4_optimize.py
py -3.10 scripts/phase5_extreme.py

# === 测试 ===
py -3.10 -m pytest tests/                  # 80%+ 覆盖率
```

**Python 版本**: 必须 `py -3.10`（不要用系统默认 3.14，因 lightgbm/numpy 在 3.14 上不稳定）

---

## 七、关键数据文件清单

| 文件 | 大小 | 用途 |
|---|---|---|
| `data/jd_auth/cookies.json` | 几 KB | **登录态**（GitHub Actions 用 env 覆盖） |
| `data/holdings_snapshot_2026-07-0[1-9].json` | 100KB×N | 每日持仓快照 |
| `data/holdings_snapshot.json` | 100KB | 最新持仓 |
| `data/holdings_diff_cache.json` | - | 持仓变化缓存（驱动信号） |
| `data/trading_records_YYYY-MM-DD.json` | - | 每日交易记录 |
| `data/trading_records_cache.json` | - | 交易缓存 |
| `data/fund_charts.json` | - | 273 只基金 1 年净值（基础） |
| `data/fund_charts_extended.json` | - | 扩展（部分 8 年） |
| `data/fund_charts/<code>.json` | - | 每只基金独立净值（自成立起，最长 17 年） |
| `data/fund_cache/fund_profile_<code>.json` | - | 基金档案 |
| `data/fund_cache/fund_perf_<code>.json` | - | 业绩排名 |
| `data/fund_cache/trade_rules_<code>.json` | - | 费率/T+N/限额（30 天有效） |
| `data/fund_cache/fund_manager_<code>.json` | - | 基金经理 |
| `data/fund_cache/fund_holdings_<code>.json` | - | 持仓分布（7 天有效） |
| `data/fund_cache/fund_notices_<code>.json` | - | 公告（7 天有效） |
| `data/fund_cache/daily_news/YYYY-MM-DD.json` | - | 每日新闻（**已按日期归档反未来函数**） |
| `data/fund_name_map.json` | 22KB | **433 条 名称→代码 映射（81.2% 覆盖）** |
| `data/fund_charts_meta.json` | - | 273 只基金元信息 |
| `data/auto/status.json` | 500KB | **实时状态**（大佬持仓/交易/市场状态） |
| `data/industry_valuation.json` | 1MB | 行业 PE 百分位 + 10 年历史 |
| `data/fundamentals.json` | 2KB | NVDA/AMD/MU 财务 |
| `data/strategy_D_config.json` | 1.5KB | D 策略核心-卫星配置 |
| `data/cache/scores.json` | - | 30 只预计算评分 |
| `data/cache/ranking.json` | 51KB | 271 只预计算排行 |
| `data/evolution/best_config.json` | - | 进化最优参数 |
| `data/long_term_backtest_results.json` | 3.4KB | 长期回测结果 |
| `backtest/data/trading_history_fixed.json` | - | **8856 笔大佬交易** |
| `backtest/data/trading_by_date_fixed.json` | - | **448 个交易日聚合** |
| `backtest/data/fund_charts.json` | - | 273 只基金（回测版） |
| `backtest/reports/strategy_comparison_v2.json` | - | **12 策略对比** |
| `backtest/reports/k_full_variants.json` | - | **K 变体细扫** |
| `reports/sim/YYYY-MM-DD.md` | - | 每日实盘模拟报告 |
| `reports/sim/virtual_portfolio.json` | - | 虚拟持仓 + PnL |
| `reports/auto/daily-YYYY-MM-DD.md` | - | 机器日报 |
| `reports/auto/scan-YYYY-MM-DD.html` | - | HTML 报告 |

---

## 八、关键设计模式与坑

### 8.1 反未来函数（**最关键约束**）

7 铁律 (`GOAL.md` L31-38):
1. **日期截断**: T 日只用 T 日前数据（`cutoff_date` 必传）
2. **无未来函数**: 任何评分/择时函数都接受 `cutoff_date` 参数
3. **T+N 确认**: 申购 T+1, 赎回 T+3~7
4. **费率全计**: 申购+赎回+管理+托管
5. **日限额约束**: 单只基金 day_limit
6. **冷却期**: 止盈卖 10 天, 止损卖 30 天
7. **多权重对比**: 跑 ≥3 种权重组合

**实现位置**:
- `tools/technical_indicators.py: compute_entry_timing_score(chart_points, cutoff_date)` L322
- `tools/ml_signal.py: pretrain(cutoff_date)` L165 — 严格检查前瞻数据不超过截止日
- `tools/fund_scorer.py` 回测版函数名带 `_backtest` 后缀
- 新闻按日期归档在 `data/fund_cache/daily_news/{date}.json`

### 8.2 五维评分 falsify 规则（自动否决）

1. 规模 < 5000 万 → 否决
2. 经理任职 < 1 年 → 否决
3. 近 3 月涨幅 > 100% → heat_penalty -0.8
4. 近 3 月涨幅 > 80% → heat_penalty -0.4

### 8.3 数据时点（**最容易出错**）

- `fund_charts.json` 自带日期，自动截断
- `trading_history_fixed.json` 自带日期
- `data/fund_cache/fund_perf_*.json` 变动少，可近似历史
- **新闻**：必须从 `daily_news/{date}.json` 读，**不要从 status.json**

### 8.4 性能与超时

`docs/AI_DATA_GUIDE.md`:
- **预计算缓存**: 50-200ms（`data/cache/*.json`）
- **JD API**: 1-5s（需 cookie）
- **消除 spawn python 后**: `/api/ranking` 从 1-2s → 50-200ms

### 8.5 JD API 已知的失败端点（不要浪费时间）

- ❌ `gw/generic/jj/h5/m/getRankingProductListV2` — 已下线
- ❌ `gw/generic/jj/newh5/m/getInvestResearchRank` — 已下线
- ✅ `gw2/generic/jj/h5/m/queryFullRanking` — 26 榜 TOP20（用这个）
- ✅ `gw2/generic/jj/h5/m/getRankingHeaderInfoV2` — 一级分类

### 8.6 牛人榜的 11 vs 21 大佬差异

- `FOLLOWED_USERS` 字典写死 **11 个 numeric_id**
- `data/holdings_snapshot_2026-07-02.json` 含 **21 个用户**（你关注了更多人）
- **新关注的 10 个只有名字，没有 numeric_id** → 无法拉交易历史
- **JD API 不提供"我关注的人"列表接口** — 这是结构性缺口
- 想突破：需 (a) Playwright 抓京东金融网页版 / (b) 牛人榜前 10 名用 base64 pin

### 8.7 28 月窗口 vs 18 月窗口的真实差异

- 18 月 (`strategy_comparison_v2.json`) K 跟投 = +82.64% / 夏普 19.01
- 28 月 (实测 `tmp_run_28m.py`) K 跟投 = +31.66% / 夏普 1.14 / **超额 -12.54%**
- 2024 H2 是 K 跟投的"低谷期"（2024-08 整月 0 笔大佬交易）
- **18 月窗口是过拟合** — 真策略必须看更长窗口

---

## 九、ROADMAP 与未来工作

`docs/ROADMAP.md`:
- **P0** (1-2 月): 接入 akshare/东财，覆盖 A 股
- **P1** (3-6 月): HTML 报告 / 多档深度 / 多股横向对比
- **P2** (6 月+): 单元测试 / 组合级分析

`specs/08-evolution-loop.md` 战略自动进化（**部分已实现**）:
- 7 铁律
- 自动调参
- 防过拟合

**当前未实现**:
- `specs/05-event-bus.md` — blinker event bus（设计有，**实装少**）
- `specs/06-rag-memory.md` — RAG 向量库 + 长期记忆（`tools/rag/` 框架有，未充分用）
- `specs/09-market-scan.md` — 全市场扫描引擎（`fund-scan` 是简化版）
- `specs/11-performance-attribution.md` — 绩效归因（`tools/performance_attribution.py` 有雏形）

---

## 十、AI 工作流（任何 IDE 通用）

### 10.1 开局 Prompt（最推荐）

复制到 IDE 系统 prompt:
```markdown
你是 AI Berkshire 投研助手, 帮用户审计场外基金/解读基金日报。

**必读**:
1. `docs/AI_DATA_GUIDE.md` — 数据地图（先读这）
2. `docs/SKILL_GRAPH.md` — SKILL 依赖图

**工作模式**:
- 用户给 SKILL 名 + 代码/参数 → 按 `skills/<skill>.md` 步骤执行
- 优先读 `data/cache/*.json` / `data/fund_cache/*_<code>.json`
- 数据陈旧（>7 天）必标 ⚠️
- 不确定时明确标 "⚠️ 不确定" + 原因
- 报告保存到 `reports/<skill>/YYYYMMDD.md`

**触发场景**:
- "这只基金能不能买" → `fund-checklist <code>`
- "今天大佬买了什么" → `fund-monitor`
- "我这只该卖吗" → `fund-sell <code>`
- "扫一下最近的好基金" → `fund-scan`
- "半导体现在能买吗" → `industry-research` + `fund-scan`
- "今天日报" → 读 `reports/sim/YYYY-MM-DD.md` 末尾 AI 审计入口

**禁止**:
- 硬编码费率/T+N/限额（必须从 API 实时获取）
- 大佬信号当成决策依据（只是参考）
- 数据缺失时瞎猜（标 N/A）
```

### 10.2 触发关键词（自动跑）

| 用户说 | 触发 |
|---|---|
| "分析今天基金操作" / "分析今天大佬操作" | `py -3.10 scripts/auto-pipeline.py` |
| "看看今天买入卖出" | 同上 |
| "跑一下基金监控" | `py -3.10 run.py` |
| "fund-scan" | `py -3.10 scripts/auto-pipeline.py` + `py -3.10 scripts/generate_report.py` |
| "输出 HTML 报告" + "基金" | `py -3.10 scripts/generate_html.py` |

### 10.3 读日报审计

```markdown
你是 AI 投研审计员。用户刚跑完 `daily_live.py`, 生成了 `reports/sim/YYYY-MM-DD.md`。

**你的任务**:
1. 读 `reports/sim/YYYY-MM-DD.md` 末尾的"AI 审计入口"
2. 按入口里的 SKILL 调用建议, **逐个执行**
3. 输出"AI 审计结论"附在原日报后 (用 ## AI 审计 区块)
```

---

## 十一、立即上手（3 步）

1. **读 `docs/AI_DATA_GUIDE.md`**（10 分钟）— 数据地图
2. **跑 `py -3.10 run.py`**（30 秒）— 看你的实盘 + 11 大佬
3. **看 `reports/sim/latest.md`**（如存在）— 最近一次实盘模拟

**之后**:
- 想看策略回测：读 `K_STRATEGY_FINAL_REPORT.md` + `STRATEGY_FINAL_REPORT.md`
- 想加新大佬：改 `tools/jd_finance_api.py: FOLLOWED_USERS`（需 numeric_id）
- 想看 SKILL 工作流：复制 `docs/AI_AUDIT_PROMPT.md` 到 IDE
- 想加新策略：参考 `backtest/run_strategies.py: STRATEGIES` 列表加新条目

---

## 十二、注意事项

1. **Python 必须 3.10**（`py -3.10`），3.14 上 lightgbm/numpy 不稳定
2. **Cookie 在 `data/jd_auth/cookies.json`**（2.4 天寿命），GitHub Actions 用 `JD_COOKIES` env
3. **IP 风控**：连续 max_pages=10+ 触发，60-180 秒冷却
4. **18 月窗口是过拟合**，真决策看 28 月
5. **基金 vs 大佬信号**：大佬信号是参考，**不是决策依据**（避免 024239 那种高位接盘）
6. **5 个回测常见问题**（`docs/项目/回测对齐方案.md` 有详细说明）:
   - 数据时点没截断
   - 费率没全计
   - 冷却期没生效
   - 重复扣分（quality 内的 heat_penalty 在总分中又算一次）
   - T+N 没确认

---

**最后更新**: 2026-07-12
**配套脚本**: `scripts/gen-prompt-context.py` — 自动生成 AI 上下文
