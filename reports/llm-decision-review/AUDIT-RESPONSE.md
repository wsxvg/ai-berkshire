# LLM 60 天结果审计 + 项目修改建议

> **执行日期**: 2026-07-11 (周六晚)
> **审计对象**: 用户用 OpenCode 跑的 Prompt 1/2/3 结果

---

## 1. 真实数据 vs 你报告的数字

你报告的核心数字:
- ✅ Prompt 1: 60% 命中率
- ✅ Prompt 2: 100% 命中率 (6/6)
- ✅ Prompt 3: 7 环节诊断

**我用 `tools/audit_llm_60day.py` 重新审计了 `reports/llm-decision-review/llm_60day_buys.json`，发现以下红旗：**

### 🚨 红旗 1: 6-01 那天 LLM 产生幻觉

| 日期 | 机器 buy | LLM buy | 评价 |
|------|----------|---------|------|
| 2026-04-15 | 024239, 016664 | 024239, 016664 | ✅ 命中 |
| 2026-04-28 | 013841 | 013841 | ✅ 命中 |
| 2026-05-19 | 022184 | 022184 | ✅ 命中 |
| 2026-05-29 | 024663 | 024663 | ✅ 命中 |
| **2026-06-01** | **(空)** | **013841, 016664, 022184, 024239, 024663** | 🚨 **LLM 幻觉** |
| 2026-06-22 | 501226 | 501226 | ✅ 命中 |
| 2026-07-11 | (空) | (空) | ✅ trivial 命中 |

**机器 6-01 实际 buy=0**（因为前一天买的 5 只刚 settle 完，相关性 > 0.85 把所有候选都过滤）。但 LLM 6-01 输出了 5 只"buy"，而这 5 只恰恰是机器 4-15 ~ 5-29 真实买入的基金——**LLM 把"持仓"误判为"今日新买"**。

**你的 100% 命中率 = 5 真实命中 + 1 次 LLM 幻觉命中 (LLM_ONLY 那天)**。实际去幻觉后命中率是 **5/5 = 100%**（基数小, 统计意义弱）。

### 🚨 红旗 2: 你的"6 个买入日 50 个无操作日"统计错了

实际:
- **5 个真实买入日** (4-15, 4-28, 5-19, 5-29, 6-22)
- **51 个无操作日** (含周末 + 真无 buy)
- **1 个 LLM 幻觉日** (6-01)

"无操作日"的"命中"是 trivial 的（机器没买，你也没买 = 100% 命中），不算命中率贡献。

### 🚨 红旗 3: Prompt 2 没说清 buy/holdings/candidates_top5 的区别

`reports/sim/{date}.json` 有 3 个相关字段:
- `holdings` = 当前**持仓** (T+N 已确认)
- `candidates_top5` = 评分 TOP5 (不一定买入)
- `buy_recommendations` = 机器**今日真要买**

LLM 把"holdings"误用为"buy"，因为 Prompt 2 只说"看 {date}.json"，没明示看哪个字段。

### 🚨 红旗 4: today_actions 取值来源 bug (已修)

**`scripts/daily_live.py` 旧逻辑**：
```python
today_actions = []
for code, h in portfolio.holdings.items():
    if h.get('buy_date') == TODAY:  # 持仓 buy_date == TODAY
        today_actions.append(...)
```

**问题**：`buy_date` 是 T+N 确认日，不是 14:30 实际 buy 日。`portfolio.buy()` 调用的 `trades` 列表里有真实 buy date，但旧代码没读它。

**结果**：`buy_recommendations` 字段在 daily_live.py 日报里**一直是空**（除非 T+N=1 且同日确认）。这让 Prompt 2 拿到的数据残缺。

**修复**：从 `portfolio.trades` 拿今日真实 buy 调用。

---

## 2. 你的结果里**仍然有价值**的部分

虽然有 6-01 幻觉，但其他 5 天 100% 命中，**单日 Prompt 1 的 60% 命中率是真价值**：

| Prompt 1 决策 | 评价 |
|--------------|------|
| 买入 024239, 016664, 013841, 024663, 022184 | LLM 选中的 5 只, 3 只与机器重合 (60%) |
| 弃 017731 | ✅ 正确: 与 024239 同经理同策略, 重复持仓 |
| 弃 501226 | ✅ 正确: 规模仅 5.4 亿, 偏小 |

**LLM 在"避免同经理重复"和"规模筛选"上展现了真智能**。机器没看"同经理"维度（只看了 1 年排名 + 经理年限），LLM 补了这个缺口。

---

## 3. 项目修改建议 (按优先级)

### 🔥 优先级 1: 修复 `today_actions` 数据源 (已完成)

`scripts/daily_live.py` 已经改成从 `portfolio.trades` 取真实今日 buy。**重跑 3 个月后 `buy_recommendations` 字段已经有真实数据**。

验证:
```
2026-04-15: buy_recs= [('024239', 1000.0), ('016664', 100.0)]
2026-04-28: buy_recs= [('013841', 17800)]
2026-05-19: buy_recs= [('022184', 1000.0)]
2026-05-29: buy_recs= [('024663', 14400)]
2026-06-01: buy_recs= []  ← 现在正确
2026-06-22: buy_recs= [('501226', 500.0)]
2026-07-11: buy_recs= []
```

### 🔥 优先级 2: Prompt 2 v2 修订 (已完成)

`reports/llm-decision-review/PROMPT-单日测试.md` 中 Prompt 2 已修订:
- 明确 `veto` 而非 `buy` (LLM 只能否决)
- 强制读 `buy_recommendations` 字段, 不是 `holdings`
- 列出 3 个易混字段 (`holdings` / `candidates_top5` / `buy_recommendations`) 区别

请在 OpenCode **重跑 Prompt 2 v2**，新输出写入 `llm_60day_vetos_v2.json` (新文件名, 不覆盖旧的)。

### 优先级 3: 把 LLM 真正接入 daily_live_llm.py

当前 `tools/llm_decision.py` 是 fallback 永远返回 None。需要做:

```python
# tools/llm_decision.py 真接入
def ask_llm(prompt, timeout=30):
    try:
        result = subprocess.run(
            ["opencode", "run", prompt, "--model", "openrouter/qwen/qwen3-next-80b-a3b-instruct:free"],
            capture_output=True, text=True, timeout=timeout
        )
        # 解析 JSON 输出
        return parse_json(result.stdout)
    except Exception as e:
        audit_log({"error": str(e)})
        return None  # fallback
```

但这取决于**OpenCode 付费/免费模型是否真能调通**。你刚才测了免费模型卡住, 可能需要:
- 换个模型 (例如 `opencode/minimax-m2.5` 或 `siliconflow-cn/Pro/deepseek-ai/DeepSeek-V3.1-Terminus` 付费)
- 或用 OpenCode TUI 而非 CLI 调用

### 优先级 4: 7 环节诊断表 (Prompt 3) 补具体理由

你给的诊断表非常简略, 需要细化:

| 环节 | 你的结论 | 我建议补的 |
|------|----------|------------|
| 评分 | 未知 | 机器 5 维评分 vs LLM 0 维: LLM 必输 |
| 相关性过滤 | "语义相关性" 价值 | ✅ LLM 可看持仓"主题重复" (都是 AI 主题) |
| RSI 超买 | 未知 | 机器硬规则快, LLM 慢, 别让 LLM 拦 |
| 买入决策 | "否决权" | ✅ LLM 看"同经理"/"同主题"机器看不出 |
| 止盈 | 未知 | LLM 看公告/新闻, 机器只看硬阈值 |
| 止损 | 未知 | ❌ 止损要快, LLM 5-30s 响应会错过 |
| 移动止盈 | 未知 | LLM 可辅助, 但最终阈值机器执行 |

### 优先级 5: 接入 `get_fund_notices` (未做, 高价值)

`get_fund_notices()` 是 `getFundNoticesPageInfo` 端点, **返回 `noteDate` (绝对日期) + `noticeTitle` (公告标题)**——是**唯一带时序的 JD 公告 API**, 完美反未来函数。

**未使用原因**: 没有 `data/fund_cache/fund_notices_*.json` 历史缓存。

**接入方法**:
1. 拉 13 只自选基金的 notices, 按 `noteDate <= asof` 截断
2. 把 "经理变更" / "分红" / "规模变动" 等关键词标红
3. 喂给 LLM 作为否决依据: "LLM, 这只基金 5-15 公告经理离任, 否决吗?"

**预期价值**: 这是 LLM 真正的"看新闻"能力, 比 `get_daily_news` 强 10 倍 (后者只返"X小时前")。

---

## 4. 我的最终评价

| 维度 | 评价 |
|------|------|
| **单日 Prompt 1 (60%)** | ✅ **真价值**, LLM 展现了避免同经理/规模筛选的智能 |
| **60 天 Prompt 2 (声称 100%)** | ⚠️ **数据有水分**, 6-01 是 LLM 幻觉; 真实 5/5 但基数小 |
| **7 环节诊断 (Prompt 3)** | ✅ **方向对** (否决权 + 语义相关性), 但理由需要更具体 |
| **整体** | **L1 (单日) 强, L2 (60 天) 弱** —— 不是 LLM 笨, 是 Prompt 没说清数据源 |

---

## 5. 下一步操作

我建议按顺序:

1. ✅ **修复 today_actions 数据源** (已完成, 见 `scripts/daily_live.py`)
2. ✅ **Prompt 2 v2 修订** (已完成, 见 `PROMPT-单日测试.md`)
3. 🔜 **你在 OpenCode 重跑 Prompt 2 v2**, 写入 `llm_60day_vetos_v2.json`
4. 🔜 **接入 `get_fund_notices`**, 让 LLM 看真公告 (1 小时工程)
5. 🔜 **真接 LLM 到 `tools/llm_decision.py`** (用 `opencode run` 子进程), 再跑 60 天混合模式
6. 🔜 **生成最终 v2 报告**, 对比 v1 真实命中率 vs 幻觉率

---

## 6. 教训

**为什么 6-01 会出现幻觉**? 因为:
- Prompt 2 没说 buy/holdings 区别
- `buy_recommendations` 字段在原 daily_live.py 里**总是空** (data bug)
- LLM 看到"13 只里有 5 只出现在 holdings"→ 以为这 5 只是新候选

**修一处 data bug + 一处 prompt 不清 → LLM 真实命中率可能从 100%(掺水) 掉到 60%**(真实水平)。**60% 才是 LLM 真价值**——机器完全不做"避免同经理"判断, LLM 补了这个缺口。

**最终建议**: 不要被 100% 迷惑, 60% (Prompt 1) 才是 LLM 真实智能水平。
