# Spec 12: 现有 Skills 整合

## 背景
ai-berkshire 已有 25 个投研 Claude Code Skill（skills/目录），其中 7 个是基金专用。

## 附着点图

```
Pipeline Task 完成 → EventBus.emit()
    │
    ├── scoring 完成 → 触发 fund-scan 做人工可读的扫描报告
    ├── decision 完成 → 触发 fund-sell/fund-trade 做操作确认
    ├── quarterly 发布 → 触发 fund-quarterly/fund-penetration 做深度分析
    ├── news 更新 → 触发 news-pulse 做新闻解读
    ├── nav 更新 → 触发 fund-monitor 检查持仓变化
    └── 晚间空闲 → 触发 investment-checklist/fund-checklist 做全局检查
```

**重要：** Skills 是交互式 LLM 工作流，不可直接融入回测（用LLM判断历史数据=泄露未来信息=作弊）。

## Skills 分类整合

### 可被 Pipeline 触发的 Skill（7个）

| Skill | 触发时机 | 输出 | 能否回测 |
|-------|---------|------|---------|
| fund-monitor | holdings_updated事件 | 持仓变化报告 | ❌ 不能 |
| fund-scan | 候选池更新 | 定性分析报告 | ❌ 不能 |
| fund-checklist | DecisionEngine结果 | 买入前六关确认 | ❌ 不能 |
| fund-sell | DecisionEngine卖出建议 | 卖出确认报告 | ❌ 不能 |
| fund-trade | DecisionEngine买入建议 | 交易执行确认 | ❌ 不能 |
| fund-quarterly | quarterly_report事件 | 季报解读 | ❌ 不能 |
| fund-penetration | quarterly_report事件 | 穿透分析 | ❌ 不能 |

### 独立投研 Skill（不自动化，用户按需调用）

| Skill | 用途 | 建议频率 |
|-------|------|---------|
| investment-team | 4Agent并行研究 | 新标的研究 |
| investment-research | 单标的深度研究 | 新标的研究 |
| earnings-review | 财报精读 | 财报季 |
| earnings-team | 团队财报解读 | 财报季 |
| management-deep-dive | 管理层研究 | 季报后 |
| industry-research | 行业研究 | 季度 |
| industry-funnel | 行业漏斗筛选 | 季度 |
| portfolio-review | 组合审视 | 月度 |
| thesis-tracker | 投资论文追踪 | 季度 |
| news-pulse | 股价异动快速归因 | 异动时 |

## 整合方式（不需要改 skill 文件）

在 Pipeline 中新增一个 `task_skill_dispatcher.py`：

```python
class SkillDispatcher:
    """根据事件类型，建议用户运行哪个 Skill（不自运行，因为Skill是交互式）"""

    def suggest_on_decision(self, decision: DecisionResult) -> Optional[str]:
        """决策完成后建议用户运行:
           买入→"建议运行 /fund-checklist 确认"
           卖出→"建议运行 /fund-sell 确认" """

    def suggest_on_quarterly(self, fund_code: str) -> List[str]:
        """季报发布后建议:
           "/fund-penetration 穿透分析持仓"
           "/fund-quarterly 追踪历史持仓变化" """

    def suggest_on_news(self, news_items: List[str]) -> Optional[str]:
        """重大新闻→"/news-pulse" """
```

## 回测与 Skills 的关系（关键约束）

**Skills 不能回测，因为：**
1. LLM 非确定性 → 同一输入两次结果不同
2. LLM 有训练数据截止日期 → 用当前知识判断历史 = 泄露未来信息
3. 交互式 Workflow → 需要用户参与，无法自动化

**解决方案：**
- 回测只用程序化模块（fund_scorer / fund_rules / fund_planner）
- Skills 作为"决策后的人工确认层"，在生产运行中做定性分析和解释
- Skills 的输出（报告/分析）存入 RAG，供 Future AI 参考