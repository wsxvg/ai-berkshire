# AI Berkshire — 项目指令

## 项目概述

基于 Claude Code 的价值投资研究 Skill 合集。四大师框架：巴菲特、芒格、段永平、李录。
GitHub: xbtlin/ai-berkshire

## 项目结构

```
skills/          — 投研 Skill 定义（.md），复制到 ~/.claude/commands/ 使用
tools/           — 辅助工具（financial_rigor.py 精确计算、jd_finance_api.py 京东金融API）
reports/         — 投资研究报告输出
data/            — 本地数据（jd_auth/认证、fund_cache/缓存、fund_snapshots/快照）
assets/          — 图片等静态资源
```

## 报告目录结构

所有报告按**公司名**建文件夹，公司相关的所有报告放在对应文件夹内：

```
reports/
├── AI产业研究/              — AI产业链全景研究（置顶）
│   ├── AI五层蛋糕-产业全景研究-20260605.md
│   └── AI五层蛋糕-公众号-20260605.md
├── 腾讯/                    — 腾讯所有研究报告
│   ├── 腾讯-research-20260408.md
│   ├── 腾讯-earnings-2025Q4.md
│   ├── 腾讯-management-20260409.md
│   └── 腾讯-thesis.md
├── 拼多多/                  — 拼多多所有研究报告
├── 泡泡玛特/                — 泡泡玛特所有研究报告
├── 核电-industry-20260409.md — 行业报告放根目录
├── AI算力-funnel-20260509.md  — 漏斗筛选报告放根目录
├── AI-轮动判断-20260509.md    — 主题级综合判断报告放根目录
├── portfolio-latest.md       — 组合报告放根目录
└── 多公司对比-checklist-20260408.md — 多公司报告放根目录
```

## 报告命名规范

| Skill | 文件命名格式 | 示例 |
|------|---------|------|
| /investment-team | `{公司名}/` 目录内含4个视角+最终报告 | `reports/拼多多/最终报告.md` |
| /investment-research | `{公司名}-research-{YYYYMMDD}.md` | `reports/腾讯/腾讯-research-20260408.md` |
| /investment-checklist | `{公司名}-checklist-{YYYYMMDD}.md` | `reports/腾讯/腾讯-checklist-20260408.md` |
| /industry-research | `{行业名}-industry-{YYYYMMDD}.md`（根目录） | `reports/核电-industry-20260409.md` |
| /industry-funnel | `{行业名}-funnel-{YYYYMMDD}.md`（根目录） | `reports/AI算力-funnel-20260509.md` |
| /private-company-research | `{公司名}-private-{YYYYMMDD}.md` | `reports/字节跳动/字节跳动-private-20260408.md` |
| /earnings-review | `{公司名}-earnings-{期间}.md` | `reports/腾讯/腾讯-earnings-2025Q4.md` |
| /earnings-team | `{公司名}/` 目录内含4个大师视角+研究底稿+公众号文章+读者评审 | `reports/腾讯/腾讯-earnings-2025Q4.md`（公众号定稿） |
| /thesis-tracker | `{公司名}-thesis.md`（长期维护） | `reports/腾讯/腾讯-thesis.md` |
| /portfolio-review | `portfolio-latest.md`（根目录，持续更新） | `reports/portfolio-latest.md` |
| /management-deep-dive | `{公司名}-management-{YYYYMMDD}.md` | `reports/腾讯/腾讯-management-20260409.md` |
| /fund-checklist | `{基金名}-fund-checklist-{YYYYMMDD}.md` | `reports/宏利印度/宏利印度-fund-checklist-20260628.md` |
| /fund-monitor | `{基金名}-monitor-{YYYYMMDD}.md` | `reports/大佬持仓监控/monitor-20260628.md` |
| /fund-penetration | `{基金名}-fund-penetration-{YYYYMMDD}.md` | `reports/宏利印度/宏利印度-fund-penetration-20260628.md` |
| /fund-quarterly | `{基金名}-fund-quarterly-{YYYYMMDD}.md` | `reports/宏利印度/宏利印度-fund-quarterly-20260628.md` |

## /investment-team 文件结构

```
reports/{公司名}/
├── README.md                         — 研究框架概览+核心结论
├── 01-商业模式分析-段永平视角.md
├── 02-财务估值分析-巴菲特视角.md
├── 03-行业竞争分析-芒格视角.md
├── 04-风险管理层评估-李录视角.md
└── 最终报告.md                       — Team Lead 综合报告
```

## 投研分析核心原则（最高优先级）

- **客观、客观、客观**——所有投研分析必须基于事实和数据，严禁主观臆断
- 严格区分"事实"与"观点"：事实用数据支撑，观点必须明确标注为"观点"或"推测"
- **不预设立场**：不预设看多或看空，先摆数据、再推逻辑、最后得结论。结论必须从数据中自然推出
- 禁止使用"我认为"、"我觉得"、"显然"等主观表述，改用"数据显示"、"证据表明"、"根据XX来源"
- **呈现正反两面**：每个核心判断都必须附带反面论据（"但另一方面..."），让读者自己权衡
- 对不确定的事情诚实说"不确定"或"数据不足"，不要用推测填充确定性
- 所有skill（investment-team、investment-research、earnings-review等）在执行时都必须遵守以上原则

## 报告语言与风格

- 所有报告使用**中文**
- 风格：直接、犀利、不说废话
- 数据必须标注来源，关键数据至少2个来源交叉验证
- 估计值必须注明"估计"
- 评分使用★符号（★1-5），不含半星
- 穿插巴菲特/芒格/段永平/李录的语录点评

## GitHub 操作

- 本地克隆路径：`~/ai-berkshire/`
- 远程仓库：`https://github.com/xbtlin/ai-berkshire.git`
- 推送前先 `git pull --rebase origin main`（远程经常有新提交）
- commit message 用中文，描述清楚改了什么
- 不要推送中间过程文件（如 data_collection.md），只推最终报告

## 常用命令

```bash
# 推送报告到GitHub
cd ~/ai-berkshire
git add reports/xxx.md
git commit -m "添加xxx报告"
git pull --rebase origin main
git push origin main
```

## 数据目录结构

```
data/
├── jd_auth/              — 京东金融认证（含cookies.json，本地使用）
│   └── cookies.json      — Cookie缓存（Playwright自动抓取或手动粘贴）
├── fund_cache/           — 基金数据缓存
│   ├── trade_rules_*.json    — 交易规则（30天有效）
│   ├── fund_holdings_*.json  — 持仓分布（7天有效）
│   ├── fund_profile_*.json   — 基金档案（7天有效）
│   ├── fund_perf_*.json      — 业绩排名（7天有效）
│   └── holdings_*.json       — 用户持仓（1天有效）
├── fund_snapshots/       — 持仓快照（每日覆盖）
└── watchlist.json        — 关注列表
```

## 工具使用

### 股票分析工具
- `tools/financial_rigor.py` — 精确计算PE/ROE等指标
- `tools/report_audit.py` — 报告数据15%抽样验证
- `tools/xueqiu_scraper.py` — 雪球数据抓取

### 基金分析工具
- `tools/jd_finance_api.py` — 京东金融42个API封装（零外部依赖）
  - `--test` 测试Cookie有效性
  - `--trade-rules {代码}` 获取交易规则（T+N、费率、限额）
  - `--fund-holdings {代码}` 获取持仓分布
  - `--fund-profile {代码}` 获取基金档案
  - `--fund-perf {代码}` 获取业绩排名
  - `--fund-manager {代码}` 获取基金经理
  - `--holdings {uid}` 获取用户持仓（需登录）
  - `--batch-holdings` 批量获取所有关注人持仓
  - `--offline` 离线模式（仅用缓存）

## 自动基金监控管道（重点）——任何 IDE 通用

**触发关键词**：只要用户说以下任一句，你就直接执行管道，不要先搜索文件：

- "分析今天基金操作" / "分析今天大佬操作"
- "看看今天买入卖出" / "今天买了什么"
- "跑一下基金监控" / "分析基金信号"
- "fund-scan" / "基金全流程扫描"
- "输出 HTML 报告" + "基金"

**执行流程（直接跑命令，不调用 Skill 工具）**：

```bash
# Step 1: 检查 cookie
python tools/jd_finance_api.py --test

# cookie 无效 → 提示 python tools/jd_finance_api.py --login

# Step 2: 抓数据 + 生成报告（并发，≈5s）
cd c:/项目/A基金/ai-berkshire-main
python scripts/auto-pipeline.py

# Step 3: 深度 Checklist 分析（并发，≈9s）
python scripts/generate_report.py
```

**然后你必须做的事**：

1. 读 `reports/auto/latest.md` — 今日信号汇总
2. 读 `data/auto/status.json` — 判断是否交易日、收益率排名
3. 如果 `status.is_trading_day == false` → 直接说"今天非交易日"，展示上一个交易日缓存
4. 如果 `status.is_trading_day == true` 且 total_records == 0 → 问用户要不要看上一天的
5. 正常有数据 → 做解读 + 四大师评价

**四大师评价**（直接做，不调用额外 Skill）：
- 段永平视角：底层持仓商业模式好不好（读 Checklist 穿透持仓）
- 巴菲特视角：费率高不高、业绩持续多久、估值贵不贵（读 Checklist 费率+业绩）
- 芒格视角：赛道拥挤度、经理能力对比（读 Checklist 经理雷达）
- 李录视角：经理背景、公司治理（读 Checklist 经理详情）

**HTML 报告**：如果用户说 "HTML" 或 "输出报告"，生成 `reports/auto/scan-{日期}.html`（独立文件，浏览器直接打开）。

**OpenCode 用户注意**：在 OpenCode 中直接贴上面那段话，OpenCode 会调用 Bash 工具执行命令，不需要 Skill 系统。
