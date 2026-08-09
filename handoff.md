# HANDOFF 交接文档 — C:\fund 量化策略项目

> **更新时间**: 2026-08-09
> **用途**: 供新开对话使用，防止上下文丢失。新对话先读本文件 + `CLAUDE.md` + `AGENTS.md`。

---

## 一、当前核心结论（一句话）

**数据已全部修正完成（v7 为权威数据），R21 已推送到 GitHub Actions 在干净数据上重跑，用于评估「大佬因子」好坏。R1–R20 结果因旧数据污染全部作废。**

---

## 二、数据现状（最重要的部分）

### 权威数据文件
| 文件 | 说明 |
|---|---|
| `backtest/data/trading_by_date_real414_v7.json.gz` | **当前权威数据**（10.89MB，550,365 条，1097 天，2023-08-08 ~ 2026-08-08） |
| `backtest/data/trading_by_date_real414_v5.json.gz` | 上一版（已含 292 条 C 类修正），现作为**回退**保留 |
| `data/smart_money_signals.json` | 大佬信号（19,586 个），已基于 v7 重建 |
| `data/follow_pool_414.json` | **权威 414 用户关注池**（2026-08-08 抓取，399 有交易 + 15 无交易） |

### 引擎加载链（`backtest/engine/backtest.py` 已更新）
```
v7.json → v7.json.gz → v5.json → v5.json.gz → v4 → v2 → real414 → fixed → trading_by_date
```
（当前 v7.json.gz 存在，直接命中）

### 已删除的旧错误文件
- `backtest/data/trading_by_date_fixed.json`（旧模糊匹配，92.9MB，错配 22%）❌ 已删
- `backtest/data/trading_by_date_real414.json`（原始未修复）❌ 已删
- `backtest/data/trading_by_date.json`（旧随机用户，1.4MB）❌ 已删

---

## 三、数据修正完整历史（为什么 v7 是对的）

### 1. 权威重映射 v4→v5（commit `9e556df`，已完成）
- `fund_name_map.json`（天天基金模糊匹配，similarity≥0.85）错配率高达 **22%**（如股票基金→债券基金）
- 用**京东官方 `getFundChart` API 的权威 `productId`** 重映射（`tools/authoritative_remap.py`）
- 修复 **88,405 条**，覆盖率提升至 **99.933%**

### 2. K 线配错修复 v5→v6（2 个 fid，292 条）
- **兴全合润混合 C (fid=105360)**: 023875→163406（C 类 2025-04-08 才成立，之前用 C 类码是错的）
- **中金沪深300ETF联接C (fid=108054)**: 023147→003579（C 类 2025-06-03 成立）
- **根因**: C 类新份额有成立日期，成立前的交易用 C 类码 = K 线错误

### 3. 异常 fid 残留错配修复 v6→v7（5 条，本会话新增）
用 `getFundChart` 权威 productId + eastmoney + 京东档案全量复核异常 fid（ZH 组合码/日期后缀 fid）后发现 5 条漏网：

| 记录基金名 | 原code（错） | 修正为（对） |
|---|---|---|
| 华安生态优先混合A | 006396 | **000294** |
| 华泰柏瑞鼎利混合C | 005787 | **004011** |
| 兴全商业模式混合(LOF) | 005364 | **163415** |
| 银河收益债券 | 1884284282-...(异常串) | **151002** |

修正后 5 条在各自交易日期**均有当日净值**，K 线无缺口。

### 4. 无法确定（保持现状，记录在案，金额极小）
- `博时新起点混合A`（163元）：查无此基金，名字疑似笔误
- `中银腾利混合C`（710元）：记录名存疑
- `浦银颐和养老FOF-C`：正确 C 类 `007402` 无净值数据，保留 A 类 `007401`

### 5. 净值缺口分类审计（已确认无其他 K 线错误）
30,177 条取不到当日净值的记录全部归因于：**周末/节假日/QDII 延迟披露/新成立基金(45天内)/净值滞后(2026-07-22后未抓)**。仅上述 2+5 条为真配错，均已修复。

---

## 四、R21 状态（最关键——评估大佬因子）

### 已做
- 触发 R21：push `33a476b` + `99b0ae0` 到 origin/master，**已触发 GitHub Actions `strict_oos_p1.yml` workflow**
- **R21 run 已确认 in_progress**：run_id=`31298563147`，head=`99b0ae0`（2026-08-09 06:18 触发）
- 上一轮 R21（head=`9e556df`，run_id=`31293640960`）**completed/failure**（4:00），已由本次干净重跑取代
- R21 在**干净数据（v7）**上跑 **172 个回测**（84 训练 + 88 测试 + 汇总）
- R21 框架（`scripts/exp_strict_oos.py`, `ROUND=21`）4 个候选：
  1. `KC_AGGRESSIVE_BASELINE` — 基线（无大佬因子）
  2. `KC_SMART_BUY_15` — 大佬因子作独立维度
  3. `KC_SMART_BUY_25` — 大佬因子作独立维度（更强阈值）
  4. `KC_SMART_MOD` — **大佬因子作加减分修饰符（不占维度权重）** ← R21 新增核心

### 待新对话做
1. **等 R21 跑完**：轮询 `v9-results/strict_oos_r21_eval.json` 是否生成（当前只有 r20，无 r21）
2. **读结果**：对比 4 个候选的 OOS 平均收益、胜率(beats_rate)、最大回撤(avg_max_drawdown/peak_max_dd)
3. **判断大佬因子好坏**：SMART_BUY/ SMART_MOD 是否显著跑赢 BASELINE
4. 若跑赢 → 保留大佬因子 → 设计 R22 深化；若没跑赢 → 降权/移除 → R22 探索其他方向

### 如何查看 GitHub Actions 状态
- `gh run list`（需 GitHub CLI 认证）或浏览器打开 https://github.com/wsxvg/ai-berkshire/actions
- **注意**：本机 GitHub 直连不通，需走本地代理 **127.0.0.1:7890**（见第五节网络说明）

---

## 五、网络/环境注意（重要，避免踩坑）

### GitHub 访问必须走代理
本机 `github.com` 直连不通（DNS 被劫持到 127.0.0.1）。检测到本地代理 **127.0.0.1:7890**（Clash 类）可用。
```powershell
# git 拉取/推送前设代理（每次命令临时设置，不写死全局配置）
$env:HTTPS_PROXY="http://127.0.0.1:7890"
$env:HTTP_PROXY="http://127.0.0.1:7890"
git push origin master
```
`www.baidu.com` 直连正常，仅 GitHub 系域名需代理。

### 其他环境要点
- 包管理器：pnpm
- 京东金融 Cookie 有效（`tools/jd_finance_api.py --test` 验证通过）
- 本地回测限制 worker=2 避免 CPU 满载；**所有计算密集型回测走 GitHub Actions**
- 后端 RPC/数据库操作用 Supabase Management API（PAT 认证），沙箱内 psql DNS 解析失败

---

## 六、本次会话创建的临时脚本（已清理）
所有 `_audit_*` / `_verify_*` / `_check_*` / `_fix_v7.py` 等临时脚本已删除。
**保留**：`scripts/_build_smart_signals_v5.py`（已更新为读取 v7，可复用于重建信号）。

---

## 七、下一步行动清单（新对话直接执行）

1. 轮询/查看 R21 GitHub Actions 是否完成，读 `v9-results/strict_oos_r21_eval.json`
2. 分析大佬因子好坏（对比 BASELINE vs SMART_BUY vs SMART_MOD）
3. 把结论写进 `v9-results/` 下的迭代文档
4. 根据结论决定 R22 方向（保留/降权/移除大佬因子）
5. 若有新的数据疑问，用 `jd-shipan-fund-mapping` skill + `getFundChart` 权威 productId 复核，不要靠名称猜

---

## 八、关键参考
- Skill: `jd-shipan-fund-mapping`（京东基金码映射权威验证）
- 工具: `tools/jd_finance_api.py`、`tools/authoritative_remap.py`
- 数据: `data/chart_to_name.json`、`data/fund_name_map.json`、`data/jdcode_to_chart.json`
- 引擎: `backtest/engine/backtest.py`（加载链已优先 v7）