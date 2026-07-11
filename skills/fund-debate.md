---
name: fund-debate
user-invocable: true
description: "多视角基金辩论——看多/看空/中立三方分析同一只基金"
---

# 基金多视角辩论

对 $ARGUMENTS 基金执行三方辩论分析。

## 输入

读取 `tools/fund_scorer.py` 的评分数据和 `tools/fund_rules.py` 的规则结论。

执行:

```bash
python tools/fund_scorer.py --score CODE
python tools/fund_rules.py --analyze CODE
```

## 输出

### 看多视角
- 强调超额收益来源、经理经验优势、持仓行业景气度
- 引用评分中得分最高的维度
- 客观不夸大

### 看空视角
- 强调回撤风险、风格漂移可能性、费率偏高
- 引用评分中得分最低的维度
- 指出潜在风险点

### 中立视角
- 综合双方观点
- 给出客观的平衡分析
- 指出数据不确定性和局限

## 约束
- 三方各自独立分析，不互相影响
- 不输出分数，不输出买卖建议
- 有数据分歧时明确标注