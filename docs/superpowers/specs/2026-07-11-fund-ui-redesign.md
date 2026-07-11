# 基金智能投资系统 UI 重构设计

## 目标

基于 real-time-fund 开源项目（Next.js + 玻璃拟态），替换数据源为京东金融 API，新增五维评分/大佬信号/AI审计功能。

## 架构

```
ai-berkshire/                   # 现有 Python 后端
  tools/jd_finance_api.py       # 京东金融 API（42个端点）
  backtest/engine/backtest.py   # 回测引擎
  scripts/daily_live.py         # GitHub Actions 日报

fund-ui/                        # 新前端（Fork 自 real-time-fund）
  app/api/fund.js               # 代理层 → 京东金融 API
  app/api/score.js              # 代理层 → Python 评分引擎
  app/components/               # 基金卡片/图表/持仓
  app/stores/                   # Zustand 状态管理
  app/lib/                      # 京东API客户端/数据处理
```

## Phase 1：数据源替换

| 原有数据源 | 替换为 | 优先级 |
|-----------|--------|--------|
| 东方财富 JSONP | 京东 getFundDetailPageInfoWithPin | P0 |
| 天天基金排行 | 京东 getRankingProductListV2 | P0 |
| 腾讯财经股票行情 | 保留（重仓股追踪） | P0 |
| 自选列表 | 京东 queryZxProductList | P0 |
| 估值时间序列 | 京东 getFundChart → 自算 | P1 |

## Phase 2：新增评分层

- `app/api/score.js`：调用 Python 评分引擎，返回五维评分 + smart_money + 4433 + RSI
- `components/ScoreBar.jsx`：评分进度条（0-5分）
- `components/SmartMoneyBadge.jsx`：大佬信号图标（★数量）
- `components/RiskTag.jsx`：风控标签（超买警告/估值高估/持仓亏损）

## Phase 3：日报页面

- 新路由 `/report`，读取 `reports/sim/*.md` + `*.json`
- 净值曲线图（基于虚拟持仓 snapshots）
- 当日推荐列表 + 风控拦截列表
- AI审计入口（fund-checklist/fund-penetrate/fund-sell 按钮）

## 技术选型

- Next.js 14+ (App Router)
- Tailwind CSS + 玻璃拟态 (backdrop-blur)
- Zustand 状态管理
- Recharts 图表库
- 京东金融 API（Python 后端代理）

## 数据流

```
浏览器 → Next.js API Route (fund.js/score.js)
         → child_process 调用 Python 脚本
         → tools/jd_finance_api.py 拉取数据
         → backtest/engine/backtest.py 评分
         → 返回 JSON → 前端渲染
```
