# {基金名称} 场外基金分析报告

> **基金代码**：{基金代码}
> **分析日期**：{日期}
> **数据来源**：京东金融API（tools/jd_finance_api.py）

---

## 一、交易规则（从API实时获取）

| 项目 | 数值 | 来源 |
|------|------|------|
| 基金全称 | {full_name} | getFundDetailProfilePageInfo |
| 基金类型 | {type} | 同上 |
| 成立日期 | {established} | 同上 |
| 资产规模 | {scale} | 同上 |
| 管理人 | {manager_company} | 同上 |
| 托管人 | {custodian} | 同上 |
| 申购费率（折扣后） | {purchase_fee}% | getFundTradeRulesPageInfo |
| 申购费率（原价） | {purchase_fee_original}% | 同上 |
| 管理费率 | {manage_fee}%/年 | 同上 |
| 托管费率 | {custody_fee}%/年 | 同上 |
| 销售服务费 | {sale_fee}%/年 | 同上 |
| T+N确认 | {confirm_date} | 同上 |
| 买入截止 | {buy_date} | 同上 |
| 日累计限额 | {day_limit}元 | 同上 |
| 最低申购 | {min_purchase}元 | 同上 |

### 赎回费率分档

| 持有期限 | 费率 |
|---------|------|
| {redeem_fee_1} | {redeem_rate_1}% |
| {redeem_fee_2} | {redeem_rate_2}% |
| ... | ... |

### 实际持有成本

| 持有期 | 总成本（申购+管理+托管+销售服务） |
|--------|-------------------------------|
| 1年 | {cost_1yr}% |
| 3年 | {cost_3yr}% |
| 5年 | {cost_5yr}% |

---

## 二、基金经理

| 项目 | 数值 |
|------|------|
| 基金经理 | {manager_name} |
| 任职时间 | {manager_tenure} |
| 管理规模 | {manager_scale} |
| 总评分 | {manager_total_score} |

### 雷达评分

| 维度 | 评分 |
|------|------|
| 收益能力 | {radar_return} |
| 选股能力 | {radar_stock_pick} |
| 避险能力 | {radar_risk} |
| 机会把握 | {radar_opportunity} |
| 投资经验 | {radar_experience} |

**基金经理能力系数**：{manager_coefficient}（范围0.5~1.5）

---

## 三、历史业绩

| 周期 | 收益率 | 同类排名 | 判断 |
|------|--------|---------|------|
| 近1周 | {ret_1w}% | {rank_1w} | |
| 近1月 | {ret_1m}% | {rank_1m} | |
| 近3月 | {ret_3m}% | {rank_3m} | |
| 近6月 | {ret_6m}% | {rank_6m} | |
| 近1年 | {ret_1y}% | {rank_1y} | |
| 近3年 | {ret_3y}% | {rank_3y} | |
| 近5年 | {ret_5y}% | {rank_5y} | |
| 今年以来 | {ret_ytd}% | {rank_ytd} | |

---

## 四、底层资产穿透

### 资产配置

| 类别 | 占比 |
|------|------|
| {alloc_1} | {alloc_1_pct}% |
| {alloc_2} | {alloc_2_pct}% |
| ... | ... |

### 前10重仓股

| 股票 | 代码 | 持仓占比 | 变动 | Checklist评分 |
|------|------|---------|------|--------------|
| {stock_1} | {code_1} | {ratio_1}% | {change_1} | |
| {stock_2} | {code_2} | {ratio_2}% | {change_2} | |
| ... | ... | ... | ... | |

**穿透评估**：对每只重仓股调用 /investment-checklist 评分

---

## 五、大佬信号验证

| 关注人 | 持仓状态 | 持仓金额 | 收益率 | 信号强度 |
|--------|---------|---------|--------|---------|
| {user_1} | {status_1} | {amount_1} | {rate_1} | {signal_1} |
| {user_2} | {status_2} | {amount_2} | {rate_2} | {signal_2} |
| ... | ... | ... | ... | |

**共识信号**：{consensus_signal}

---

## 六、六关 Checklist 评分

| 关卡 | 评分(★) | 关键发现 | 是否否决 |
|------|---------|---------|---------|
| 第一关：理解 | /5 | | |
| 第二关：质量 | /5 | | |
| 第三关：经理 | /5 | | |
| 第四关：成本 | /5 | | |
| 第五关：流动性 | /5 | | |
| 第六关：聪明钱 | /5 | | |

**综合评分**：{total_score}/5

---

## 七、综合决策

### 建议
{recommendation}

### 核心理由
{reasoning}

### 风险提示
{risks}

---

> 本报告由 AI Berkshire 场外基金分析框架生成
> 数据来源：京东金融API（tools/jd_finance_api.py）
> 分析框架：skills/fund-checklist.md
