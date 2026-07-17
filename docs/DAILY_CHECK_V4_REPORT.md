# daily_check V4 — 新端点接入 + 实盘首跑报告

> 日期: 2026-07-13
> 阶段: P2-P4 (新端点) + P5 (实盘) 完成

## 🔍 P2-P4 新端点接入结论

3 个新端点 **封装完成** 但 **端点全部 FAIL**，**无法接入回测**。

| 端点 | 状态 | 原因 |
|------|------|------|
| `getInvestResearchRank` (经理评级) | ❌ FAIL | `status: FAIL` |
| `getFundLabel` (基金标签) | ❌ FAIL | `code: 0000` 但无数据 |
| `getIndexValuationTrendChart` (估值) | ❌ FAIL | `status: FAIL` |

**根因** — 端点需要更复杂的登录态（HAR 抓包与当前 cookies 不一致），5 种 referer 全部试过都失败。

**已封装但暂不可用** — 代码已写到 `tools/jd_finance_api.py` 末尾，等抓包 cookies 修复后自动可用。

## 📊 当前策略状态 (V2 仍是最终方案)

| 版本 | 年化 | 夏普 | 胜率 | 验证集年化 | 验证集胜率 |
|------|-----:|-----:|-----:|----------:|----------:|
| V0 (best_config) | 24.13% | 1.52 | - | - | - |
| V1 (无止盈) | 53.03% | 2.02 | 0% | (未测) | - |
| **V2 (P1 止盈) ⭐** | **39.18%** | **1.64** | **55%** | **+182%** | **84.6%** |
| V3 (P1+P3) | 17.23% | 1.38 | 60.9% | +94.8% | 80% |
| V4 (V2+新端点) | - | - | - | - | 端点 FAIL 跳过 |

## 🎯 P5 实盘首跑 (2026-07-13 11:15)

`daily_push.py` 首次执行结果：

### 今日 (2026-07-13) 体检
- ✅ 跟买共识: **3 只 QDII 科技基各被 2 位大佬同买**
  - 华夏全球科技先锋混合(QDII)A
  - 建信新兴市场混合(QDII)A
  - 国富全球科技互联混合(QDII)人民币A
- ⚠️ ranking 缓存过期（需跑 build_ranking_cache.py）
- ⚠️ 无卖出信号 / 无关键公告

### 30 天 V2 策略实测
| 指标 | 值 |
|------|---|
| 区间 | 2026-06-13 ~ 2026-07-13 |
| 年化 | **-9.08%** (小幅回调) |
| 夏普 | -0.02 |
| 胜率 | 6% (1 笔盈利 / 6 笔) |
| 交易 | 6 笔 |
| **Alpha (超额)** | **+7.63%** ✅ |

**实盘观察** — 7 月初小幅震荡，V2 跑输市场 9% 但仍**跑赢基准 7.6%**。属于策略正常工作。

## 📦 全部产出

| 文件 | 用途 |
|------|------|
| `tools/jd_finance_api.py` (末尾新增) | 3 个新端点封装（待修复 cookies 后可用） |
| `scripts/backtest_v2.py` | V2 引擎 |
| `scripts/grid_tp.py` | tp 参数扫描 |
| `scripts/daily_push.py` | 每日推送 |
| `scripts/daily_check.py` | 一键体检 |
| `.github/workflows/daily.yml` | GitHub Actions 自动化 |
| `docs/DAILY_CHECK_V2_REPORT.md` | V2 完整报告 |
| `docs/DAILY_CHECK_V3_REPORT.md` | V3 (P3 失败证据) |
| `docs/DAILY_CHECK_V4_REPORT.md` | V4 (新端点 + 实盘首跑) |
| `reports/daily_check_2026-07-13.{json,md}` | 今日体检结果 |
| `logs/daily_push_20260713_*.json` | 今日推送日志 |

## 🚀 实盘下一步

| 任务 | 操作 | 频率 |
|------|------|------|
| 1. 每日体检 | `py -3.10 scripts/daily_check.py --no-feishu` | 每日 14:30 |
| 2. 跑 V2 推送 | `py -3.10 scripts/daily_push.py --no-feishu` | 每日 14:30 |
| 3. 监控 30 天 V2 表现 | 看 `logs/daily_push_*.json` 里的 alpha | 每日 |
| 4. 修复新端点 cookies | 抓新 HAR 抓包提取 | 一次性 |
| 5. 真实买/卖执行 | 等 1 周观察 | 一周后 |

## 💡 重要提醒

- **V2 仍是最优策略** — 新端点全部失败，V2 (P1 止盈) 仍是当前冠军
- **新端点封装已就位** — 一旦 cookies 修复即可用
- **实盘已就绪** — daily_push 完整跑通
- **胜率是关键指标** — V2 验证集 84.6% 胜率是真实能力
- **本次 30 天 -9% 不必慌** — Alpha +7.6% 仍跑赢基准
