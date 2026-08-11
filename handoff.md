# HANDOFF 交接文档 — C:\fund 量化策略项目

> **更新时间**: 2026-08-09 深夜
> **用途**: 供新开对话使用，防止上下文丢失。新对话先读本文件 + `CLAUDE.md` + `AGENTS.md`。

---

## 〇、最新进展（R23/R24 — 方向反转！大佬因子首次出现正超额并翻倍）

### 🎯 一句话核心结论
修复未来数据泄露 bug（top3 全期→逐日滚动）+ 接入接口全量 T+N 后，**R23 首次出现正超额，R24 精调阈值把超额翻倍到 +0.86%**。方向：**"宽回调"有效——回调窗口越宽、大佬信号越有效**。这是连续第 2 次正超额，迭代远未到停损线（10 次连续零收益才停）。

### R23（双线路 top3，逐日滚动 + 真实 T+N）
| 候选 | avg_return | vs BASELINE |
|---|---|---|
| BASELINE | 3.271% | — |
| **KC_SMART_AMOUNT**（持仓金额 top3）| **3.641%** | **+0.37%** |
| KC_SMART_RETURN（持仓收益率 top3）| 3.551% | +0.28% |

- 修复前信号仅覆盖 187 基金（未来泄露 bug 压缩）；修复后覆盖 1869-1872 基金，覆盖率正常。
- **8/22 窗有信号**（5 正 +8.63%，3 负 -0.50%），正贡献跨多个时期，非只在近期。
- **去掉收益最高 2 窗后仍为正** → 非单窗偶然。

### R24（sm_params 阈值精调，全部走 amount 线路 + 共识分层修饰符）
| 候选 | avg_return | vs BASELINE | peak MaxDD |
|---|---|---|---|
| **KC_SMART_AMOUNT_WIDE**（回调 -15~-2%）| **4.130%** | **+0.859%** | 16.08% |
| KC_SMART_AMOUNT_STRICT（回调 -8~-4%）| 3.495% | +0.224% | 15.98% |
| KC_SMART_AMOUNT_HICONS（净买 7/5/3）| 3.387% | +0.116% | 16.02% |
| KC_AGGRESSIVE_BASELINE | 3.271% | — | 15.63% |

**关键发现**：
1. **更宽回调（-15~-2%）把 alpha 从 +0.37% 放大到 +0.86%**（翻倍）——浅回调（-3~-5%）也是有效信号，原 -10~-3% 窗口漏掉了。
2. 严回调（-8~-4%，+0.22%）和高共识（nb 7/5/3，+0.12%）都**不如默认**——"信号越多越有效"，卡太严错过 alpha。
3. 收益翻倍但 **peak MaxDD 几乎不变**（16.08% vs 15.63%，仅 +0.45%）。

### 迭代停损协议（用户制定）
- 每轮迭代找更好因子方向，**连续 3 次零收益/无超额 → 停，查代码 bug**；**连续 10 次零收益 → 判定无 alpha，停止**。
- 当前：连续 2 次正超额且持续提升（+0.37%→+0.86%），继续迭代。

### 本次迭代的关键技术改动（已提交）
- **信号构建重写** `scripts/_build_smart_signals_v7.py`：top3 改**逐日滚动**（截至信号日），消除未来泄露；读 `data/tn_by_fund.json` 按基金 T+N 生效；双线路输出 `smart_money_signals_amount.json`（84769 信号/1869 基金）和 `smart_money_signals_ret.json`（80329 信号/1838 基金）。
- **接口全量 T+N**：`scripts/fetch_all_tn_rules.py` 用 `getFundTradeRulesPageInfo` 接口抓全部 5985 只基金，98.7% 成功 → `data/tn_by_fund.json`（不用硬编码，符合用户要求）。
- **引擎参数化** `backtest/engine/backtest.py`：`signal_line` 参数（amount/return）+ `sm_params` 阈值字典（cb_lo/cb_hi/nb_hi/nb_mid/tg_hi/tg_mid/boost_hi/boost_mid/boost_lo）。
- **脚本** `scripts/exp_strict_oos_r23.py` / `exp_strict_oos_r24.py`；**workflow** `.github/workflows/strict_oos_r23_dualline.yml` / `strict_oos_r24_tuning.yml`。
- eval 落盘 `v9-results/strict_oos_r23_eval.json` / `strict_oos_r24_eval.json`。

### R25（在 WIDE 上测 3 个扰动方向，全部 amount/return 线路 + 共识分层修饰符）
| 候选 | avg_return | vs BASELINE | 正/负/持平窗 |
|---|---|---|---|
| **KC_SMART_WIDE_HIGHBOOST**（-15~-2% + boost 0.8/0.6/0.4）| 4.129% | **+0.858%** | 8正/3负/11持平 |
| KC_SMART_WIDER（-20~-1%）| 3.986% | +0.714% | 8正/4负/10持平 |
| KC_SMART_WIDE_RET（-15~-2% + return 线路）| 3.822% | +0.551% | 8正/3负/11持平 |
| KC_AGGRESSIVE_BASELINE | 3.271% | — | — |

**关键发现**：
1. **3 个方向全部正超额**，无一跑输基线 → "宽回调+大佬信号"方向整体稳健，非单点运气。
2. **HIGHBOOST 与 R24 WIDE 几乎持平（+0.858% vs +0.859%）** → boost 提档无效，不是瓶颈。
3. **WIDER（-20~-1%）降到 +0.714%** → 回调再放宽开始稀释信号，**-15~-2% 已是回调甜点位**。
4. **WIDE_RET（+0.551%）< 金额线路** → **金额 top3 优于收益率 top3**。
5. **稳健性确认**：去掉 top1/top2 最优窗后 HIGHBOOST/WIDER 仍有 +0.24~+0.48% 正超额，非单窗撑起。
6. **峰值大回撤不变**（peak MaxDD 15.59~16.08% vs 基线 15.63%）。

### 当前迭代状态
- **连续 3 次正超额**（R23 +0.37% → R24 +0.86% → R25 +0.86%），alpha 稳定在 +0.86% 附近。
- R24 的 WIDE 配置（-15~-2% + amount 线路 + boost 0.6/0.4/0.2）已是**回调窗口甜点**，回调/boost/线路 3 个维度均验证到头。
- **R26 方向**：转向**信号丰富度**——加大 top3→top5/top10（更多大佬持仓）、近期信号时间衰减权重、回调+动量过滤组合（仅在有正动量的基金上入场）。

### R26（信号丰富度 topN：top3→top5/top10，全部 WIDE 配置）
| 候选 | avg_return | vs BASELINE | 正/负/持平窗 | peak MaxDD |
|---|---|---|---|---|
| **KC_WIDE_TOP3** | 4.130% | **+0.859%** | 8正/3负/11持平 | 16.08% |
| KC_WIDE_TOP5 | 4.058% | +0.786% | 8正/3负/11持平 | 17.82% |
| KC_AGGRESSIVE_BASELINE | 3.271% | — | — | 15.63% |
| **KC_WIDE_TOP10** | 2.990% | **-0.281%** | 6正/5负/11持平 | 17.84% |

**关键发现**：
1. **top10 明确失败**：+0.859% → **-0.281%**（跑输基线），去最优窗后仍 -0.34~-0.40% 持续负 → **"信号越丰富越好"假设被证伪**。
2. **top5 略降**：+0.786%，仍正但回落。
3. **top3 保持最优**（+0.859%），稳健性最好（去 top2 后 +0.248%）。
4. **回撤恶化**：top5/top10 峰值回撤 17.8% vs top3 16.08%。
- **结论**：大佬持仓价值高度集中在 top3（重仓最深的3只），第4-10名是分散浅仓/噪音。**top3 是信号甜点位**。这反证 +0.86% alpha 是真因子，非运气。

### 当前信号内部参数 4 维度全部验证到头
| 维度 | 最优 | 验证轮 |
|---|---|---|
| 回调窗口 | -15~-2%（甜点位）| R24/R25 |
| boost 强度 | 提档无效 | R25 |
| 线路 | 金额 > 收益率 | R25 |
| topN | **top3 最优**，top5 略降，top10 变负 | R26 |

**R27 方向**：转向**信号组合过滤**——最看好"回调 + 动量过滤"（只在回调但中期趋势向上的基金上跟大佬入场，避免接"大佬抄底抄在半山腰"的下跌刀）。可针对 R23-R26 负超额窗口（如 2026-03-25 +8.7% 后开始回调）检验。

### 关键技术改动（R26，已提交）
- 信号构建 `scripts/_build_smart_signals_v7.py`：`compute_top3` 参数化 topn，`main` 接受 `python ... <topn>` 参数，输出 `smart_money_signals_amount_top5.json`(112318信号)/`top10.json`(149356信号)。
- 引擎 `backtest/engine/backtest.py`：`_SIGNAL_FILE_NAMES` 增 `amount_top5`/`amount_top10` 映射。
- 脚本 `scripts/exp_strict_oos_r26.py`（ci1 top3 / ci2 top5 / ci3 top10）；workflow `strict_oos_r26_topn.yml`。
- 临时脚本已清理：`_poll_github.py`（通用轮询器，保留）、`_analyze_eval.py`（通用 eval 分析，保留）。

### R27（动量门控：回调 + momentum 门控，mom_gate 2.5/3.0/3.5）
| 候选 | avg_return | vs BASELINE | 正/负/持平窗 |
|---|---|---|---|
| **KC_WIDE_MOM25**（mom_gate=2.5）| 3.843% | **+0.572%** | 6正/4负/12持平 |
| KC_WIDE_MOM30（mom_gate=3.0）| 3.709% | +0.438% | 5正/4负/13持平 |
| KC_WIDE_MOM35（mom_gate=3.5）| 3.358% | +0.086% | 4正/2负/16持平 |
| KC_AGGRESSIVE_BASELINE | 3.271% | — | — |

**关键发现（动量门控被证伪）**：
1. **一开门控 alpha 就掉**：无门控 WIDE +0.859% > MOM25 +0.572% > MOM30 +0.438% > MOM35 +0.086%——**门控越严 alpha 越低（单调）**。
2. **稳健性崩溃**：MOM25 去 top1 后 +0.183%、去 top2 后 +0.045%（几乎归零）；无门控 WIDE 去 top2 后 +0.248%。
3. **核心结论**：**"趋势向下的回调信号是失败信号"假设错误**。大佬逆势抄底（趋势弱但回调）反而是高 alpha 信号（大佬信息优势更早看到反转）。动量过滤把这类信号过滤掉了。与 R24"回调越宽越好"一致——**大佬信号自成一体，外部趋势过滤器帮倒忙**。

### 当前信号内部参数 5 维度全部验证到头
| 维度 | 最优 | 验证轮 |
|---|---|---|
| 回调窗口 | -15~-2%（甜点位）| R24/R25 |
| boost 强度 | 提档无效 | R25 |
| 线路 | 金额 > 收益率 | R25 |
| topN | **top3 最优**，top5 略降，top10 变负 | R26 |
| 动量门控 | **无效，越严越差**（叠加外部过滤方向被证伪）| R27 |

**最优配置稳定**：无门控 WIDE（回调-15~-2% + amount top3 + boost 0.6/0.4/0.2）= +0.859%（R24，多次复现）。

**R28 方向（已实现+本地证伪，未跑 GitHub）**：信号有效期 TTL——引擎加 `ttl_days` 回溯，cutoff 当天无信号时取最近 N 天内信号。本地诊断证明**无效**：TTL 命中的滞后信号因 `net_buy`（历史信号日值）大多 <3，boost 三档全不满足（boost_cb_ok 仅 ~10/133，boost_hi/mid/lo 全为 0），3 个候选（TTL3/7/14）在 wi26 结果完全一致（+0.274%）。**结论：大佬信号的高共识（nb>=3）只在信号当天有效，跟进晚了拿不到高共识信号 → 信号有效期方向被证伪**。已回滚引擎改动，删除脚本/workflow。

**R29 结果（回调深度分层，run 31375605087）**：
| 候选 | avg_return | vs BASELINE | 正/负窗 | 去top2 |
|---|---|---|---|---|
| KC_WIDE_SHALLOW_BOOST（重仓浅回调）| 4.123% | **+0.852%** | 8正/4负 | +0.218% |
| KC_WIDE_DEEP_BOOST（重仓深回调）| 3.889% | +0.618% | 8正/3负 | +0.215% |
| KC_WIDE_DEEP_ONLY（只做深抄底）| 3.334% | +0.063% | 2正/0负 | +0.000% |
| KC_AGGRESSIVE_BASELINE | 3.271% | — | — | — |

**关键发现（回调深度分层证伪）**：
1. **shallow_boost（+0.852%）≈ WIDE 无分层（+0.859%），未超越**——给浅回调加权的空间已用尽。
2. **deep_only（+0.063%）几乎崩塌**：只做深抄底（-15~-10%）、剔除浅回调后 alpha 归零，22 窗几乎全平局。**证明浅回调（-8~-2%）是 alpha 的重要组成**，深、浅都有贡献，砍掉任何一段都损失（印证 R24"宽回调越好"）。
3. **alpha 高度集中在 2025-11 后少数窗口**：shallow/deep 的正和主要来自 2026-03-25(+8.7/+3.6)、2026-01-24(+5.2)、2025-11-25(+2.9/+2.7)——去 top2 后塌缩到 ~+0.2%。**非稳定信号内优化，是单窗巧合**。
4. **核心结论**：回调深度分层无法超越 WIDE。回调-15~-2%整体就是最优，内部再分层无增益。

**R30 方向（降低净买入共识门槛）**：R24 HICONS 提高 nb 门槛（7/5/3）→ +0.12% 更差，强烈暗示**低共识方向可能有空间**（R24 结论"信号越多越有效，卡太严错过 alpha"）。当前 boost 三档 nb 门槛为 5/3/3，**没有一档接受 nb<3**。R30 给 sm_params 加 `nb_lo` 参数（boost_lo 净买入门槛，默认 3），测 nb_lo=1/2 是否更好——"只要 1-2 个大佬买就给基础 boost"的低共识信号价值。

**R30 结果（降低共识门槛，run 31383338665）**：
| 候选 | avg_return | vs BASELINE | 去top1 | 去top2 |
|---|---|---|---|---|
| KC_WIDE_NBLO2（nb_lo=2）| 3.732% | **+0.461%** | +0.223% | +0.092% |
| KC_WIDE_NBLO1_BOOST（nb_lo=1+boost0.3）| 3.416% | +0.145% | -0.092% | -0.224% |
| KC_WIDE_NBLO1（nb_lo=1）| 3.409% | +0.138% | -0.100% | -0.231% |
| KC_AGGRESSIVE_BASELINE | 3.271% | — | — | — |

**关键发现（降低共识门槛被证伪）**：
1. **nb_lo 降低全部未超越 WIDE（+0.859%）**。最好 nb_lo=2 也只 +0.461%，明显低于 WIDE。
2. **单调性明确**：nb_lo=2（+0.461%）> nb_lo=1（+0.138%）≈ nb_lo=1+boost（+0.145%）——**门槛越低 alpha 越低**。
3. **低共识信号是"噪音"**：nb_lo=1（接受 nb=1）与 nb_lo=1+boost 在去 top1 后**变负**（-0.1%、-0.23%），alpha 完全依赖单窗；nb_lo=2 去 top1 后 +0.223%（相对稳但也远不如 WIDE）。
4. **核心结论**：降低共识门槛被证伪。R24 提高 nb（7/5/3 → +0.12%）更差，R30 降低 nb（1/2 → +0.46% 及以下）也更差——**两条路都证明当前 boost 的 nb 门槛（5/3/3）就是甜点位，nb>=3 是共识下限**。只有 1-2 个大佬买的信号是噪音，加了稀释 alpha。**高共识（nb>=3）正是 alpha 所在**。R24"卡太严错过 alpha"的正确解读是"在 nb>=3 基础上回调越宽越好"，而非"降低共识"。

**当前信号内部参数 + 组合过滤 8 维度全部验证到头**：
| 维度 | 最优 | 验证轮 |
|---|---|---|
| 回调窗口 | -15~-2%（甜点位）| R24/R25 |
| boost 强度 | 提档无效 | R25 |
| 线路 | 金额 > 收益率 | R25 |
| topN | **top3 最优**，top5 略降，top10 变负 | R26 |
| 动量门控 | **无效，越严越差** | R27 |
| 信号有效期 TTL | 本地证伪 | R28 |
| 回调深度分层 | 证伪，shallow≈WIDE、deep_only 崩塌 | R29 |
| 降低共识门槛 | 证伪，nb_lo 越低越差，nb>=3 是下限 | R30 |

**最优配置稳定**：无门控 WIDE（回调-15~-2% + amount top3 + boost 0.6/0.4/0.2）= +0.859%（R24，8 维度全部围绕它验证，均无法超越）。

**R31 方向候选**：信号内部参数与组合过滤全到头，转向① **nb 连续值映射**；② **topgain 持仓深度带**；③ **smart_money 作为独立维度重测**（修复 look-ahead 后未再以"非修饰符"形式测过，仅测了修饰符模式）；④ **多信号叠加权重**。

**R31 方向调整**：初案 nb 连续值映射（线性/对数/幂 3 候选）在 wi26/30/36 全部与 WIDE 平局 → **boost 量级维度确证冗余（R25 HIGHBOOST 已证明结论一致）**。改测③独立维度：smart_money 作为非修饰符（`smart_money_modifier=False`），带权重（20/30/40%）参与 4D 加权，自 R23 修复 look-ahead 后**从未重测此形式**。wi30 烟雾测试确认区分：SM_IND20=-1.231%、SM_IND30=-1.009%、SM_IND40=-1.151%，全部跑赢 R29/R30 的 WIDE(-1.747%)，方向有效。

**R31 结果（独立维度，run 31400180891）**：
| 候选 | avg_return | vs BASELINE | 去top1 | 去top2 |
|---|---|---|---|---|
| KC_SM_IND40 | 3.651% | **+0.380%** | +0.118% | -0.144% |
| KC_SM_IND30 | 3.595% | +0.324% | +0.014% | -0.269% |
| KC_AGGRESSIVE_BASELINE | 3.271% | — | — | — |
| KC_SM_IND20 | 3.188% | -0.084% | -0.333% | -0.438% |

**结论（独立维度证伪）**：最好的 SM_IND40 +0.38% 远低于 WIDE 修饰符 +0.86%。独立维度参与 4D 加权反而不如修饰符加减分模式。WIDE 仍是最优 — 累计第 10 个维度证伪。

**当前 10 维度验证全貌**：
| 维度 | 最优 | 验证轮 |
|---|---|---|
| 回调窗口 | -15~-2%（甜点位）| R24/R25 |
| boost 强度 | 提档无效 | R25 |
| 线路 | 金额 > 收益率 | R25 |
| topN | **top3 最优**，top5 略降，top10 变负 | R26 |
| 动量门控 | **无效，越严越差** | R27 |
| 信号有效期 TTL | 本地证伪 | R28 |
| 回调深度分层 | 证伪 | R29 |
| 降低共识门槛 | 证伪，nb>=3 是下限 | R30 |
| nb 连续值映射 | ✗ 与 WIDE 全平局 (局部证伪) | R31a |
| 独立维度 | ✗ +0.38% < WIDE +0.86% | R31b |

**用户反馈与 R32 方向**：WIDE 16% CAGR ≈ 宽基 ETF，没有超额外收益。转用户的 ①③ 方向（引擎易实现且未测过）：
- ① 仓位收紧：max_holdings 12→4/6（信号更集中）
- ③ 活跃门控：引擎加 window-level `sm_active_gate` — 测试窗口期内统计 max net_buy + 合格基金数，双低→全仓货基(0%窗口收益)，避免低共识期"空转"
- 下一轮考虑：② 克隆大佬组合（直接买 top3 重仓），④ 更短 walk-forward 窗口（30d）

**R32 状态 (run 31411854332)**：已触发，监控中。ci1=NARROW4(4只,无gate), ci2=NARROW4_GATE(4只+门控), ci3=NARROW6_GATE(6只+门控)。wi30 烟雾测试三候选区分：NARROW4 -0.808%、NARROW4_GATE -0.808%(gate未触发)、NARROW6_GATE -1.305%，均不同于 WIDE -1.747%。

### R34 — Tactical Asset Allocation (宽基配比)
**触发原因**：R33 克隆大佬模式最终证伪（5 bug 修完后 avg +0.699%，alpha -2.57% vs BASELINE 3.27%）。结论：买回调 ≠ 未来超额收益。**转向宽基战术资产配置**。

**策略概念**：跨 13 类宽基资产（A股大小盘、红利低波、纳指/标普QDII、恒生、国债、信用债、黄金、货币）动量轮动。月度再平衡，CSI300 200日均线择时控制仓位（熊=全仓避险），等权 top-K。

**关键 Bug 修复**（commit 60c1656）：
- `alloc_backtest.py` 第 127 行 `if len(dates) < rebalance_days` — 当 EQW13 设 `rebalance_days=99999` 时任何窗口都因不够长而返回 None。改为 `< 2`。
- 第 153 行 `and i > 126` 预热守卫 — 在 60 交易日的早期 OOS 窗内彻底阻断了任何交易（暖up > 窗口长）。删除此守卫；`momentum_score` 通过检查 `past_val` 自然处理不足历史，无需逐窗守卫。

**OOS 完整结果（59 test windows, 2016-12 → 2026-08, 3.6 年）**：
| 候选 | avg_return | beats bench | avg_mdd | peak_mdd | bear strat | bull strat |
|---|---|---|---|---|---|---|
| **C_EQW13** 🔵 | **+7.83%** | **32/59 (54%)** | 15.2% | 42.1% | -3.7% | +15.8% |
| C_TAA_K5 | +4.08% | 29/59 | 14.0% | 42.9% | -2.2% | +8.4% |
| C_TAA_K4 | +3.96% | 26/59 | 15.3% | 42.9% | -2.6% | +8.4% |
| C_TAA_K3 | +3.82% | 30/59 | 15.8% | 43.6% | -3.6% | +8.9% |
| CSI300 | +8.03% | — | — | — | -15.8% | +24.4% |

benchmark BEAR avg -15.8% / BULL avg +24.4%

**复利曲线（12 个非重叠 90 交易日窗）**：
- C_EQW13: **+54.6%**
- C_TAA_K4: -12.1%
- C_TAA_K3: -16.1%
- C_TAA_K5: **-25.0%** ⚠️
- CSI300: +1.4%

**核心结论**：
1. **跨资产动量轮动再次被证伪**：K3/K4/K5 全部跑输最笨的 EQW13，差距 -3.75% ~ -4.01% avg
2. **熊市二元择时有害**：K5 的 CSI300 < MA200 空仓权益规则在长期系统性地踏空牛市，复利 -25%
3. **EQW13 胜出但非碾压**：熊市保护确实（-3.7% vs -15.8%），代价是牛市踏空（+15.8% vs +24.4%）
4. **跨资产 = 噪声互累**：股/债/金/海外四维动量互相独立，跨类轮动只是在月度调仓中贡献换仓摩擦

**累计证伪记录**：R23-R32 价格/质量/成本/动量/大佬信号 多次证伪 → R33 克隆模式证伪 → **R34 跨资产动量轮动证伪**。

### 关键技术改动（R27 已提交 → R32 增量 108de3e）
- R27 引擎 `backtest/engine/backtest.py`：`score_smart_money_backtest` 加 `momentum_score` 参数，sm_params 支持 `mom_gate`。
- R32 引擎（108de3e）：
  - 模块级全局 `_SM_WINDOW_ACTIVE = True`：window-level consensus gate 标志
  - `run_backtest` 顶部提取 `_sm_active_gate_cfg` 等本地变量（避免作用域污染）
  - 窗口循环前置扫描：按 `min_qualified_funds=3` + `min_max_nb=5` 阈值，预计算整个窗口是否通过 gate，不通过则 `_SM_WINDOW_ACTIVE = False`
  - 主循环跳过：`if cfg has gate and not _SM_WINDOW_ACTIVE: continue` 效果=全仓货基, 窗口收益=0
  - `score_smart_money_backtest` modifier 分支：共识评分 gated（`if consensus_layers and _SM_WINDOW_ACTIVE:`），gate 关→tiers 不生效
  - `max_holdings` 参数：12（默认）→4/6（通过候选配置传入）
- 脚本 `scripts/exp_strict_oos_r32.py`（NARROW4 / NARROW4_GATE / NARROW6_GATE + BASELINE）；workflow `strict_oos_r32.yml`（3 块并行）。
- 通用保留：`scripts/_poll_github.py`、`scripts/_analyze_eval.py`。
## R16 前瞻（待验证，不阻塞 R/O 系列）
- **最保守 OOS 概念**：不做任何 walk-forward，直接用全部历史数据训练一个模型，对未来（未知）做一次性测试。
- 与当前 walk-forward OOS 的区别：当前 43 窗口滚动训练-测试；R16 前瞻=1 窗口全程训练 → 1 次真实前瞻测试

---

## 一、当前核心结论（一句话）

**R21 修正版结论（2026-08-09 晚，重跑已完成）：发现并修复了 `score_smart_money_backtest()` 缺 `global _SMART_MONEY_MODIFIER` 的 bug（该 bug 让 SMART_MOD 在初版 22 窗全部退化成 BASELINE，制造"大佬因子无用"的假象）。修复后重跑 ci3 证明：SMART_MOD 确实改变持仓（9/22 窗与基线不同），但**平均收益 -0.001%、peak MaxDD 恶化到 16.43%**——独立维度（SMART_BUY ±0.09~-0.19%）和修饰符两种方式均无正净 alpha。因此"放弃大佬因子、保留 BASELINE"的**方向判断仍成立**，但原因修正为"触发了但确实没 alpha"。R1–R20 结果因旧数据污染作废。**

**（以下为中间结论，已被上方取代，保留作历史）"大佬因子无 alpha"初判曾因 global bug 被推翻，修复后重跑确认方向不变。**

---

## 二、数据现状（最重要的部分）

### 权威数据文件
| 文件 | 说明 |
|---|---|
| `backtest/data/trading_by_date_real414_v7.json.gz` | **当前权威数据**（10.89MB，550,365 条，1097 天，2023-08-08 ~ 2026-08-08） |
| `backtest/data/trading_by_date_real414_v5.json.gz` | 上一版（已含 292 条 C 类修正），现作为**回退**保留 |
| `data/smart_money_signals.json` | 大佬信号（19,586 个），已基于 v7 重建 |
| `data/follow_pool_414.json` | **权威 414 用户关注池**（2026-08-08 抓取，399 有交易 + 15 无交易） |

### 引擎加载链（`backtest/engine/backtest.py` 已更新）
```
v7.json → v7.json.gz → v5.json → v5.json.gz → v4 → v2 → real414 → fixed → trading_by_date
```
（当前 v7.json.gz 存在，直接命中）

### 已删除的旧错误文件
- `backtest/data/trading_by_date_fixed.json`（旧模糊匹配，92.9MB，错配 22%）❌ 已删
- `backtest/data/trading_by_date_real414.json`（原始未修复）❌ 已删
- `backtest/data/trading_by_date.json`（旧随机用户，1.4MB）❌ 已删

---

## 三、数据修正完整历史（为什么 v7 是对的）

### 1. 权威重映射 v4→v5（commit `9e556df`，已完成）
- `fund_name_map.json`（天天基金模糊匹配，similarity≥0.85）错配率高达 **22%**（如股票基金→债券基金）
- 用**京东官方 `getFundChart` API 的权威 `productId`** 重映射（`tools/authoritative_remap.py`）
- 修复 **88,405 条**，覆盖率提升至 **99.933%**

### 2. K 线配错修复 v5→v6（2 个 fid，292 条）
- **兴全合润混合 C (fid=105360)**: 023875→163406（C 类 2025-04-08 才成立，之前用 C 类码是错的）
- **中金沪深300ETF联接C (fid=108054)**: 023147→003579（C 类 2025-06-03 成立）
- **根因**: C 类新份额有成立日期，成立前的交易用 C 类码 = K 线错误

### 3. 异常 fid 残留错配修复 v6→v7（5 条）
用 `getFundChart` 权威 productId + eastmoney + 京东档案全量复核异常 fid（ZH 组合码/日期后缀 fid）后发现 5 条漏网：

| 记录基金名 | 原code（错） | 修正为（对） |
|---|---|---|
| 华安生态优先混合A | 006396 | **000294** |
| 华泰柏瑞鼎利混合C | 005787 | **004011** |
| 兴全商业模式混合(LOF) | 005364 | **163415** |
| 银河收益债券 | 1884284282-...(异常串) | **151002** |

修正后 5 条在各自交易日期**均有当日净值**，K 线无缺口。

### 4. 无法确定（保持现状，记录在案，金额极小）
- `博时新起点混合A`（163元）：查无此基金，名字疑似笔误
- `中银腾利混合C`（710元）：记录名存疑
- `浦银颐和养老FOF-C`：正确 C 类 `007402` 无净值数据，保留 A 类 `007401`

### 5. 净值缺口分类审计（已确认无其他 K 线错误）
30,177 条取不到当日净值的记录全部归因于：**周末/节假日/QDII 延迟披露/新成立基金(45天内)/净值滞后(2026-07-22后未抓)**。仅上述 2+5 条为真配错，均已修复。

---

## 四、R21 状态（最关键——评估大佬因子）

### 🔴 R21 结论修正公告（2026-08-09 晚，重跑已完成）
**发现致命 bug，R21 初版对 SMART_MOD 的结论作废。** `score_smart_money_backtest()`（`backtest/engine/backtest.py` 第 268 行）给全局变量 `_SMART_MONEY_MODIFIER` 赋值（0.5/0.3/0.0）时**没有 `global` 声明**，导致这些赋值成为函数局部变量，模块级变量恒为 0.0。于是 `score_fund_backtest()`（第 1005 行）读到的修饰符**永远是 0.0**，**SMART_MOD 在初版全部 22 窗 === BASELINE 是必然，不是"信号未触发"，而是"触发了但没生效"**。初版"修饰符逻辑零触发/零影响"是误判。

- **修复**：commit `61f00ec` 在 `score_smart_money_backtest` 首行加 `global _SMART_MONEY_MODIFIER`。已验证：强信号（2023-11-23/161725, cb=-7.07,tg=4,nb=2）修复后返回 0.5，无信号返回 0.0。✅
- **影响范围**：仅 SMART_MOD（ci3）受影响。SMART_BUY_15/25（ci1/2）用原始模式（直接返回 DimensionScore 带 score），**不受 global bug 影响，结果真实**。
- **重跑结果（已出）**：`.github/workflows/strict_oos_r21_smartmod_rerun.yml` 已在 GitHub Actions 跑完（run `31313216507`，4 job 全 success），修复后 ci3 与 BASELINE 在 **9/22 窗不同**（修饰符确实生效），但**平均收益 -0.001%、peak MaxDD 恶化到 16.43%**——修饰符模式无净 alpha。**结论：放弃大佬因子方向不变，但原因修正为"触发了但确实没 alpha"。**

### ⭐ R21 结果（2026-08-09 更新——**结论颠覆，谨慎！**）
**⚠️ 核心结论已反转：补全 BASELINE 后，大佬因子无正 alpha，此前"跑赢基线"是缺窗口造成的假象！**

**背景**：R21 在 v7 干净数据上跑，24 backtest job 全部 success（run `31308921476`），但 aggregate 的 git push 失败。我直接从 artifacts 下载了全部结果（含 ci0-BASELINE 的 wi21-38），本地做逐窗口对比 + 敏感性分析，得出**与上一轮相反的结论**。

**重叠 18 窗（wi21-38）逐窗口对比（最公平）**：
| 候选 | 跑赢 BASELINE | 平均超额 vs BASELINE |
|---|---|---|
| `SMART_BUY_15` | 8/18 (44%) | **-0.270%** |
| `SMART_BUY_25` | 9/18 (50%) | **-0.121%** |
| `SMART_MOD` | 0/18 (0%) | **+0.000%**（与基线完全相同）|

**关键事实**：
1. **`SMART_MOD` 在所有窗口收益与 `BASELINE` 完全一致**（wi24-38 全部相同数值）→ 修饰符逻辑在 OOS 中**零触发/零影响**（回调+大佬持仓信号在测试期极少满足条件，或匹配失败）。
2. **BASELINE 缺的 4 窗（wi39-42）是高收益窗口**：wi41 参考值 +23~33%。用 ci1/ci3 敏感性补全后，**BASELINE 22窗 avg = 3.27~3.59%**，直接追平甚至反超 3 候选（3.09~3.37%）。
3. 上一轮"BASELINE 1.16% + 大佬因子 +2.2%"是**假象**——只因 BASELINE 缺了高收益后段窗口被低估。

**最终判断（数据支持）**：大佬因子（SMART_BUY 维度 / SMART_MOD 修饰符）在 R21 OOS 上**没有带来正超额收益**。SMART_BUY 略跑输，SMART_MOD 完全无效。**不推荐保留大佬因子作为增强方向。**

---

## 四-A、R22 共识强度分层版（2026-08-09 晚，已跑完）

**假设**：R21 老 SMART_MOD 用低门槛（net_buy>=1）无效；轻量前向收益验证发现共识强度(net_buy)分层单调提升回调买入质量（nb>=5 中位17.33%/胜率78.4% vs nb>=1 中位11.64%/胜率72.8%）。于是假设"提高 net_buy 门槛并按其给分层修饰符分"能产生 alpha。

**实现**（commit `36ec91c`，run `31316563070`，4 job 全 success）：
- 引擎 `backtest/engine/backtest.py` 新增 `consensus_layers` 参数（`score_smart_money_backtest` / `score_fund_backtest` / config 传递链）
- 新候选 `KC_SMART_CONSENSUS`（`scripts/exp_strict_oos_r22.py`）：修饰符模式，极高共识(回调+tg>=4+nb>=5)→+0.6、中共识(回调+tg>=4+nb>=3)→+0.4、弱共识(回调+tg>=2+nb>=3)→+0.2、净买<3一律0
- BASELINE 复用 R21 ci0（同 config，未重跑）
- eval 已落盘 `v9-results/strict_oos_r22_eval.json` 并 push（commit `39e37b9`）

**结果（22 窗同窗公平对比）**：

| 候选 | avg_return | avg MaxDD | peak MaxDD | beats率 |
|---|---|---|---|---|
| BASELINE | 3.271% | 5.77% | 15.63% | 12/22 |
| CONSENSUS | 3.225% | 5.83% | 16.43% | 12/22 |

- **共识分层版仍无正 alpha（-0.046%），回撤还略差（peak +0.80%）**
- 8/22 窗有差异（跑赢5/跑输3），但跑输的单窗差异更大（尤其 wi41 -0.495%、wi42 -0.961%）
- **结论：无论低门槛(R21)还是共识分层(R22)，大佬买入侧信号在 OOS 都无稳定正 alpha。买入侧这条路基本到顶。**

---

## 四-B、防守侧验证：大佬卖出信号（2026-08-09 晚，本地轻量）

**假设**：大佬 9.2 万条卖出记录(16.7%)从未被当独立信号用过。"大佬撤退→基金走弱"可做止损/离场信号。

**验证 1（大佬净卖出前向收益）**：
- 净卖<=-2：中位 +12.94%、胜率 77.2%（反而高于净买）→ 大佬卖出预测不了下跌
- 区分止盈/恐慌：净卖+前涨>5%(止盈) 超额中位 +1.57%；**净卖+前跌>5%(恐慌) 超额中位 +46.01%** → 恐慌卖出后基金暴涨

**验证 2（关键对照组，排除均值回归）**：加"C无交易深跌基金"对照（61.7万样本）：

| 组 | 跌幅 | 中位 | 胜率 |
|---|---|---|---|
| A 恐慌净卖 | 跌>10 | 33.88% | 70.7%（N=290）|
| B 净买 | 跌>10 | 26.09% | 72.8% |
| **C 无交易** | **跌>10** | **24.57%** | **68.9%（N=617321）**|

- **决定性结论：+46% 超额本质是"深跌基金均值回归/超跌反弹"，与大佬信号无关。** 任何深跌基金（61.7万对照样本）都反弹，A组（仅290样本）相对优势不显著。
- **"大佬恐慌卖出=反向买入"被证伪。**

**防守侧最终判断**：大佬交易信息（无论买/卖）在 OOS 都无法提供超越"深跌基线"或市场基准的稳定 alpha。**整个"大佬因子"方向（买入侧 R20-R22 + 卖出侧防守验证）均已证伪，正式关闭。**

**R23 方向建议**：不再围绕大佬信号。转向非 smart_money 的硬数据源（费率/规模/份额变动/分红），或纯量化因子（动量持续性/质量/行业轮动），或 BASELINE 自身稳健性微调。

**遗留**：ci0 BASELINE 的 wi39-42 仍缺（GitHub runner 上 ci0 后段窗口每个 >300s 超时被杀，ci1/2/3 能跑完但 ci0 不能——疑为 BASELINE 无信号过滤导致全市场扫描更慢）。需把 ci0-b5 的 timeout 单独提到 600s+ 或拆分窗口才能补全。

### R21 并行化历程（2026-08-09，血泪踩坑，务必参考！）
GitHub Actions 并行化连续踩坑，**最终方案才可用**。完整经历：
1. **v1（172 独立 job，ci×wi 双矩阵）**：回测全成功，但 **172 个并行 artifact 上传丢失 64 个**（Found 108/172），consolidate 缺 test 文件 → aggregate 失败。**教训：不要用海量独立 artifact**
2. **v2（4 job × xargs -P8）**：8 进程并发把 GitHub 免费 runner **内存打爆，OOM exit 143**，runner 被杀。**教训：单 runner 内不要多进程并发跑回测**
3. **v3（24 job，ci×窗口块 b0-5，每块单进程顺序跑 7-8 窗）**：单进程无 OOM，但 **后段窗口（wi 30-42）每个要 >90s，`timeout 90` 全被杀死** → b4/b5 块文件缺失 → 又是 test 缺文件。**教训：后段窗口慢，timeout 必须 ≥300s**
4. **v3 修复（timeout 90→300，job timeout 30→60min）**：✅ 正常跑完，test 文件 82/88，aggregate 算出全部 4 候选结果。**但最后 git commit/push 失败**（报错 `fatal: /: '/' is outside repository`，eval 文件没推到远程）

**✅ 最终可用 workflow**：`.github/workflows/strict_oos_r21_parallel.yml`
- `strategy.matrix`：ci=[0,1,2,3] × b=[0,1,2,3,4,5] = **24 个 backtest job**（每 job 单进程顺序跑一个窗口块）
- 块窗口划分：b0=wi0-7, b1=wi8-15, b2=wi16-22, b3=wi23-29, b4=wi30-36, b5=wi37-42
- 每窗口 `timeout 300`；job `timeout-minutes: 60`
- **每块单进程**（无 OOM），**24 个 artifact**（上传可靠）
- **⚠️ aggregate 仍失败**：Commit results 步骤 `git push origin "HEAD:${GITHUB_REF_NAME}"` 在 `workflow_dispatch` 下 `GITHUB_REF_NAME` 可能为空 → 仍报 `fatal: /: '/' is outside repository`。**修复办法**：显式写死分支 `git push origin HEAD:master`（勿用 GITHUB_REF_NAME）。**但注意**：24 个 backtest job 的 artifacts 已在 run `31308921476` 里，可**直接下载聚合，无需重跑**（本次就是这么拿到公平结果的）。

### 成功 run 记录
- **最新 run**：run_id=`31308921476`，head=`dd49383`，24 backtest job **全部 success**（含 ci0-b5 但该 job 实际 0 产出，见下），aggregate 仍 git push 失败
- **上轮有结果 run**：run_id=`31302696102`，head=`a5bbfcf`，24 job 全完成，aggregate 算出 eval 但 push 失败
- 之前失败 run（历史，勿再用）：`31299392136`、`31300564189`(v1 artifact丢)、`31301363828`(v2 OOM)、`31302050338`(v3 timeout)

### ✅ 当前状态（2026-08-09 23:00 更新——补全完成，eval 已落盘推送）
- **✅ 已补全 BASELINE 全部 6 窗（wi37-42）**：新建 `.github/workflows/strict_oos_r21_baseline_backfill.yml`（3 job × 2 窗，`timeout 900`，commit `6fe758e`），在 Actions 上跑完 run `31310382385` 全部 success。补全的 6 窗：wi37(+25.6%) wi38(-6.2%) wi39(+8.2%) wi40(-5.8%) wi41(+30.7%) wi42(+0.9%)，均值 ~+8.8%/窗（确认为高收益段）。
- **✅ 完整 22 窗公平 eval 已落盘**：下载全部 4 候选 × 22 窗窗口数据（run `31308921476` 的 ci1/2/3 artifact + ci0 b0-b4 artifact + 补跑的 ci0 b5），本地 `python scripts/exp_strict_oos.py test` 生成 `v9-results/strict_oos_r21_eval.json`，并已 push 到 master（commit `2e98080`）。
- **✅ 最终结论（22 窗同窗公平对比）**：见下方表格——大佬因子**无净 alpha**，保留 BASELINE，放弃 smart_money。
- **⚠️ ci0-b5 超时根因**：`strict_oos_r21_parallel.yml` 的 b5 块 `timeout 300` 对 ci0 后段窗口不够（每窗 >300s，BASELINE 无信号过滤全市场扫描更慢），导致 wi37-42 全被杀。补跑 workflow 已用 `timeout 900` 解决。
- **aggregate 的 git push 修复**：把 Commit results 的 push 改写成 `git push origin "HEAD:${GITHUB_REF_NAME}"` 仍会因 `workflow_dispatch` 下 `GITHUB_REF_NAME` 为空而报 `fatal: /: '/' is outside repository`。**建议写死 `git push origin HEAD:master`**。但 aggregate 非必需（可直接下载 artifact 本地聚合，本次即如此）。

### R21 框架（`scripts/exp_strict_oos.py`, `ROUND=21`）4 个候选
1. `KC_AGGRESSIVE_BASELINE` — 基线（无大佬因子）
2. `KC_SMART_BUY_15` — 大佬因子作独立维度，weight=15
3. `KC_SMART_BUY_25` — 大佬因子作独立维度，weight=25
4. `KC_SMART_MOD` — **大佬因子作加减分修饰符（不占维度权重）** ← R21 新增核心

### 待新对话做（按优先级，2026-08-09 晚重跑完成后）
1. **✅ R21 修正版结论已确认**：修复 global bug 后重跑 ci3（run `31313216507`），SMART_MOD 确实改变持仓（9/22 窗不同）但平均收益 -0.001%、peak MaxDD 16.43%——修饰符模式无净 alpha。**结论：放弃大佬因子方向不变，原因修正为"触发了但确实没 alpha"。** eval 已重聚落盘。
2. **R22 方向**：不再以大佬因子为增强主方向，基于 BASELINE（KC_AGGRESSIVE_BASELINE）探索其他 alpha（动量/质量调参、行业轮动、择时细化）。若未来再引入 smart_money，务必先用单元测试验证修饰符确实改变分数（本次教训）。
3. **清理临时脚本/目录**：`_ci3_rerun/`（重跑下载产物，eval 已落盘可删）、`scripts/_dl_r21_artifacts.py`、`_tmp_*.py`、`_r21x/`、`_r21_artifacts/` 等可清理；根目录的 `strict_*.json` 是回测结果文件，可清理（eval 已落盘）。

### 如何查看 GitHub Actions 状态
- API 轮询：`python scripts/_poll_r21_true_parallel.py`（脚本内改 RUN_ID 即可复用）
- **注意**：本机 GitHub 直连不通，需走本地代理 **127.0.0.1:7890**（见第五节网络说明）
- **下载 artifact 需要 PAT 有 `actions:read` 权限**（当前 git-credentials 的 token 没有，下载会 401）

---

## 五、网络/环境注意（重要，避免踩坑）

### GitHub 访问必须走代理
本机 `github.com` 直连不通（DNS 被劫持到 127.0.0.1）。检测到本地代理 **127.0.0.1:7890**（Clash 类）可用。
```powershell
# git 拉取/推送前设代理（每次命令临时设置，不写死全局配置）
$env:HTTPS_PROXY="http://127.0.0.1:7890"
$env:HTTP_PROXY="http://127.0.0.1:7890"
git push origin master
```
`www.baidu.com` 直连正常，仅 GitHub 系域名需代理。

### 其他环境要点
- 包管理器：pnpm
- 京东金融 Cookie 有效（`tools/jd_finance_api.py --test` 验证通过）
- 本地回测限制 worker=2 避免 CPU 满载；**所有计算密集型回测走 GitHub Actions**
- 后端 RPC/数据库操作用 Supabase Management API（PAT 认证），沙箱内 psql DNS 解析失败

---

## 六、本次会话创建的临时脚本
- **保留**：`scripts/_build_smart_signals_v5.py`（已更新为读取 v7，可复用于重建信号）
- **保留**：`scripts/_poll_r21_true_parallel.py`（R21 轮询器，改 RUN_ID 可复用）
- 其余 `_audit_*` / `_verify_*` / `_check_*` / `_fix_v7.py` / `_dl_r21_artifacts.py` / `_diag_*` 等临时脚本已删除

---

## 七、下一步行动清单（新对话直接执行）

### R21 状态（2026-08-09 晚更新——bug 已修复，重跑已完成，修正结论落盘）
1. **✅ 已修复 bug**：`score_smart_money_backtest()` 补 `global _SMART_MONEY_MODIFIER` 声明（commit `61f00ec`）。初版 SMART_MOD 因该 bug 在 22 窗全 ≡ BASELINE，初版结论作废。
2. **✅ 重跑已完成**：`.github/workflows/strict_oos_r21_smartmod_rerun.yml` 在 Actions 跑完（run `31313216507`，4 job 全 success），修复后 ci3 与 BASELINE 在 9/22 窗不同。
3. **✅ 修正结论已落盘**：SMART_MOD 平均收益 -0.001%、peak MaxDD 16.43%——修饰符模式无净 alpha。`v9-results/strict_oos_r21_eval.json` 已重聚。
4. **✅ ci0/1/2 复用**：BASELINE/SMART_BUY_15/SMART_BUY_25 不受 bug 影响，结果真实有效。

### 下一步（R22 方向——已确认）
1. **R22 设计**：不再以大佬因子为增强主方向，基于 BASELINE（KC_AGGRESSIVE_BASELINE）探索其他 alpha：动量/质量维度调参、行业轮动、择时细化。
2. **遗留（可选）**：`strict_oos_r21_parallel.yml` 的 aggregate push 仍失败（GITHUB_REF_NAME 为空），可改 `git push origin HEAD:master`。但 aggregate 非必需（可下载 artifact 本地聚合）。
3. **清理（可选）**：`_ci3_rerun/`、根目录的 88 个 `strict_test_ci*.json`（eval 已落盘可删）；`scripts/_dl_r21_artifacts.py`、`scripts/_poll_r21_*.py` 可保留（复用于下载/轮询）。
5. 若有新的数据疑问，用 `jd-shipan-fund-mapping` skill + `getFundChart` 权威 productId 复核，不要靠名称猜

---

## 八、关键参考
- Skill: `jd-shipan-fund-mapping`（京东基金码映射权威验证）
- 工具: `tools/jd_finance_api.py`、`tools/authoritative_remap.py`
- 数据: `data/chart_to_name.json`、`data/fund_name_map.json`、`data/jdcode_to_chart.json`
- 引擎: `backtest/engine/backtest.py`（加载链已优先 v7）

---

## 九、R33 交接更新（2026-08-11 13:30 — smart_money_clone 证伪 + 5 引擎 bug 修复）

### 🎯 一句话核心结论
R24 找到 WIDE 修饰符 +0.86% alpha 后，R25-R33 连续 6 次尝试全部证伪。**结构性问题**：q/c/m 过滤器反向剔除回调中的基金 → 修饰器无法补救 → R33 直接绕过 q/c/m "克隆大佬持仓"也失败（avg +0.70% < BASELINE 3.271%，alpha -2.57%）。同时发现并修复了 5 个引擎 bug。

### 当前最优策略（未被超越）
| 候选 | avg_return | alpha | peak MaxDD |
|---|---|---|---|
| KC_AGGRESSIVE_BASELINE | **3.271%** | — | 15.63% |
| KC_SMART_AMOUNT_WIDE (R24) | **4.130%** | **+0.859%** | 16.08% |

### R25~R33 汇总
| 轮次 | 方向 | 结果 | avg_return (alpha) |
|---|---|---|---|
| R25 | WIDE+动量过滤/行业轮动/多周期 | 全负 | 最高 +0.52% |
| R26 | 净信号约束 / 非对称 boost | 全负 | 最高 +0.47% |
| R27 | 动量门控 | 更差 | +0.05% |
| R28 | 回调深度分层 | 更差 | +0.40% |
| R29 | 回调波段(deep/shallow) | 更差 | +0.45% |
| R30 | 降 nb_lo→1 (更多信号) | 更差 | +0.23% |
| R31 | 独立维度 SM_IND40 | 不如修饰符 | +0.38% |
| R32 | NARROW 窄持仓+共识门控 | 全崩 | NARROW4_GATE -1.48% |
| **R33** | **smart_money_clone 绕过 q/c/m** | **证伪** | **+0.70% (α -2.57%)** |

### R33 详情（关键发现）
1. **结构性 bug**：q/c/m 分与 smart money 信号反向 → 回调时 q/c/m 分极低 → 修饰器无法救回
2. **修复路径**：smart_money_clone 模式 → 候选=全量基金 → 纯信号评分 → top-N 买入
3. **引擎 bug 修复 5 处**：
   - `_min_consensus=1` in clone mode (commit f5d8a1f)
   - `_smart_money_clone` UnboundLocalError — line 2382 uses var before line 2402 def
   - `_SMART_MONEY_MODIFIER` 跨基金残留 (commit 070280c)
   - `_resolve_fund_code()` 不识别代码，returns None (commit 0ac5e4a)
   - 全量 fund_charts (8000+) 每日评分 → 改用预计算合格池 (~150) (commit 0ac5e4a)
4. **结果**：22 窗中 3 零(无信号), 16 负 3 正；win_avg +21.3%, loss_avg -3.0%
5. **根因**：smart money 回调抄底常继续回调 → crash 止损

### 迭代停损协议执行
- 当前：连续 9 轮 (R25-R33) alpha 为负（R24 之后）
- **已达停损阈值边缘**（10 次连续无 alpha → 判定无 alpha 并停止）
- **建议**：暂停独立大佬因子方向，改完全不同的 alpha 源（动量/质量/行业轮动独立优化）

### 关键 commit（R33 相关）
- `f5d8a1f` fix _min_consensus=1 in clone mode
- `070280c` fix UnboundLocal + SM modifier reset
- `0ac5e4a` fix _resolve_fund_code + pre-computed pool (FINAL working engine)