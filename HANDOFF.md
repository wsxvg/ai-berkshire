# AI Berkshire — 迭代交接文档

## 项目概述
基于 3648 只基金每周 NAV 的量化选股策略，通过严格的 OOS (Out-of-Sample) 回测迭代优化。

## 当前状态
- **最新成功轮次**: R10
- **基线**: R4_BASELINE = 9.624%/q (历史) → 10.010%/q (数据刷新后)
- **当前最优**: DYN_TREND = 11.088%/q (+1.078% alpha)

## 完整迭代历史

| 轮次 | 候选数 | OOS 平均 | vs 基线 | 状态 |
|------|--------|---------|---------|------|
| R4 | 5 | 9.624% | baseline | ✅ 最佳基线 |
| R7 | 5 | ~9.5% | -0.1% | ❌ |
| R8 | 5 | ~9.3% | -0.3% | ❌ |
| R9 | 5 | 9.4% | -0.2% | ❌ |
| **R10** | **5** | **11.088%** | **+1.078** | **✅ 突破!** |
| R11 | 5 | TBD | TBD | 🔄 运行中 |

## R10 详细结果
排名:
1. **DYN_TREND**: 11.088% (牛市 SM=35/Mo=20, 熊市 Mgr=30/Q=25)
2. R4_BASELINE: 10.010%
3. DYN_AGGRESSIVE: 9.834%
4. DYN_MOMENTUM: 9.735%
5. DYN_DEFENSIVE: 9.276%

关键发现:
- 趋势跟踪（牛市加 smart_money）有效
- 熊市防守（加质量/成本）反而拖累
- W7 噩梦窗口 (-8.14%) 虽改善但仍存在
- 最新数据 (wi=13,14) 趋势跟踪爆发力极强

## R11 进行中 (2026-08-03 启动)
候选:
1. DYN_TREND_V2: SM 从 35→40，延续 R10 成功路径
2. TRIPLE_REGIME: 引入中性行情（bull/neutral/bear 三元）
3. ADAPTIVE_HOLDINGS: 牛市 max_holdings=15，熊市 max_holdings=8
4. TRAILING_REDUCE: 渐进式减仓
5. R4_BASELINE: 对照

防作弊:
- 所有候选在 OOS 数据可见前预注册 (2026-08-03)
- 行情划分基于 cutoff 之前数据
- 不基于 TEST 期调优

## 关键技术细节

### OOS 框架
- 14 TRAIN windows + 14 TEST windows
- 30天滑动，180天训练 + 90天测试
- BASE: 2023-07-17 ~ 2026-07-31
- 数据从京东金融 API 刷新至 2026-07-31

### 运行方式
- 本地并行: `python scripts/run_r10_local.py test 4`
- GitHub Actions: 每个 (candidate, window) = 1 job, max-parallel=8
- 单次 OOS 全量 (75 jobs): 本地约 4-5 小时，Actions ~52 分钟

### 模型
5-D 评分: quality(20) + cost(25) + manager(15) + momentum(10) + smart_money(30)

## 目录结构
- `scripts/exp_strict_oos.py` — 主实验脚本（含 ROUND 和 CANDIDATES 定义）
- `scripts/run_r10_local.py` — 本地并行运行器
- `scripts/analyze_r10.py` — 结果聚合分析
- `backtest/engine/backtest.py` — 回测引擎（含 regime detection）
- `v9-results/` — 各轮次结果 JSON 和分析
- `HANDOFF.md` — 本文档

## 交接注意事项
1. 修改 ROUND/CANDIDATES 后需重新 git push
2. 本地运行和 GitHub Actions 共享同一份 CANDIDATES 定义
3. `aggregate_test()` 函数将结果写入 `v9-results/strict_oos_r{N}_eval.json`
4. R7-R9 均无法超越基线，R10 首次突破
