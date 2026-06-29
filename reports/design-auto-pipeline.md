# AI Berkshire 自动化方案设计

> **目标**：GitHub Actions 每日自动爬取京东金融数据 → 缓存到仓库 → 生成推荐报告 → 用户只读报告，按需深挖
>
> **设计原则**：最小化人力介入，最大化自动化，AI 只在需要深度分析时引入

---

## 一、现状与痛点

当前使用方式：

```
用户打开 OpenCode → skill("fund-monitor") → 等待 AI 理解 → AI 调 python 脚本 → 出报告
                                 ↑ 每次都要手动操作，无法定时自动跑
```

问题：
1. 每次分析都要打开 OpenCode/Claude Code，无法定时自动运行
2. 数据爬取和 AI 分析耦合在一起，AI 调用成本高
3. 没有持久化的数据仓库，每次重新爬

---

## 二、目标架构

```
┌──────────────────────────────────────────────────────────────┐
│                    GitHub Actions（每日14:30定时）             │
│                                                              │
│  1. 从 Secret 读取 Cookie → 写入 data/jd_auth/cookies.json    │
│  2. 运行 auto-pipeline.py：                                    │
│     ├── 爬取所有大佬持仓（holdings）                            │
│     ├── 爬取所有大佬交易流水（trading records）                 │
│     ├── 计算 diff（对比上次缓存）                               │
│     ├── 合并信号 → 输出推荐                                    │
│     └── 生成 markdown 报告                                     │
│  3. 提交前删除敏感文件                                         │
│  4. git add 白名单文件 → commit → push（数据 + 报告回仓库）     │
└──────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────┐
│                    GitHub 仓库（数据中枢）                      │
│                                                              │
│  data/trading_records_cache.json   ← 交易流水缓存（定名）      │
│  data/trading_records_2025-06-28.json ← 交易流水缓存（归档）  │
│  data/holdings_diff_cache.json     ← 持仓 diff 缓存           │
│  data/holdings_snapshot.json       ← 当日持仓快照（定名）      │
│  data/holdings_snapshot_2025-06-28.json ← 持仓快照（归档）    │
│  data/auto/status.json             ← 运行状态元数据           │
│  reports/auto/daily-2025-06-28.md  ← 每日报告                │
│  reports/auto/latest.md            ← 最新报告（覆盖）          │
└──────────────────────────────────────────────────────────────┘
                              │
          ┌───────────────────┴───────────────────┐
          ▼                                       ▼
┌─────────────────────┐             ┌─────────────────────────┐
│  用户：读报告          │             │  用户：深度分析           │
│  打开 GitHub 看 .md   │             │  打开 OpenCode → 提问    │
│  无需任何 AI 工具      │             │  AI 读仓库缓存后分析      │
│  3 秒看完今日推荐      │             │  比爬取+分析快 10 倍     │
└─────────────────────┘             └─────────────────────────┘
```

### 关键时间线

```
14:00  大佬下午买入 → 交易记录已生成
14:30  ✅ Action 运行 → 爬取所有数据 → 出报告
14:30 - 15:00  你看报告，决定操作
15:00  交易截止
```

- 选择 14:30 而不是收盘后，因为京东交易流水是准实时的，买了就能看到
- 如果 14:30-15:00 有新的操作 → 开 OpenCode，AI 现爬一次（缓存已经是最新的了）
- 周末/节假日也跑（工作日照常，非交易日跳过无数据变更的 commit）

---

## 三、核心组件设计

### 3.1 Cookie 管理

**痛点**：京东金融 API 需要登录 Cookie，且会过期（约 7-30 天）。

**方案**：GitHub Actions Secrets + 本地手动刷新

```
① 首次：用户本地运行一次，用 Playwright 自动获取 Cookie
        → python tools/jd_finance_api.py --login
        → 将 data/jd_auth/cookies.json 内容 base64
        → 存入 GitHub Secrets (key: JD_COOKIES)

② 每日：Action 从 secrets.JD_COOKIES 解码 → 写入 cookies.json
         → run pipeline → 提交前 rm -rf data/jd_auth/

③ Cookie 过期：pipeline 跳过增量爬取，报告顶部标 ⚠️ 警告
         → 用户本地重新 --login → 更新 Secret

④ 安全：提交前强制删除 data/jd_auth/ + 白名单 git add
         绝不 git add data/ 整体目录
```

### 3.2 自动化管道脚本: `scripts/auto-pipeline.py`

**定位**：**纯数据处理，不调用 AI**。所有逻辑都是 if-else + 计算，确定性输出。

```
Phase 0: Cookie Bootstrap
  CI 环境：从 JD_COOKIES env base64 解码 → 写入 data/jd_auth/cookies.json
  本地环境：直接读 data/jd_auth/cookies.json
  → 验证 Cookie 有效性

Phase 1: 数据采集
  爬取 11 位大佬的持仓 + 交易流水
  每个 uid 用 try-except 包裹，单用户失败不阻塞整体
  每次请求间隔 0.3s 限流

Phase 2: 信号计算 [详细逻辑见 3.3]
  持仓 diff：新增/清仓/金额变化
  交易流水聚合：按基金统计 buy_count/sell_count
  合并信号：交易流水权重大于持仓快照

Phase 3: 报告生成
  生成 markdown 报告（卖出 → 买入 → 观察 → 总览 → 系统状态）
  报告头部标注数据新鲜度

Phase 4: 缓存写入（双写）
  定名文件 → data/*_cache.json（skills 消费）
  归档文件 → data/*_YYYY-MM-DD.json（历史追溯）
  报告 → reports/auto/daily-YYYY-MM-DD.md + latest.md
```

### 3.3 信号计算逻辑（详细）

#### 交易流水 → 信号

| 条件 | 信号 | 分数 |
|------|------|:----:|
| `buy_count >= 3` | 🔴 strong_buy | +5 |
| `buy_count >= 2 AND sell_count = 0` | 🟢 buy | +3 |
| `buy_count >= 2 AND sell_count > 0` | 🟢 weak_buy | +2 |
| `sell_count >= 3` | 🔴 strong_sell | -5 |
| `sell_count >= 2 AND sell_count > buy_count + 1` | 🔴 sell | -3 |
| `sell_count >= 1 AND buy_count = 0` | 🟡 weak_sell | -2 |
| 新增持仓（无交易流水） | 🟢 weak_buy | +1 |
| 清仓（无交易流水） | 🟡 weak_sell | -1 |
| 其他 | ⚪ neutral | 0 |

**规则解释**：

- **`buy_count >= 3`**（多人共识买入）：3位以上大佬同时买入同一基金，置信度最高的买入信号
- **`sell_count >= 2 AND sell_count > buy_count + 1`**（硬卖出）：至少2人卖出，且卖出人数明显多于买入人数，过滤季度再平衡误杀
- **`sell_count >= 1 AND buy_count = 0`**（无人买入的卖出）：只有卖出记录没有买入记录，减仓观察
- **持仓新增/清仓但无交易流水**：可能是系统同步延迟或手动操作未记录，降级为弱信号

#### 信号优先级

```
交易流水信号 > 持仓 diff 信号
```

持仓数据可能买于很久之前（成本未知），而交易流水反映**当下的判断**。

### 3.4 GitHub Actions 工作流: `.github/workflows/daily-report.yml`

```yaml
name: Daily Fund Report

on:
  schedule:
    # 每天 14:30 北京 = 06:30 UTC（周一至周日）
    - cron: '30 6 * * *'
  workflow_dispatch:

jobs:
  pipeline:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Decode cookie
        run: |
          mkdir -p data/jd_auth
          echo "${{ secrets.JD_COOKIES }}" | base64 -d > data/jd_auth/cookies.json

      - name: Run pipeline
        id: pipeline
        run: python scripts/auto-pipeline.py
        continue-on-error: true    # 即使无 cookie 也能走降级路径

      - name: Check pipeline status
        if: steps.pipeline.outcome == 'failure'
        run: |
          echo "::warning::Pipeline failed — report may be stale"

      - name: Clean sensitive files before commit
        run: rm -rf data/jd_auth/

      - name: Commit results
        run: |
          git config user.name "ai-berkshire-bot"
          git config user.email "bot@ai-berkshire.local"
          # 白名单 add，绝不 git add data/
          git add data/holdings_snapshot*.json \
                  data/holdings_diff_cache.json \
                  data/trading_records_cache.json \
                  data/trading_records_*.json \
                  data/auto/ \
                  reports/auto/
          git commit -m "auto: daily report $(date +%Y-%m-%d)" || echo "No changes"
          git push
```

**安全设计**：
- 提交前 `rm -rf data/jd_auth/` 强制删除 cookie
- `git add` 使用白名单，绝不 `git add data/`
- `continue-on-error: true` 允许降级，但后续 step 检查到失败时标记警告

### 3.5 数据新鲜度指标

报告头部始终显示：

```markdown
> ✅ 数据已更新 · 2025-06-28 14:30:05       # 正常
> ⚠️ 数据可能不是最新的 — Cookie 过期/缺失   # 降级
```

`data/auto/status.json` 记录运行状态：

```json
{
  "date": "2025-06-28",
  "timestamp": "2025-06-28 14:30:05",
  "cookie_ok": true,
  "crawl_ok": true,
  "holdings_ok": true,
  "trading_ok": true,
  "message": "Valid (user: 某某某)"
}
```

### 3.6 缓存文件双写

每次运行同时写入两种文件：

| 文件 | 用途 | 行为 |
|------|------|------|
| `data/trading_records_cache.json` | skills 读取（fund-monitor, fund-sell） | 覆盖 |
| `data/trading_records_2025-06-28.json` | 历史归档 | 新增 |
| `data/holdings_snapshot.json` | 下次 diff 对比基准 | 覆盖 |
| `data/holdings_snapshot_2025-06-28.json` | 历史归档 | 新增 |
| `data/holdings_diff_cache.json` | skills 读取 | 覆盖 |
| `reports/auto/latest.md` | 用户查看最新报告 | 覆盖 |
| `reports/auto/daily-2025-06-28.md` | 历史报告 | 新增 |

### 3.7 AI 深度分析（可选，分层使用）

| 场景 | 用什么 | 需要 AI？ | 操作 |
|------|--------|:---------:|------|
| **今天该不该卖？** | 读 `reports/auto/latest.md` | ❌ 不用 | 打开 GitHub 看报告 |
| **最近谁在动？** | 读 `reports/auto/latest.md` | ❌ 不用 | 打开 GitHub 看报告 |
| **基金 X 为什么被卖出？** | OpenCode + `skill("fund-penetration")` | ✅ | 开一次会话提问 |
| **我的持仓整体怎样？** | OpenCode + `skill("fund-sell")` | ✅ | 开一次会话提问 |
| **能不能买基金 Y？** | OpenCode + `skill("fund-checklist")` | ✅ | 开一次会话提问 |

**关键优化**：数据被 Action 每日爬好存在仓库里，AI 会话时**不需要重新爬取**。耗时最长的 API 调用环节已经被跳过了，AI 直接从缓存数据开始分析。

---

## 四、需要做的改动

### 新增文件（3 个）

| 文件 | 说明 |
|------|------|
| `scripts/auto-pipeline.py` | 自动化管道脚本（已实现） |
| `.github/workflows/daily-report.yml` | GitHub Actions 配置（已实现） |

### 不需要改动的文件

`tools/jd_finance_api.py`、`skills/*.md`、`scripts/sync-opencode-skills.py` — 全部保持原样。

管道脚本 `auto-pipeline.py` 通过 `from tools.jd_finance_api import ...` 复用现有函数，零侵入。

---

## 五、成本分析

### GitHub Actions

| 项目 | 费用 |
|------|------|
| GitHub Actions 额度 | 免费版 2,000 分钟/月 |
| 每日运行估计 | ~2 分钟（11 个 uid × 2 API/uid + 信号计算） |
| 月消耗 | ~60 分钟（每天跑，含周末） |
| 占免费额度 | **3%** |

### 仓库存储

| 项目 | 大小 |
|------|------|
| 每日缓存数据增量 | ~20 KB（仅归档文件增，定名文件覆盖） |
| 每日报告 | ~5 KB |
| 年增长 | ~10 MB |
| 结论 | **可以忽略** |

---

## 六、风险与应对

| 风险 | 概率 | 影响 | 应对 |
|------|:----:|:----:|------|
| Cookie 过期 | 高（每月） | Pipeline 跳过增量爬取，报告标⚠️警告 | 用户 1 分钟本地刷新 + 更新 Secret |
| 雪球 API 改版 | 低 | 所有爬取失败 | 手动修复 `jd_finance_api.py`，重新部署 |
| GitHub Actions 故障 | 低 | 当天无报告 | 手动触发 `workflow_dispatch` 重试 |
| 部分用户数据缺失 | 每天 | 该用户信号消失 | try-except 包裹单用户，不阻塞整体 |

---

## 七、使用流程（用户视角）

### 日常（30 秒）

```
① 打开 GitHub → ② 点进 ai-berkshire 仓库
③ 打开 reports/auto/latest.md
④ 看 🔴 卖什么 / 🟢 买什么 → 完事
```

### Cookie 刷新（每月一次，1 分钟）

```bash
# 1. 本地运行
python tools/jd_finance_api.py --login
# 用浏览器扫码登录

# 2. 更新 GitHub Secret
# 把 data/jd_auth/cookies.json 内容 base64
# → 复制输出 → GitHub → Settings → Secrets → 更新 JD_COOKIES
```

### 深度分析（按需，5 分钟）

```bash
# 打开 OpenCode，问：
"帮我分析基金 006105，数据在仓库里"
# AI 自动读缓存 → 给你深度分析
```

---

## 八、评审焦点

1. `auto-pipeline.py` 的信号计算逻辑是否足够保守？（宁可漏报不错报）
2. Cookie 过期时 pipeline 的降级行为是否合理？（跳过增量爬取，报告标⚠️）
3. 报告格式是否满足"只看报告就能做决策"的目标？
4. 14:30 的时间点是否能覆盖所有今天的交易数据？
