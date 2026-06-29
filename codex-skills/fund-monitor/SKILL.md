---
name: fund-monitor
description: "AI Berkshire skill: 场外基金大佬持仓监控. Source: skills/fund-monitor.md."
---

## Codex adapter note

This skill is generated from `skills/fund-monitor.md` so Claude Code and Codex users share one canonical workflow.

- Treat `$ARGUMENTS` as the user's request in the current Codex thread.
- When the source mentions Claude-only surfaces such as Task, Agent, WebSearch, Bash, Read, or Write, use the closest Codex capability available in this session: subagents when available, web search when needed, shell commands for local tools, and normal file edits for workspace files.
- Use shared project tools from `tools/` in this repository. Commands that reference `~/ai-berkshire/tools/...` assume the repo is checked out at `~/ai-berkshire`; if needed, prefer the current workspace path.
- Preserve the research quality rules from `AGENTS.md`: cross-check financial data, use exact arithmetic tools for valuation/math, and clearly label uncertainty and source gaps.

# 场外基金大佬持仓监控

监控 11 位关注大佬的持仓变化，识别共识信号，自动触发基金分析。

**支持参数**：`--user {uid}` 仅监控指定用户 | `--offline` 离线模式 | 默认全量监控

## 执行流程

### 第一步：获取关注人列表

使用内置的 11 位关注人映射（tools/jd_finance_api.py FOLLOWED_USERS）：

| 用户名 | numeric_id | uid |
|--------|-----------|-----|
| 蓝鲸跃财 | 3546208 | jimu_user_info-3546208 |
| Z先生养基 | 14345330 | jimu_user_info-14345330 |
| 王晴阳的活财之路 | 16020895 | jimu_user_info-16020895 |
| 黑夜银翼 | 2690580 | jimu_user_info-2690580 |
| 南山隐士 | 4063754 | jimu_user_info-4063754 |
| 赚自己认知内的钱 | 3642504 | jimu_user_info-3642504 |
| 晴空万里理财 | 3748946 | jimu_user_info-3748946 |
| 小猫咪爱黄金 | 10458335 | jimu_user_info-10458335 |
| 家庭的温暖 | 11979538 | jimu_user_info-11979538 |
| 西西的金算盘 | 4968958 | jimu_user_info-4968958 |
| 招财小猫 | 11953905 | jimu_user_info-11953905 |

如果指定 `--user` 参数，仅监控该用户的numeric_id。

### 第二步：批量获取最新持仓

```bash
python3 tools/jd_finance_api.py --batch-holdings
```

或逐人获取：
```bash
python3 tools/jd_finance_api.py --holdings jimu_user_info-{uid}
```

### 第三步：对比快照，识别变化

1. 从 `data/fund_snapshots/` 加载上次快照
2. 与本次持仓对比，识别：
   - **新增持仓**（大佬新买了什么基金）→ 标记为 ⭐ 重点关注
   - **增持**（持仓金额增加）→ 标记为 ↑
   - **减持**（持仓金额减少）→ 标记为 ↓
   - **清仓**（从持仓中消失）→ 标记为 ⚠️ 警告
   - **无变化** → 标记为 =

### 第四步：识别共识信号

统计所有关注人的持仓变化，识别：

| 信号类型 | 判断标准 | 信号强度 |
|---------|---------|---------|
| 多人新进 | ≥3人同时新买同一只基金 | ⭐⭐⭐ 强烈 |
| 多人加仓 | ≥3人同时增持同一只基金 | ⭐⭐ 中等 |
| 大额买入 | 单笔买入 > 1万元 | ⭐⭐ 中等 |
| 大佬清仓 | 有人全卖了 | ⚠️ 风险信号 |
| 分歧信号 | 有人买有人卖同一只基金 | ❓ 需深入分析 |

### 第五步：输出监控报告

报告保存到 `reports/大佬持仓监控/` 目录：

```
reports/大佬持仓监控/monitor-{YYYYMMDD}.md
```

#### 报告格式

```markdown
# 大佬持仓监控报告

> **监控时间**：{日期}
> **监控人数**：{N}人
> **数据来源**：京东金融API（tools/jd_finance_api.py）

---

## 一、持仓变化摘要

### 新增持仓（大佬新买了什么）
| 基金 | 买入大佬 | 信号强度 | 建议 |
|------|---------|---------|------|
| {基金名} | {大佬1}、{大佬2} | ⭐⭐⭐ | 触发 /fund-checklist |

### 减持/清仓
| 基金 | 操作大佬 | 说明 |
|------|---------|------|
| {基金名} | {大佬1} | 减持50% |

---

## 二、共识信号排行

| 基金 | 买入人数 | 总金额 | 信号强度 | 建议 |
|------|---------|--------|---------|------|
| {基金1} | 5人 | {金额} | ⭐⭐⭐ | 强烈推荐分析 |
| {基金2} | 3人 | {金额} | ⭐⭐ | 值得关注 |

---

## 三、各大佬最新持仓

### {大佬名1}
| 基金 | 金额 | 收益率 | 变化 |
|------|------|--------|------|
| ... | ... | ... | ... |

### {大佬名2}
...

---

## 四、建议操作

### 建议分析的基金（按优先级）
1. **{基金名}** — {N}位大佬同时新进，建议执行 /fund-checklist
2. ...

### 需要关注的风险
- {大佬名} 清仓了 {基金名}，建议检查是否存在风险
- ...
```

### 第六步（并行）：全市场前置信号检测

> 此步骤与持仓监控并行执行，扫描范围涵盖**持仓基金+候选基金**，输出预警信号供 `fund-sell` 读取。

对每个被关注的基金（从 `data/fund_snapshots/` 缓存中获取持仓+候选列表），按以下顺序检查：

| 检测项 | 检测逻辑 | 数据来源 | 预警级别 |
|--------|---------|---------|:-------:|
| **基金经理变更** | 对比缓存中的经理姓名与 `getFundManagerListPageInfo` 实时返回的姓名 | `--fund-manager {code}` | 🔴 红色（主动型/指增） |
| **基金规模<5000万** | `getFundDetailProfilePageInfo` 返回的规模<5000万 | `--fund-profile {code}` | 🔴 红色 |
| **基金规模异常暴增** | 季度环比+200%以上（仅主动基金） | `--fund-profile {code}` | 🟡 黄色 |
| **费率变化** | 管理费/托管费/销售服务费与缓存不一致 | `--trade-rules {code}` | 🟡 黄色 |
| **投资范围变更** | 投资策略/投资范围字段与缓存不一致 | `--fund-profile {code}` | 🟡 黄色 |
| **基金公司负面** | 从新闻/公告抓取的基金公司重大事件 | 外部信源 | 🔴 严重 / 🟡 轻微 |
| **投研团队动荡** | 基金经理人数量减少超过上期（如从3人减到1人） | `--fund-manager {code}` | 🟡 黄色 |

#### 预警池输出

检测结果写入 `data/pre_alert_cache.json`，每日覆盖：

```json
{
  "updated_at": "2026-06-28T20:30:00+08:00",
  "red": [
    {"fund_code": "006105", "fund_name": "XXX基金", "reason": "主动型基金经理更换: 张三→李四",
     "detected_at": "2026-06-28", "severity": "red"}
  ],
  "yellow": [
    {"fund_code": "000216", "fund_name": "YYY基金", "reason": "规模异常暴增: 3亿→12亿",
     "detected_at": "2026-06-28", "severity": "yellow"}
  ],
  "watch": [
    {"fund_code": "ZZZ", "fund_name": "ZZZ基金", "reason": "投研团队动荡: 经理从3人减至1人",
     "detected_at": "2026-06-28", "severity": "watch"}
  ]
}
```

> **联动逻辑**：红色预警自动触发 `fund-sell` 对该基金执行全部四级信号检查。

---

### 第七步：保存快照

将本次持仓数据保存为快照：
```bash
python3 tools/jd_finance_api.py --save-snapshot {tag} {json_data}
```

快照保存到 `data/fund_snapshots/{tag}_{timestamp}.json`

---

## 降级模式

使用 `--offline` 参数时：
- 跳过所有京东金融API调用
- 仅使用 `data/fund_cache/` 中的本地缓存数据
- 报告中标注"数据截至 {缓存日期}，未联网更新"

---

## 注意事项

- 每日运行一次即可，持仓数据每日收盘后更新
- 大佬持仓是**季度公开**的（基金季报），但京东金融实盘功能提供了**实时可见**的持仓
- 大佬买 ≠ 你该买，大佬的仓位/期限/目标可能与你不同
- 监控报告是**参考**，不是**决策依据**
