# 变更文档：交易流水信号集成

> 日期：2025-06（持续更新）
> 类型：功能新增 + 技能优化
> 涉及技能：fund-monitor, fund-sell, fund-checklist
> 涉及工具：jd_finance_api.py
> 兼容层：AGENTS.md, opencode-skills, scripts/sync-opencode-skills.py

---

## 变更全貌

### A. jd_finance_api.py — CLI 新增交易流水接口

**新增参数**：
- `--trading-records {uid}`：查看某位大佬的近期交易流水
- `--trading-records-all`：遍历所有关注 uid，串行拉取全量流水

**核心函数** `get_trading_records()`：
- 调用 `gw2/generic/aladdin/h5/m/getPageMutilData`（pageId=11568）
- 解析 feed 中的 `tradeRecordData`，包含操作（买入/卖出）、基金名称、金额
- 复用 `_ensure_cookies()` 鉴权，cookie 失效时自动报错

### B. fund-monitor.md — Step 4 交易流水分析

**新增流程**（在已有时机/交叉引用检查之后）：

```
Step 4: 交易流水获取 → 信号转换 → 缓存持久化
```

核心设计：
- 交易流水 > 持仓快照（持仓代表过去，交易代表当下判断）
- 每条记录转为信号强度（⭐⭐⭐ 强共识买入 / ⚠️ 卖出 / 🔴 多人卖出）
- 结果写入 `data/trading_records_cache.json`
- 缓存结构：`{date, funds: {代码: {buy_count, sell_count, net_signal, buy_actions[], sell_actions[]}}}`

### C. fund-sell.md — 双缓存合并加权 + Buy Shield

**数据源增加**：新增读取 `data/trading_records_cache.json`

**硬性卖出 A2**：
| 条件 | 规则 |
|---|---|
| 大佬集体清仓≥3人 + 交易流水确认卖出 | 🔴 双确认→清仓 |
| 大佬集体清仓≥3人 + 交易流水无卖出 | 🟡 降级减仓（可能被动赎回） |
| 交易流水≥2人卖出 + 持仓下降 | 🔴 强行卖出确认 |
| 交易流水+持仓信号矛盾 | 标记"分歧观察"，不触发 |

**减仓观察 B**：
| 条件 | 减仓比 |
|---|---|
| 交易流水确认多人卖出（sell_count ≥ 2） | 1/3 |
| 交易流水确认单一人卖出（sell_count = 1） | 1/4 |
| 交易流水多人买入（buy_count ≥ 2）→ buy shield | ✅ 持有确认，跳过本次 |

**Buy Shield 逻辑**：
```
如果 trading_records 显示 ≥2 位大佬买入你持仓的基金
→ 强制持有确认，跳过本轮卖出检查
→ 原理：大佬们现在正在买入，你没有卖出的理由
```

**加权计算规则**：
```
weighted_clear = holdings_score × (1 - sell_count × 0.1)
sell_count=0 → 满权重
sell_count=1 → ×0.9
sell_count=2 → ×0.8
sell_count=3+ → ×0.7（上限扣减）

当 net_signal=sell & sell_count≥2 & 持仓金额减少
→ 🔴 硬性独立触发（不依赖加权分阈值）
```

### D. fund-checklist.md — 前轮遗留：频率分级 + YAML frontmatter

**频率分级**：daily / every_other_day / weekly / monthly
- YAML frontmatter 中声明 `frequency`，Step 1 根据 `last_check` 判断是否该扫描

**过期清理**：fund-monitor 中穿透信号 >15 天未确认 → 自动失效

### E. OpenCode 兼容层（本轮新增）

- `scripts/sync-opencode-skills.py`：skills/*.md → opencode-skills/*/SKILL.md
- `scripts/install-opencode-skills.ps1`：Windows 安装脚本
- `scripts/install-opencode-skills.sh`：macOS/Linux 安装脚本
- AGENTS.md 更新：增加 OpenCode 目录说明 + 同步规则

---

## 改动文件清单

| 文件 | 状态 | 行数变化 |
|---|---|---|
| `tools/jd_finance_api.py` | 修改 | +40 行（CLI + parse） |
| `skills/fund-monitor.md` | 修改 | +90 行（Step 4 + 缓存） |
| `skills/fund-sell.md` | 修改 | +50 行（双缓存 + buy shield + 模板三） |
| `skills/fund-checklist.md` | 前轮 | YAML frontmatter + 频率逻辑 |
| `scripts/sync-opencode-skills.py` | 新增 | ~65 行 |
| `scripts/install-opencode-skills.ps1` | 新增 | ~45 行 |
| `scripts/install-opencode-skills.sh` | 新增 | ~35 行 |
| `AGENTS.md` | 修改 | +6 行 |

---

## 关键设计决策

1. **交易流水 > 持仓快照**：持仓可能是几个月前的成本，交易反映当下判断
2. **独立触发**：sell_count≥2 + 持仓下降 无需加权分达标即可触发硬性卖出
3. **Buy Shield**：sell_count≥2 买入触发持有确认，防止高位建仓后因微小波动卖出
4. **sell_count 系数 0.1**：启发式，每多一人卖出扣减 10% 权重，最高扣 30%
5. **串行 API 调用**：--trading-records-all 依次调用，避免雪球限流

---

## 评审焦点

1. sell_count ≥ 2 硬触发门槛是否合理？是否应改为 sell_count > buy_count + 1？
2. buy shield 是否有 30 天时效限制？目前无时效，买入信号一直有效
3. sell_count × 0.1 扣减系数是否需要根据回测调整？
4. API 调用频率：11 人 × 1 次/监控周期，是否触发雪球限流？
5. 缓存格式是否便于 fund-sell 扩展（如增加持仓成本推算）？
