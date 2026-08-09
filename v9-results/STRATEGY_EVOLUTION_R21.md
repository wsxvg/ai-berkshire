# R21 迭代总结 — 大佬因子 OOS 公平验证（干净数据 v7 + bug 修复）

> 更新: 2026-08-09 晚（修正版——修复 global bug 后重跑）
> 数据: `trading_by_date_real414_v7.json.gz`（权威干净数据，550,365 条）
> 方法: 22 OOS 测试窗口 (2022-12 ~ 2026-08)，4 候选同窗公平对比

## 🎯 一句话结论（修正版）

**发现并修复了一个致命 bug（`_SMART_MONEY_MODIFIER` 缺 `global` 声明），导致 R21 初版对 SMART_MOD 的结论作废。修复后重跑证明：大佬因子在"独立维度"（SMART_BUY）和"修饰符"（SMART_MOD）两种处理方式下，OOS 上均无正净 alpha，且略微恶化回撤。因此"放弃大佬因子"的**方向判断**仍然成立，但**原因**从"修饰符未触发"修正为"修饰符触发了但确实没有 alpha"。**

## 📊 R21 完整结果（22 窗，修复后，2022-12-11 ~ 2026-08-22）

| 候选 | avg_return | vs BASELINE | avg MaxDD | peak MaxDD | beats率 |
|---|---|---|---|---|---|
| **KC_SMART_BUY_15** | **3.366%** | **+0.094%** | 5.55% | 15.87% | 12/22 (55%) |
| KC_AGGRESSIVE_BASELINE | 3.271% | — | 5.77% | 15.63% | 12/22 (55%) |
| KC_SMART_MOD（修复后） | 3.270% | -0.001% | 5.81% | **16.43%** | 12/22 (55%) |
| KC_SMART_BUY_25 | 3.085% | -0.186% | 5.37% | 16.12% | 14/22 (64%) |

- 基准 CSI300: avg +1.648%
- 前 3 个测试窗口 (wi21-23, 2022-12~2023-07) 全部 0% 空仓（基金覆盖率不足 warm-up，同 R18-R20 一致）

## 🔍 关键发现

### 1. 【本修正轮核心】发现并修复 SMART_MOD 失效的 global bug
- **根因**：`score_smart_money_backtest()`（backtest.py 第 268 行）给全局变量 `_SMART_MONEY_MODIFIER` 赋值时**没有 `global` 声明**，赋值成为局部变量，模块级变量恒为 0.0，下游 `score_fund_backtest()`（第 1005 行）读到的修饰符永远为 0。
- **影响**：R21 初版中 SMART_MOD 在全部 22 窗 === BASELINE（收益完全相同），不是"信号未触发"，而是"触发了但加成被 bug 吞掉"。
- **实证**：直接调用函数传入确定命中强信号的基金（2023-11-23/161725, cb=-7.07,tg=4,nb=2），修复前修饰符返回 0.0，修复后返回 0.5。✅
- **修复**：commit `61f00ec` 在函数首行加 `global _SMART_MONEY_MODIFIER`。
- **仅 ci3 受影响**：SMART_BUY_15/25（ci1/2）用原始模式（直接返回 DimensionScore），不受影响，结果真实。

### 2. 修复后：SMART_MOD 确实改变持仓，但无净 alpha
- 修复后 SMART_MOD 与 BASELINE 在 **9/22 窗**不同（win30/32/33/34/35/39/40/41/42），证明修饰符真正生效。
- 但**平均收益 -0.001%（≈0）**，跑赢 5 窗、跑输 4 窗，赢输相抵。
- 亮点：wi41 单窗 +1.63% 超额；败点：wi42 -0.96%、wi33 -0.64%、wi34/35 -0.32%。
- **peak MaxDD 恶化到 16.43%（全场最差）**——修饰符让仓位在回调中更激进，回撤反而加大。

### 3. 两种大佬因子处理方式均无 alpha → 方向判断不变
- 独立维度：SMART_BUY_15 (+0.094%)、SMART_BUY_25 (-0.186%)——权重越高越差
- 修饰符：SMART_MOD (-0.001%)
- **无论哪种处理方式，大佬因子在干净数据 + 完整 22 窗下都没有带来正净 alpha。**
- 这与 R20 结论一致，也与历史教训一致。

### 4. 方法论教训（重要）
- **一个没跑通的实现，绝不能被当成"因子无效"的证据。** 当某候选与基线"完全相同"时，第一反应应是怀疑**实现有 bug**（作用域/缓存/条件分支），而不是断言"信号没触发"。
- 初版 R21 因该 bug 把"修饰符模式无 alpha"误判为"SMART_MOD ≡ BASELINE"，差点错误放弃一个从未真正测试过的设计。修复后才得到真实结论。

## ✅ 决策

**确认：放弃大佬因子（smart_money）作为增强主方向，保留 BASELINE（KC_AGGRESSIVE_BASELINE）作为 R22 起点。**
- 与初版结论的"方向"一致，但**原因已修正**：不是"修饰符未生效"，而是"独立维度与修饰符两种方式实测均无正 alpha"。
- R22 转向探索其他 alpha 来源（动量/质量维度调参、行业轮动、择时细化），不再围绕 smart_money 信号。

## 🛠 本轮操作记录（修正轮）

1. **定位 bug**：用户质疑"大佬因子为何没用"，触发排查。检查信号覆盖率（1097 天 / 19586 条，覆盖充足）、编码匹配（信号 TA 码 ∩ 交易记录 187 全命中）、日期对齐（1097 天全重合）——均正常，最终锁定 `global` 作用域问题。
2. **修复**：commit `61f00ec` 加 `global` 声明，本地实证修复有效（强信号→0.5）。
3. **重跑**：新建 `.github/workflows/strict_oos_r21_smartmod_rerun.yml`，仅重跑 ci3（SMART_MOD）22 窗，在 GitHub Actions 完成（run `31313216507`，4 job 全 success）。
4. **下载 + 重聚**：下载 4 个 artifact，替换 ci3 文件，本地 `python scripts/exp_strict_oos.py test` 重聚 `v9-results/strict_oos_r21_eval.json`。
5. **ci0/1/2 复用**：不受 bug 影响，结果直接复用，未重跑。

## 📁 产物
- `v9-results/strict_oos_r21_eval.json` — 修正后的完整 R21 eval（4 候选 × 22 窗）
- `.github/workflows/strict_oos_r21_smartmod_rerun.yml` — ci3 重跑 workflow（可复用）
- `scripts/_poll_r21_smartmod.py` — R21 ci3 轮询器

## 下一步（R22 方向建议）
- 基于 BASELINE（KC_AGGRESSIVE_BASELINE）做稳健性/参数优化，或探索**非 smart_money 的新信号源**（费率/规模/份额变动等硬数据）。
- 若未来再引入 smart_money，务必先用单元测试验证修饰符确实改变分数（本次教训）。
- 本地不再跑回测，所有计算走 GitHub Actions。