# R21 迭代总结 — 大佬因子 OOS 公平验证（干净数据 v7）

> 更新: 2026-08-09
> 数据: `trading_by_date_real414_v7.json.gz`（权威干净数据，550,365 条）
> 方法: 22 OOS 测试窗口 (2022-12 ~ 2026-08)，4 候选同窗公平对比

## 🎯 一句话结论

**大佬因子在完整 22 窗同窗对比下几乎没有净 alpha——最佳候选（SMART_BUY_15）仅领先 BASELINE +0.094% 且回撤更差，不值得保留。R20 的"smart_money 有害"结论在干净数据 + 完整窗口下再次确认。**

## 📊 R21 完整结果（22 窗，2022-12-11 ~ 2026-08-22）

| 候选 | avg_return | vs BASELINE | avg MaxDD | peak MaxDD | beats率 |
|---|---|---|---|---|---|
| **KC_SMART_BUY_15** | **3.366%** | **+0.094%** | 5.55% | 15.87% | 12/22 (55%) |
| KC_AGGRESSIVE_BASELINE | 3.271% | — | 5.77% | 15.63% | 12/22 (55%) |
| KC_SMART_MOD | 3.271% | +0.000% | 5.77% | 15.63% | 12/22 (55%) |
| KC_SMART_BUY_25 | 3.085% | -0.186% | 5.37% | 16.12% | 14/22 (64%) |

- 基准 CSI300: avg +1.648%
- 前 3 个测试窗口 (wi21-23, 2022-12~2023-07) 全部 0% 空仓（基金覆盖率不足 warm-up，同 R18-R20 一致）

## 🔍 关键发现

### 1. 补全 BASELINE 后，大佬因子超额几乎消失（本轮核心）
- 之前 BASELINE 只有 16 窗（缺 wi37-42 高收益段）时：SMART_BUY_15 = **+2.20%** vs BASELINE
- 补全到 22 窗后（wi37-42 收益高：+25.6/+8.2/+30.7 等）：SMART_BUY_15 只领先 **+0.094%**
- **证实 handoff 预测**：BASELINE 只跑 16 窗被严重低估，补全后均值从 1.162% 升至 3.271%，大佬因子超额从 +2.20% 收窄到 +0.09%
- BASELINE 补全的 6 窗：wi37(+25.6%) wi38(-6.2%) wi39(+8.2%) wi40(-5.8%) wi41(+30.7%) wi42(+0.9%)，均值 ~+8.8%/窗，确实是高收益段

### 2. SMART_MOD（修饰符模式）≡ BASELINE（零效果）
- SMART_MOD 与 BASELINE 在所有 22 窗**收益完全相同**（0 窗口差异）
- 说明 `smart_money_modifier` 加减分在测试窗口**从未触发**（信号未命中）或实现无效
- 无论哪种，修饰符模式对"是否保留大佬因子"的决策无影响——它没产生任何 alpha

### 3. SMART_BUY_25（weight=25）反而跑输
- 权重越高越差：weight=15 (+0.094%) > weight=25 (-0.186%)
- 更高权重放大噪声，加剧回撤（peak MaxDD 16.12%，全场最差）

### 4. 与 R20 结论一致
- R20 (2026-08-08) 已发现 smart_money 信号 alpha 微弱 (+0.4%) 且恶化回撤 (+6% peak)
- R21 在干净数据 v7 + 完整 22 窗下**再次确认**：大佬因子无净 alpha，且恶化回撤
- 唯一正面：SMART_BUY_25 的 beats 率 64%（14/22）最高，但靠的是更激进换仓换来的，收益反而更低

## ✅ 决策

**放弃大佬因子（smart_money），保留 BASELINE（KC_AGGRESSIVE_BASELINE）作为 R22 起点。**
- 下一轮 R22 聚焦 BASELINE 自身的稳健性/参数优化，不再引入 smart_money 信号
- 与历史教训一致：R15 (smart_money=0)、R20 (smart_money 有害) 都指向去掉该维度

## 🛠 本轮操作记录

1. **发现 R21 重跑 bug**：`strict_oos_r21_parallel.yml` 的 b5 块用 `timeout 300`，但 ci0 后段窗口在 GitHub runner 上 >300s，导致 wi37-42 全部超时被杀，ci0-b5 artifact 为空，BASELINE 仍缺 6 窗
2. **新建补跑 workflow** `.github/workflows/strict_oos_r21_baseline_backfill.yml`（commit `6fe758e`）：3 job × 2 窗，`timeout 900`，跑完 ci0 wi37-42 全部成功
3. **下载 artifact**：从 R21 run `31308921476` 下载 ci1/2/3 的 18 个 artifact + ci0 b0-b4 的 5 个 artifact + 补跑的 3 个 artifact，共 26 个，整合 88 个 test 窗口文件（4 候选 × 22 窗）
4. **重建 eval**：本地 `python scripts/exp_strict_oos.py test` → `v9-results/strict_oos_r21_eval.json`
5. **R21 旧 eval 作废**：之前 aggregate 因 ci0-b5 缺失 + git push 失败，只算出 16 窗 BASELINE（1.162%，低估）；现已被完整 22 窗 eval 取代

## 📁 产物
- `v9-results/strict_oos_r21_eval.json` — 完整 R21 eval（4 候选 × 22 窗，本轮核心交付）
- `.github/workflows/strict_oos_r21_baseline_backfill.yml` — 补跑 workflow（可复用）
- 88 个 `strict_test_ci*_wi*.json` 窗口文件（已整合到项目根目录）

## 下一步（R22 方向建议）
- 基于 BASELINE 稳健性做微调（如 kelly_cap、max_holdings 网格）——但 R16 已证边际有限
- 或探索**非 smart_money 的新信号源**（费率/规模/份额变动等硬数据，避免大佬持仓噪声）
- 本地不再跑回测，所有计算走 GitHub Actions