---
name: fund-scan
description: "以下自然语言/命令会自动触发本 SKILL:"
user-invocable: true
# Original frontmatter from skills/fund-scan.md:
#   name: fund-scan
#   user-invocable: true
#   description: "完整基金全流程扫描——抓数据→五维评分→交易信号→深度分析→四大师评价→独立HTML报告"
---
## OpenCode adapter note

This skill is generated from `skills/fund-scan.md` — the canonical source.

- Treat `$ARGUMENTS` as the user's request in the current session.
- When the source references Claude-only tool names (Task, Agent, etc.), use the closest capability available in your environment.
- Commands reference `python3 tools/...` — use the correct Python path for your shell.
- Preserve the research quality rules from `AGENTS.md`: cross-check financial data, use exact arithmetic, label uncertainty.

## 触发短语 (triggers)

以下自然语言/命令会自动触发本 SKILL:

- `基金扫描`
- `基金筛选`
- `扫基金`


## 必读数据

| 文件 | 用途 |
|------|------|
| `data/cache/ranking.json` | 271 只排行 (近1/3/6/12月+夏普+回撤) |
| `data/fund_cache/featured_rankings_main.json` | 京东官方 26 榜 TOP20 |
| `data/fund_name_map.json` | 名称→代码 |
| `data/fund_charts_meta.json` | 元数据 |

# 基金全流程扫描

一站式基金分析：从京东金融实时数据抓取到五维评分+独立HTML报告输出。

## 一句话触发

"分析今天基金操作" / "看看大佬买卖什么" / "基金全流程扫描" / "fund-scan" / "今天基金有什么信号"

## 执行步骤

### 第一步：前置检查

运行 `python tools/jd_finance_api.py --test` 检查 cookie。无效则提示登录。

### 第二步：抓取数据

```bash
python scripts/auto-pipeline.py
python scripts/generate_report.py
```

管道自动包含五维评分（tools/fund_scorer.py）+ 资金分配器 + 穿透估值(PE/PB)。

### 第三步：解读报告 + 评分

读取 `reports/auto/latest.md` 和 `data/auto/status.json`，展示：
- 今日信号 + 五维评分
- 评分≥4.0 建议买入，3.3~4.0 值得关注，<3.3 建议跳过

### 第四步：LLM 自动点评（读取 daily_snapshot.json）

读取 `data/auto/daily_snapshot.json`（管道自动生成），用 Claude 生成 2-3 句今日解读：

```json
// daily_snapshot.json 包含:
{
  "summary": { "total_scored": 271, "buy_verdict": 0, "watch_verdict": 7, "strong_buy_signals": 12 },
  "top_scores": [ { "code": "013841", "total": 3.57, "verdict": "watch" }, ... ],
  "buy_signals": [ { "code": "013841", "buy_count": 5, "score": 3.57 }, ... ],
  "changes": { "013841": 0.17, ... }
}
```

解读要点：
- 今天评分最高的基金是谁？为什么？
- 评分变化最大的基金（涨/跌）原因分析
- 大佬共识集中在哪个方向？评分是否支持？
- 你的持仓基金评分变化和操作建议
- 输出简洁、直接、不说废话，2-3 句话

### 第五步：四大师评价

对 strong_buy（≥3人）基金做四大师视角评价，结合评分数据。

### 第六步：生成 HTML

```bash
python scripts/generate_html.py
```
输出 `reports/auto/scan-{日期}.html`。

直接展示关键结论，告诉用户 HTML 报告位置。

## 注意事项

- 所有费率/限额/N 从 API 实时获取，不硬编码
- 评分是 Python 数值计算，LLM 只做解读不做评分
- 穿透估值目前仅支持 A 股 PE/PB，美股只支持价格行情
- 反模式参见 docs/评分反模式.md
