# AI 主动调 SKILL 实战指南

> 当你说"AI 主动调 SKILL", 意思是: 不再等用户复制粘贴 SKILL 名,
> AI 看到日报/基金名, **自己判断该调哪个 SKILL**, 自己执行.

## 三种方式

### 方式 1: OpenCode CLI (推荐)

```bash
# 安装
npm i -g opencode  # 或 winget install opencode

# 准备 SKILL 目录
mkdir -p ~/.opencode/skills
cp -r skills/* ~/.opencode/skills/

# 在项目根目录, 让 OpenCode 读日报
cd c:/项目/A基金/基金
opencode "读 reports/sim/2026-06-26.md, 对每只持仓跑 fund-sell, 输出审计结论"
```

**前置**: OpenCode 已识别 `~/.opencode/skills/` 下的 SKILL 文件.
可通过 `opencode skill list` 验证.

### 方式 2: Claude Code 斜杠命令

项目已有 Claude Code 命令, 见 `codex-skills/` (实际是 Claude Code 适配版).
使用 `/fund-checklist 013841` 直接调用.

### 方式 3: 自动脚本 (本项目 tools/ai_audit.py)

`tools/ai_audit.py` 已经实现了"无 LLM 主动调 SKILL" 的简化版:
- 读日报 JSON
- 跑机器化 4 关审计 (能力圈/经理/成本/聪明钱)
- 生成 `## AI 审计 (auto)` 区块, 附加到日报末尾

不是完整 LLM, 但**给出可重复的事实摘要**, 后续 LLM 可在此基础上做语义判断.

```bash
py -3.10 tools/ai_audit.py 2026-06-26
py -3.10 tools/ai_audit.py --all
```

## 验证清单

- [ ] OpenCode 已安装 (`opencode --version` 有输出)
- [ ] SKILL 已同步到 `~/.opencode/skills/`
- [ ] `docs/AI_AUDIT_PROMPT.md` 的 system prompt 已贴在 OpenCode 会话开头
- [ ] 读 `reports/sim/2026-06-26.md` 能让 AI 列出 6 只持仓的 `fund-sell` 建议
- [ ] 读 `reports/sim/2026-05-29.md` 能让 AI 列出 5 只买入候选的 `fund-checklist` 结果

## 当前实操结果 (2026-07-11)

### 自动脚本模式 (ai_audit.py, 已实跑)

| 日期 | 买入审计 | 持仓审计 | 关键发现 |
|------|----------|----------|----------|
| 2026-05-22 | 1 只 | 0 | 501226 长城: 4 关过 |
| 2026-05-29 | 5 只 | 1 | 4 关全过, 4.1/5 |
| 2026-06-05 | 0 | 6 | T+1 全部 settle, 总收益 +0.07% |
| 2026-06-12 | 0 | 6 | 持有中 |
| 2026-06-19 | 0 | 6 | 持有中 |
| 2026-06-26 | 0 | 6 | 013841 +51.4% 触发止盈 1/3 建议 |

### LLM 主动模式 (待 OpenCode 验证)

需要用户在本机执行:
```bash
opencode "读 c:/项目/A基金/基金/reports/sim/2026-06-26.md,
对持仓的 6 只基金分别跑 fund-sell, 给具体卖出建议.
特别关注 013841 银华集成电路 (+51.4%) 是否该止盈."
```

预期输出格式参考 `docs/AI_AUDIT_PROMPT.md` 的"## 2. 日报审计专用".

## SKILL 适配状态 (截至 2026-07-11)

| SKILL 名 | skills/ | codex-skills/ | opencode-skills/ | Claude 兼容 | OpenCode 兼容 |
|----------|---------|---------------|------------------|-------------|----------------|
| fund-checklist | ✅ | ✅ | ✅ | ✅ | ✅ |
| fund-sell | ✅ | ✅ | ✅ | ✅ | ✅ |
| fund-monitor | ✅ | ✅ | ✅ | ✅ | ✅ |
| fund-scan | ✅ | ✅ | ✅ | ✅ | ✅ |
| fund-penetration | ✅ | ✅ | ✅ | ✅ | ✅ |
| industry-research | ✅ | ✅ | ✅ | ✅ | ✅ |
| portfolio-review | ✅ | ✅ | ✅ | ✅ | ✅ |
| ... (其余 22 个) | ✅ | ✅ | ✅ | ✅ | ✅ |

29 个 SKILL 全部已三向同步.

## 故障排查

| 现象 | 原因 | 解决 |
|------|------|------|
| OpenCode 找不到 SKILL | `~/.opencode/skills/` 没同步 | `cp -r skills/* ~/.opencode/skills/` |
| AI 不会主动调 SKILL | system prompt 没贴 | 复制 `docs/AI_AUDIT_PROMPT.md` 第 1 段到会话开头 |
| 跑基金档案报 404 | `data/fund_cache/` 没这只基金 | `python -c "from tools.jd_finance_api import get_fund_detail; get_fund_detail('CODE')"` 触发拉取 |
| 跑排行榜返空 | 排行榜缓存过期 | `py -3.10 tools/build_ranking_cache.py` |
