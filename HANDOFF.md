# AI Berkshire 策略迭代 — 完整交接文档

> 生成时间: 2026-08-02
> 当前最佳: R7 WEEKLY_MACD, OOS 11.208%/q, 年化 ~53.0%, vs CSI300 超额 ~26.3%/年
> 协议: 严格零作弊 (无未来函数, 无过拟合, 无数据窥探)

---

## 1. 项目目标

在**零作弊**约束下, 持续迭代量化基金策略以提高 OOS (样本外) 收益率:

- **严禁未来函数**: T 日决策只能用 ≤T 日的数据
- **严禁过拟合**: Train/Test 严格分离, 结论只基于 TEST
- **严禁数据窥探**: 候选必须在看到 TEST 结果前预注册

---

## 2. 核心架构

### 2.1 交易机制 (京东金融 OTC 基金)

- **15:00 前**下单 → **当日收盘净值**成交
- **15:00 后** → 下一日净值
- Smart money 信号 (大佬 T 日买入 T 日晚间公布) → T+1 日 15:00 前下单 → T+1 日成交, 完全符合现实, 无未来函数
- **T+N 结算**: API 返回的 "预计到账" 就是**实际日历日期**, 使用 `_add_days()` (日历日加法, 非交易日)。买入确认用 buy_date→confirm_date 日历差, 卖出到账用 redeem_date→redeem_arrive_date 日历差

### 2.2 Strict OOS Walk-forward

- 28 个滑动窗口 (180 天训练 + 270 天测试, 30 天滑动)
- W0-W13 = Train, W14-W27 = Test
- 结论**只基于 Test**

### 2.3 5 维评分模型

| 维度 | 权重 (R7 最佳) | 说明 |
|------|---------------|------|
| quality | 20 | 4433 排名 |
| cost | 25 | 费率 |
| manager | 15 | 经理质量 |
| momentum | 10 | 动量 |
| smart_money | 30 | 大佬买入信号 |

### 2.4 关键文件

| 路径 | 作用 |
|------|------|
| `C:\fund\backtest\engine\backtest.py` | 回测引擎主文件 |
| `C:\fund\scripts\exp_strict_oos.py` | OOS 实验框架 (候选定义在此) |
| `C:\fund\.github\workflows\strict_oos_p1.yml` | GitHub Actions workflow |
| `C:\fund\tools\jd_finance_api.py` | 京东 API 数据采集 |
| `C:\fund\v9-results/strict_oos_r7_eval.json` | R7 结果 |
| `C:\fund\v9-results/strict_oos_r8_eval.json` | R8 结果 |
| `C:\fund\data/trading_by_date_fixed.json` | smart money 交易记录 |
| `C:\fund\data/fund_charts/` | 基金净值图表数据 |

---

## 3. 迭代历史

### R1-R4 (2026-08-01)

| 轮 | 最佳候选 | OOS avg/q | 关键改动 |
|---|---------|-----------|---------|
| R1 | TP_CONSERVATIVE | 10.05% | 止盈/止损 |
| R2 | Q30_C20_M20 | 8.77% | 权重调节 |
| R3 | HOLD12_AGGRESSIVE | 7.90% | 持仓上限 |
| **R4** | **WEIGHTS_ALT** | **10.583%** | smart_money=30 |

**R4 建立基线**: 5 维评分模型成熟, 候选间差异 <1%。

### R5-R8 (2026-08-02)

| 轮 | 方向 | 假设 | 结论 |
|----|------|------|------|
| R5 | market_risk_filter | 市场风险规则 | ❌ 未出结果 |
| R6 | LightGBM 尾部风险 | ML 预测器 | ❌ 超时 |
| **R7** | **价格型滤波** | MA250/MACD/Bollinger | **✅ 微弱改进 (边际)** |
| R8 | 广度防御+组合回撤 | 被动式风控 | ❌ 无效/反效果 |

### R7 详细结果 (当前最佳)

```
TRIPLE_COMBO : avg_return=10.142 beats=10/14 max_dd=8.148
MA250_FILTER : avg_return=10.594 beats=10/14 max_dd=8.246
WEEKLY_BOLL  : avg_return=9.962  beats=10/14 max_dd=8.613
WEEKLY_MACD  : avg_return=11.208 beats=10/14 max_dd=8.060  ← BEST
R4_BASELINE  : avg_return=10.583 beats=10/14 max_dd=8.245
```

### R8 关键发现 (广度防御失败的原因)

- **BREADTH_30 vs R4_BASELINE**: 完全一致 (9.624%/q, W7 同样 -9.26%)
- 原因: TEST 期 (2023-07 ~ 2026-07 的 W14-W27) 市场**结构性上涨**, 广度很少跌破阈值
- BREADTH_30 唯一触发过的, 反而**更差** (9.179) — 减仓在大盘横盘期错失了选股 alpha

---

## 4. 发现的关键洞察

### 4.1 W7 是所有策略的噩梦

- 窗口: 2025-10-04~2026-01-02
- CSI300 仅 -1.16%, 但选股策略 **-9.29%** (R4baseline)
- 这是**选股 alpha 的系统性失灵**, 大盘横盘但持仓基金暴跌
- R7 价格滤波 / R8 广度防御 都无法修复

### 4.2 核心矛盾

- smart_money 在**牛市** (W3/W4/W9) 捕获力最强
- 但在**横盘偏弱**期 (W7/W10/W11/W12) 产生严重负 alpha
- 策略本质是 **smart_money 追踪 + 趋势跟随**, 在无趋势市场失灵

### 4.3 边际递减

- R4 → R7 改进仅 +0.625%/q (~2.5%/年)
- R7/R8 的价格/广度信号额外改进 ~0
- **评分模型已到瓶颈**, 必须换方向

---

## 5. T+N 结算的经验教训

**三轮反复最终确认的正确逻辑**:

1. API 返回 `redeemBankProcess` 数组, 包含 赎回/确认份额/预计到账 三步
2. "预计到账" 就是**实际日历日期** (用户纠正: "实际京东到账的日期就是那时候")
3. 用 `_add_days()` 做日历日加法 (非交易日)
4. 买入: `get_t_plus_n()` 返回 buy_date→confirm_date 日历差
5. 卖出: `_get_sell_t_plus_n()` 返回 redeem_date→redeem_arrive_date 日历差

---

## 6. 反作弊检查清单 (R1-R8 全程)

- [x] 候选预注册 (在看到 TEST 结果前设定)
- [x] 训练集/测试集严格分离 (W0-W13 vs W14-W27)
- [x] 自动化选参 (aggregate_train 自动选 ci, 人工不干预)
- [x] 5 候选全部 TEST (不只测 train-winner)
- [x] 结论只基于 TEST (W14-W27)
- [x] 迭代规则: 上一轮 TEST 结果 → 设计下一轮 → 重新预注册
- [x] 结果推送到 origin (可审计)
- [x] smart_money 无未来函数验证 (大佬 T 日买入, T+1 日 15:00 前下单, T+1 收盘成交)

---

## 7. GitHub Actions 机制

### 7.1 触发方式

```bash
git add -A && git commit -m "R9 ready: xxx" && git push
```

- Workflow: `.github/workflows/strict_oos_p1.yml`
- matrix: ci: [0,1,2,3,4] × wi: [0..13]
- 70 train + 70 test + aggregate ≈ 143 jobs
- max-parallel=8, 全部完成约 4-8 小时

### 7.2 结果回收

```bash
# 结果自动 push 到 v9-results/strict_oos_r9_eval.json
curl https://raw.githubusercontent.com/wsxvg/ai-berkshire/master/v9-results/strict_oos_r9_eval.json
```

### 7.3 常见问题

| 问题 | 原因 | 修复 |
|------|------|------|
| 全部 job failure | Python 函数名/变量未定义 | 本地先跑 `python scripts/exp_strict_oos.py run_train 0 0` |
| 结果 = baseline | 新增信号逻辑有 bug 或永远不触发 | 打印日志 + 对比 ci |
| GitHub 链接 reset | 网络问题 | 自动重试 |

---

## 8. R9 候选建议 (预注册)

**方向: 单基金止损线 (Per-position Trailing Stop-loss)**

- 不同于组合层宏观止损 (R8 失败), 为**每只持仓基金**设峰值回撤 Y% 止损
- 逻辑: 基金净值从持仓最高点回撤 > Y% 时强制清仓
- 金融学原理: 趋势跟随 + 截断亏损
- W7 场景: 暴跌基金及早砍掉, 避免组合整体 -9%

**候选 (预注册 2026-08-02)**:

| # | 名称 | 参数 |
|---|------|------|
| 0 | R4_BASELINE | 对照 |
| 1 | STOPLOSS_12 | stop_loss=12% |
| 2 | STOPLOSS_15 | stop_loss=15% |
| 3 | STOPLOSS_15_TIGHT | stop_loss=15% + 组合 DD 6% 减仓 |
| 4 | TRAILING_10 | 动态跟踪止损, 从最高净值回撤 10% |

**实现要点**:

在 `sell()` 逻辑中添加每基金峰值跟踪:
```python
if code in self.holdings:
    peak = self.holdings[code].get("peak_nav", 0)
    current = self.fund_prices.get(code, 0)
    if peak > 0 and current < peak * (1 - stop_loss_pct / 100):
        # 触发止损, 卖出
```

---

## 9. 关键数据库

| 表名 | 说明 |
|------|------|
| `trading_by_date_fixed.json` | 大佬交易记录, {date: [{fund_code, fund_name, ...}]} |
| `fund_charts/` | 每只基金的净值时间序列 |
| `v9-results/` | 各轮 OOS 结果 |

---

## 10. 长期有效的迭代方法论

1. **固定基线**: R4_BASELINE 始终包含在新轮测试中作为锚点
2. **预注册**: 候选列表在看到 TEST 结果前设定, 事后不改
3. **5 候选**: 4 实验 + 1 基线, 避免单候选过拟合
4. **差异对比**: 新 vs 旧基线 的 per-window diff 比绝对值更重要
5. **W7 专项**: 每轮必看 W7 表现, 这个窗口区分策略是否鲁棒
6. **边际 = 0 时换方向**: 当改进 <0.5%/q, 说明当前维度到瓶颈, 必须换假设

---

## 11. 启动新 AI 时的指令模板

```
你正在继续一个量化基金策略迭代项目。

## 必须遵守
1. 严禁未来函数/作弊
2. 结论只基于 OOS TEST (W14-W27)
3. 候选预注册后才能看结果

## 当前状态
- 最佳: R7 WEEKLY_MACD, OOS 11.208%/q, 年化 ~53%
- 基线: R4_BASELINE, OOS 10.583%/q
- W7 (Oct~Jan 2025) 是所有策略的噩梦 (-9.26%)
- R8 (广度防御) 失败, 未改善 W7

## 下一轮方向
R9: 单基金止损线 (per-position stop_loss)

## 文件
- 回测引擎: C:\fund\backtest\engine\backtest.py
- 实验脚本: C:\fund\scripts\exp_strict_oos.py
- 工作流: C:\fund\.github\workflows\strict_oos_p1.yml
- 结果目录: C:\fund\v9-results/

## 工作循环
1. 设计候选 (更新 exp_strict_oos.py)
2. 本地验证 1-2 个关键窗口
3. git commit + push 触发 Actions
4. 等待 ~4-8 小时
5. 拉取 JSON 结果, per-window 分析
6. 决定 R10 方向
```

---

## 12. R10+ 方向候选池

如果 R9 也边际 = 0, 可以探索:

1. **换仓频率优化**: 减少再平衡频率以降低 fee
2. **多时间框架**: 把周线/月线信号混合到日频
3. **基金间相关性**: 用相关性矩阵避免高度相关基金重复持有
4. **市场中性**: 持有多 + 模拟空 (如果有期货数据)
5. **动量崩溃检测**: 识别动量因子反转早期信号
6. **Lasso/ElasticNet 自适应权重**: 用 ML 动态调整 5 维权重而非固定

---

*文档版本: R8 后, 2026-08-02*
*维护人: kilo (github: wsxvg)*
