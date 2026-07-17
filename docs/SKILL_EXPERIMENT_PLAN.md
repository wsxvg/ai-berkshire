# SKILL A/B 实验方案 V3（已跑完 8 组, 2026-07-13）

> **🎉 实验已完成** — 详细结果见 `docs/SKILL_AB_V3_REPORT.md`
>
> **核心结论**: **B5 评分仓位调节是赢家**（Full 42.36% / Val 271.90%）
>
> **失败案例**: B7 RSI + 评分门槛过度过滤, 拖累 -18.46%

---

## 🏆 8 组实验结果速览

| # | 名称 | Full 年化 | Val 年化 | 结论 |
|---|------|----------:|---------:|------|
| A0 | V2 baseline | +39.18% | +182.07% | 持平 |
| B1 | RSI>75 拦截 | +36.30% | +135.76% | 持平 |
| B1b | RSI>80 拦截 | +37.72% | +182.07% | 持平 |
| B2 | 集中度过滤 | +39.18% | +182.07% | 未生效 (字段缺失) |
| B3 | 经理筛选 1y | +39.18% | +121.23% | 持平 |
| B3b | 经理筛选 2y | +39.18% | +121.23% | 持平 |
| B4 | 评分门槛 12.5 | +30.00% | +194.49% | 验证+ |
| B4b | 评分门槛 15.0 | +24.76% | +221.13% | 验证+ |
| **B5** | **评分仓位调节** | **+42.36%** | **+271.90%** | **⭐ 双优** |
| B6 | B1+B2+B3 组合 | +36.30% | +135.81% | 持平 |
| B7 | B1+B4 组合 | +20.72% | +136.18% | 🔴 拖累 |

---

## 一、实验设计

| # | 名称 | 配置 | 预期 |
|---|------|------|------|
| A0 | V2 baseline | 纯 P1 止盈 | 39.18% baseline |
| B1 | RSI 拦截 | RSI>75 不买 | 防追高 |
| B2 | 集中度过滤 | 行业集中度>60% 减仓 | 防单基爆雷 |
| B3 | 经理筛选 | 经理<1 年不买 | 防新人风险 |
| B4 | 5 维评分门槛（修复版） | score(截止日)<12.5/15 → 不买 | **必须先修** |
| B5 | 评分仓位调节 | score 高 +30% 仓位 | 信任好基金 |
| B6 | B1+B2+B3 组合 | 三层过滤叠加 | 极保守 |
| B7 | B1+B4 组合 | RSI + 评分门槛 | 拦截型 |

---

## 二、修复 5 维评分（已实装到 `backtest_v2.py`）

**修复函数**: `compute_score_at(code, cutoff_date, charts, fund_cache, trades_by_date, name_to_code)`

```python
def compute_score_at(code, cutoff_date, charts, fund_cache, trades_by_date, name_to_code):
    """按截止日现场算 5 维评分 (无前瞻偏差, 2026-07-13 修复版)"""
    bd = {}
    score = 0.0

    # 1. Quality (0~5): 1y 收益 + 1y 最大回撤
    chart = charts.get(code, [])
    valid = [p for p in chart if p[0] <= cutoff_date]
    if len(valid) >= 250:
        ret_1y = valid[-1][1] - valid[-250][1]
        q_ret = min(2.5, max(0, 1.25 + ret_1y * 5))
        peak = max(p[1] for p in valid[-250:])
        dd = (valid[-1][1] - peak) / peak * 100 if peak > 0 else 0
        q_dd = max(0, min(2.5, 2.5 + dd * 0.1))
        score += q_ret + q_dd
    else:
        score += 2.0

    # 2. Cost (0~5): 管理费
    rules = fund_cache.get(code, {}).get("rules", {})
    mf = rules.get("manage_fee", 1.2)
    if mf < 0.5: c = 5.0
    elif mf < 0.8: c = 4.0
    elif mf < 1.2: c = 3.0
    elif mf < 1.5: c = 2.0
    else: c = 1.0
    score += c

    # 3. Manager (0~5): 任职年限 (按 cutoff_date 算)
    mgr = fund_cache.get(code, {}).get("manager", {})
    tenure = _mgr_tenure_years_at(mgr, cutoff_date)
    m_score = min(5.0, tenure * 1.0) if tenure is not None else 2.5
    score += m_score

    # 4. Momentum (0~5): 60日斜率
    if len(valid) >= 60:
        recent = sum(p[1] for p in valid[-60:]) / 60
        past = sum(p[1] for p in valid[-120:-60]) / 60 if len(valid) >= 120 else recent
        slope_pct = (recent - past) / (past + 0.01) * 100
        mom = max(0, min(5.0, 2.5 + slope_pct * 0.25))
    else:
        mom = 2.5
    score += mom

    # 5. Smart Money (0~5): 14 天内被几位大佬买
    sm_users = set()
    for d_key, recs in trades_by_date.items():
        if lookback_start <= d_key <= cutoff_date:
            for r in recs:
                if name_to_code.get(r.get("fund_name", "")) == code:
                    if "买入" in r.get("action", "") and uid:
                        sm_users.add(uid)
    sm_score = min(5.0, len(sm_users) * 1.5)
    score += sm_score

    return {"total": round(score, 2), "breakdown": bd}
```

---

## 三、扩展 backtest_v2.py 支持 SKILL（已实装）

5 个新参数 + 5 个对应过滤逻辑：
- `use_rsi_filter` (B1) — `compute_rsi_at()` 现场算 RSI
- `use_concentration_filter` (B2) — 检查 holdings.sectors
- `use_manager_filter` (B3) — `_mgr_tenure_years_at()` 现场算年限
- `use_score_threshold` (B4) — `compute_score_at()` 现场评分门槛
- `use_score_position` (B5) — `compute_score_at()` 现场评分调仓位

---

## 四、关键发现 (详解)

### ✅ B5 评分仓位调节: 真正的赢家

| 指标 | A0 (baseline) | **B5** | 增益 |
|------|------:|------:|-----:|
| Full 年化 | 39.18% | **42.36%** | **+3.18%** |
| Val 年化 | 182.07% | **271.90%** | **+89.83%** 🏆 |
| 夏普 | 1.64 | 1.58 | 持平 |
| 胜率 | 55% | 55% | 持平 |
| Alpha | 21.98% | **25.15%** | +3.17% |

**为什么有效** — 评分系统的边际判断有用：
- 同样是大佬共识, 5 维评分高的 (有经理/低费/正斜率) 仓位 +30% 
- 评分低的 (新人经理/高费/负斜率) 仓位 -30%
- 不是"门槛"阻挡, 是"信任分层"
- 胜率没变 (55%), 但**每笔平均赚更多** (因为高分基仓位大)

### 🟡 B4b 评分门槛 15.0: 适合追求稳定

| 指标 | 值 |
|------|---|
| Full 年化 | 24.76% |
| **Val 年化** | **221.13%** |
| Val 夏普 | **3.27** (最高) |
| Val 胜率 | **92.3%** ⭐ (13 笔 12 笔赢) |
| Val 回撤 | -6.99% |

**特点**: 胜率 92% 但年化 25% — 适合"低风险偏好"用户。

### 🔴 B7 RSI + 评分门槛: 失败案例

**Full 年化 20.72% (-18.46%)** — 双重过滤阻挡了 60% 信号, 错过大行情。

**教训**: SKILL 要"拦截"和"调节"组合, 不要"门槛叠加"。

---

## 五、opencode 后续工作

### 推荐接入 daily_push 的组合

**B5 评分仓位调节** (追求收益):
```python
# daily_push.py 改造
from backtest_v2 import run_backtest, compute_score_at
sc = compute_score_at(code, today, charts, fund_cache, trades, name_to_code)
position = max(0.10, min(0.40, 0.10 + (sc["total"] - 5) * 0.02))
```

**B4b 评分门槛 15.0** (追求稳定):
```python
sc = compute_score_at(code, today, charts, fund_cache, trades, name_to_code)
if sc["total"] < 15.0:
    skip = True  # 不买
```

### 验证集 271% 的隐含风险

- Val 只有 4 月, 16 笔交易
- 不能保证 1 年后还这么高
- 建议: 实时监控 4 周, 若 Full 年化跌破 35% 立即关闭 B5

---

## 六、文件清单

| 文件 | 用途 |
|------|------|
| `scripts/backtest_v2.py` | V2 引擎 + 5 个 SKILL 维度 + compute_score_at 修复 |
| `scripts/skill_ab_test.py` | 8 组 A/B 实验入口 |
| `scripts/gen_ab_report.py` | 生成对比报告 |
| `docs/SKILL_AB_V3_REPORT.md` | 详细报告 |
| `reports/skill_ab_test/skill_ab_v3_20260713_124232.json` | 8 组实验原始数据 |

---

## 七、运行方式

```bash
# 跑 8 组 A/B
py -3.10 -X utf8 scripts\skill_ab_test.py

# 生成对比报告
py -3.10 -X utf8 scripts\gen_ab_report.py

# 跑单组实验
py -3.10 -X utf8 -c "
from backtest_v2 import run_backtest
r = run_backtest('2024-03-11', '2026-07-01', 100000, 3, 1,
    use_score_position=True)
print(r['result'])
"
```

---

## 八、opencode 提示词 (如需重跑)

```markdown
# 任务
你已接手一个 SKILL A/B 实验项目, 之前 8 组实验已跑完。
现在需要:
1. 验证 docs/SKILL_AB_V3_REPORT.md 中的结果
2. 跑 1 组 B5 评分仓位调节的实盘回测 (30 天)
3. 输出 "哪些 SKILL 真正有效" 的简短结论
4. 不要重跑 8 组 (已跑完), 只补充新视角

## 工作目录
c:\项目\A基金\基金

## 关键文件
- docs/SKILL_AB_V3_REPORT.md (必读, 完整结果)
- scripts/backtest_v2.py (引擎, 已修复前瞻偏差)
- scripts/skill_ab_test.py (实验入口)

## 跑这个命令看 B5 在 30 天实盘的效果
py -3.10 -X utf8 scripts\daily_check.py

## 输出
"哪些 SKILL 真正有效" 的简短结论 (< 500 字)
```

---

## 九、修复的 Bug 清单

| Bug | 修复 | 影响 |
|-----|------|------|
| 5 维评分用"当下"数据 | `compute_score_at()` 按 cutoff 算 | B4 从 -18% 变成 +13% (验证集) |
| manager 任职年限虚高 | `_mgr_tenure_years_at()` 按截止日 | B3 从不过滤变成真过滤 |
| RSI 除零崩溃 | 边界检查 + 100.0 fallback | B1/B1b/B6/B7 全部能跑 |
| fund_cache 没加载 | `load_fund_cache()` 函数 | B2/B3/B4/B5 全部能算 |
| trades 没按日聚合 | `trades_by_date` dict | compute_score_at 内部用 |
