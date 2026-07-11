---
name: fund-scan
description: "对关注的大佬进行一站式分析：抓持仓→交易流水→信号合并→基金Checklist→四大师投资评价→输出HTML报告。"
user-invocable: true
# Original frontmatter from skills/fund-scan.md:
#   name: fund-scan
#   user-invocable: true
#   description: "一句话全流程分析：抓数据→信号→Checklist→四大师评价→输出HTML报告"
---
## OpenCode adapter note

This skill is generated from `skills/fund-scan.md` — the canonical source.

- Treat `$ARGUMENTS` as the user's request in the current session.
- When the source references Claude-only tool names (Task, Agent, etc.), use the closest capability available in your environment.
- Commands reference `python3 tools/...` — use the correct Python path for your shell.
- Preserve the research quality rules from `AGENTS.md`: cross-check financial data, use exact arithmetic, label uncertainty.

# 基金全流程扫描

对关注的大佬进行一站式分析：抓持仓→交易流水→信号合并→基金Checklist→四大师投资评价→输出HTML报告。

## 一句话触发

"分析今天基金操作" / "看看大佬买卖什么" / "基金全流程扫描" / "fund-scan"

## 执行流程

### Phase 0：前置检查

检查 `data/jd_auth/cookies.json` 是否存在且有效。
- 无效 → 提示用户重新登录
- 有效 → 继续

### Phase 1：抓取数据

```bash
cd c:/项目/A基金/ai-berkshire-main
python scripts/auto-pipeline.py
python scripts/generate_report.py
```

读取输出：
- `reports/auto/latest.md` — 监控报告
- `data/auto/status.json` — 管道状态

### Phase 2：解析结果

从报告中提取：
- 今日买入最多的基金（前10）
- 强共识基金名单
- 大佬活跃度排行
- 用户本年收益排名（从快照提取）

### Phase 3：四大师评价（仅针对强共识基金）

对 **strong_buy（≥3人买入）** 的每只基金，调用四大师视角分析：

| 角色 | 评估维度 |
|------|---------|
| 段永平视角 | 商业模式+护城河（基金底层持仓的生意质量） |
| 巴菲特视角 | 财务面+估值（费率、历史业绩、穿透持仓估值） |
| 芒格视角 | 行业竞争+风险（基金赛道拥挤度、管理人能力） |
| 李录视角 | 管理层+治理（基金经理背景、公司治理） |

数据来源：已经自动生成的 Checklist 报告在 `reports/fund-checklist/{代码}/checklist-{日期}.md`。

### Phase 4：生成 HTML 报告

输出一份独立 HTML 到 `reports/auto/scan-{日期}.html`，包含：

1. 用户收益率排名（柱状图）
2. 买入信号汇总表（基金名、共识人数、代码、费率摘要、限额）
3. 每只强共识基金的四大师评价卡片
4. 建议操作策略：
   - A类/C类推荐
   - 限购情况说明
   - 建议金额（参考日限额）
   - 定投/一次性策略
5. 风险提示

### 第四步：呈现

直接展示 HTML 给用户或告诉用户报告位置。

## 注意事项

- cookie 先验证，过期直接提示
- 四大师评价基于 Checklist 数据，不做重复 API 调用
- HTML 报告使用内联 CSS，独立文件，浏览器可直接打开
