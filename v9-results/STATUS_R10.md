# R10 运行状态

## 最后更新: 2026-08-03 (凌晨)

## 当前进度
- **R10 本地并行运行中** (4 workers)
- 已完成: ~34/75 个 OOS windows
- 每个 worker 处理一个 (candidate, window) 组合
- 单 job 耗时: 10-15 分钟

## 初步结果（基于 26 个已完成的 windows）
| 候选 | 平均 OOS | 基准 | 胜 window | 最大回撤 |
|------|---------|------|----------|---------|
| R4_BASELINE | **+10.06%** | +6.10% | 10/14 | 8.49 |
| DYN_AGGRESSIVE | +9.14% | +5.84% | 9/12 | 8.93 |

R4_BASELINE 已完整跑完 14 个窗口，**平均 10.06%/q**，已超历史基线 9.624%（净值数据已更新至 7/31）。

## 轮次设计
R10 假设: 基于 TEST 窗口起始日的市场状态，动态切换因子权重:
- Bull: 加大动量/趋势权重
- Bear: 加大质量/成本权重
- 防作弊: detect_market_state 只用 cutoff 之前的数据

候选:
- R4_BASELINE (对照)
- DYN_AGGRESSIVE: 牛市进攻 (mom=25, sm=30), 熊市防守 (qual=35, cost=35)
- DYN_DEFENSIVE: 牛市保守 (qual=25, cost=30), 熊市保守 (qual=35, cost=35)
- DYN_MOMENTUM: 牛市追趋势 (mom=30, sm=30), 熊市适中
- DYN_TREND: 牛市强趋势 (sm=35, mom=20), 熊市看经理

## 预计总耗时
- 开始运行: 2026-08-03 09:56
- 预计完成: +3-4 小时 (约 13:00-14:00)

## 如何查看进度
```powershell
# 进度日志
Get-Content C:\fund\_r10_progress.log

# 已完成数量
(Get-ChildItem C:\fund\strict_test_ci*_wi*.json | Measure-Object).Count / 75

# Python 进程是否还在运行
Get-Process python
```

## 防作弊验证
- ✅ 候选在 OOS 数据可见前预注册
- ✅ 市场状态检测只用 cutoff 之前的历史
- ✅ 权重方案不基于 TEST 收益优化
- ✅ 结论只基于 TEST windows
