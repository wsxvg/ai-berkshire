---
name: fund-analyze
user-invocable: true
description: "解读基金5维评分结果——AI解释为什么得到这个分数，不输出分数本身"
---


## 触发短语 (triggers)

以下自然语言/命令会自动触发本 SKILL:

- `基金综合分析 {代码}`
- `基金体检 {代码}`


## 必读数据

完整数据 → `docs/AI_DATA_GUIDE.md` → fund-analyze 章节

主要复用: fund-checklist + fund-penetration + fund-sell 三套数据
- `data/cache/scores.json` (评分引擎结果)
- `data/fund_cache/fund_*_<code>.json` (档案/持仓/经理/费率)
- `data/fund_charts/<code>.json` (净值/择时)

# 基金评分解读

对 $ARGUMENTS 的基金评分结果进行 AI 文本解读。

## 输入数据

从 `tools/fund_scorer.py` 和 `tools/fund_rules.py` 的输出读取：

1. 评分数据：`fund_scorer.score_fund(code)` → 5维分数
2. 规则数据：`fund_rules.analyze_all(code)` → 规则结论
3. 详细数据：`jd_finance_api.get_fund_data(code)` → 基金基本信息

## 执行流程

1. **读取评分** — 运行 `python tools/fund_scorer.py --score CODE` 获取结构化JSON
2. **读取规则** — 运行 `python tools/fund_rules.py --analyze CODE` 获取规则结论
3. **逐维解读**：
   - 质量分：排名原因、回撤控制、Sharpe比率
   - 成本分：管理费/托管费/申购费各档位
   - 经理分：任职年限、任职回报、稳定性
   - 动量分：近期趋势、均线斜率、回撤恢复
   - 聪明钱分：大佬买入/卖出共识信号
4. **规则结论解读**：
   - 清仓信号是否激活
   - 买入护盾是否生效
   - 调仓成本是否合理
5. **输出**：只输出文本解释，不输出分数，不输出买卖建议