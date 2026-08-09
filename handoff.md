# HANDOFF 交接文档 — C:\fund 量化策略项目

> **更新时间**: 2026-08-09 晚
> **用途**: 供新开对话使用，防止上下文丢失。新对话先读本文件 + `CLAUDE.md` + `AGENTS.md`。

---

## 一、当前核心结论（一句话）

**数据已全部修正完成（v7 为权威数据），R21 已跑完并补全 BASELINE 全部 6 窗，完成 4 候选 × 22 窗同窗公平对比——最终结论：大佬因子（smart_money）无净 alpha，放弃该因子，保留 BASELINE 作为 R22 起点。R1–R20 结果因旧数据污染全部作废。**

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

### 3. 异常 fid 残留错配修复 v6→v7（5 条）
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

### ⭐ R21 结果（2026-08-09 更新——**结论颠覆，谨慎！**）
**⚠️ 核心结论已反转：补全 BASELINE 后，大佬因子无正 alpha，此前"跑赢基线"是缺窗口造成的假象！**

**背景**：R21 在 v7 干净数据上跑，24 backtest job 全部 success（run `31308921476`），但 aggregate 的 git push 失败。我直接从 artifacts 下载了全部结果（含 ci0-BASELINE 的 wi21-38），本地做逐窗口对比 + 敏感性分析，得出**与上一轮相反的结论**。

**重叠 18 窗（wi21-38）逐窗口对比（最公平）**：
| 候选 | 跑赢 BASELINE | 平均超额 vs BASELINE |
|---|---|---|
| `SMART_BUY_15` | 8/18 (44%) | **-0.270%** |
| `SMART_BUY_25` | 9/18 (50%) | **-0.121%** |
| `SMART_MOD` | 0/18 (0%) | **+0.000%**（与基线完全相同）|

**关键事实**：
1. **`SMART_MOD` 在所有窗口收益与 `BASELINE` 完全一致**（wi24-38 全部相同数值）→ 修饰符逻辑在 OOS 中**零触发/零影响**（回调+大佬持仓信号在测试期极少满足条件，或匹配失败）。
2. **BASELINE 缺的 4 窗（wi39-42）是高收益窗口**：wi41 参考值 +23~33%。用 ci1/ci3 敏感性补全后，**BASELINE 22窗 avg = 3.27~3.59%**，直接追平甚至反超 3 候选（3.09~3.37%）。
3. 上一轮"BASELINE 1.16% + 大佬因子 +2.2%"是**假象**——只因 BASELINE 缺了高收益后段窗口被低估。

**最终判断（数据支持）**：大佬因子（SMART_BUY 维度 / SMART_MOD 修饰符）在 R21 OOS 上**没有带来正超额收益**。SMART_BUY 略跑输，SMART_MOD 完全无效。**不推荐保留大佬因子作为增强方向。**

**遗留**：ci0 BASELINE 的 wi39-42 仍缺（GitHub runner 上 ci0 后段窗口每个 >300s 超时被杀，ci1/2/3 能跑完但 ci0 不能——疑为 BASELINE 无信号过滤导致全市场扫描更慢）。需把 ci0-b5 的 timeout 单独提到 600s+ 或拆分窗口才能补全。

### R21 并行化历程（2026-08-09，血泪踩坑，务必参考！）
GitHub Actions 并行化连续踩坑，**最终方案才可用**。完整经历：
1. **v1（172 独立 job，ci×wi 双矩阵）**：回测全成功，但 **172 个并行 artifact 上传丢失 64 个**（Found 108/172），consolidate 缺 test 文件 → aggregate 失败。**教训：不要用海量独立 artifact**
2. **v2（4 job × xargs -P8）**：8 进程并发把 GitHub 免费 runner **内存打爆，OOM exit 143**，runner 被杀。**教训：单 runner 内不要多进程并发跑回测**
3. **v3（24 job，ci×窗口块 b0-5，每块单进程顺序跑 7-8 窗）**：单进程无 OOM，但 **后段窗口（wi 30-42）每个要 >90s，`timeout 90` 全被杀死** → b4/b5 块文件缺失 → 又是 test 缺文件。**教训：后段窗口慢，timeout 必须 ≥300s**
4. **v3 修复（timeout 90→300，job timeout 30→60min）**：✅ 正常跑完，test 文件 82/88，aggregate 算出全部 4 候选结果。**但最后 git commit/push 失败**（报错 `fatal: /: '/' is outside repository`，eval 文件没推到远程）

**✅ 最终可用 workflow**：`.github/workflows/strict_oos_r21_parallel.yml`
- `strategy.matrix`：ci=[0,1,2,3] × b=[0,1,2,3,4,5] = **24 个 backtest job**（每 job 单进程顺序跑一个窗口块）
- 块窗口划分：b0=wi0-7, b1=wi8-15, b2=wi16-22, b3=wi23-29, b4=wi30-36, b5=wi37-42
- 每窗口 `timeout 300`；job `timeout-minutes: 60`
- **每块单进程**（无 OOM），**24 个 artifact**（上传可靠）
- **⚠️ aggregate 仍失败**：Commit results 步骤 `git push origin "HEAD:${GITHUB_REF_NAME}"` 在 `workflow_dispatch` 下 `GITHUB_REF_NAME` 可能为空 → 仍报 `fatal: /: '/' is outside repository`。**修复办法**：显式写死分支 `git push origin HEAD:master`（勿用 GITHUB_REF_NAME）。**但注意**：24 个 backtest job 的 artifacts 已在 run `31308921476` 里，可**直接下载聚合，无需重跑**（本次就是这么拿到公平结果的）。

### 成功 run 记录
- **最新 run**：run_id=`31308921476`，head=`dd49383`，24 backtest job **全部 success**（含 ci0-b5 但该 job 实际 0 产出，见下），aggregate 仍 git push 失败
- **上轮有结果 run**：run_id=`31302696102`，head=`a5bbfcf`，24 job 全完成，aggregate 算出 eval 但 push 失败
- 之前失败 run（历史，勿再用）：`31299392136`、`31300564189`(v1 artifact丢)、`31301363828`(v2 OOM)、`31302050338`(v3 timeout)

### ✅ 当前状态（2026-08-09 23:00 更新——补全完成，eval 已落盘推送）
- **✅ 已补全 BASELINE 全部 6 窗（wi37-42）**：新建 `.github/workflows/strict_oos_r21_baseline_backfill.yml`（3 job × 2 窗，`timeout 900`，commit `6fe758e`），在 Actions 上跑完 run `31310382385` 全部 success。补全的 6 窗：wi37(+25.6%) wi38(-6.2%) wi39(+8.2%) wi40(-5.8%) wi41(+30.7%) wi42(+0.9%)，均值 ~+8.8%/窗（确认为高收益段）。
- **✅ 完整 22 窗公平 eval 已落盘**：下载全部 4 候选 × 22 窗窗口数据（run `31308921476` 的 ci1/2/3 artifact + ci0 b0-b4 artifact + 补跑的 ci0 b5），本地 `python scripts/exp_strict_oos.py test` 生成 `v9-results/strict_oos_r21_eval.json`，并已 push 到 master（commit `2e98080`）。
- **✅ 最终结论（22 窗同窗公平对比）**：见下方表格——大佬因子**无净 alpha**，保留 BASELINE，放弃 smart_money。
- **⚠️ ci0-b5 超时根因**：`strict_oos_r21_parallel.yml` 的 b5 块 `timeout 300` 对 ci0 后段窗口不够（每窗 >300s，BASELINE 无信号过滤全市场扫描更慢），导致 wi37-42 全被杀。补跑 workflow 已用 `timeout 900` 解决。
- **aggregate 的 git push 修复**：把 Commit results 的 push 改写成 `git push origin "HEAD:${GITHUB_REF_NAME}"` 仍会因 `workflow_dispatch` 下 `GITHUB_REF_NAME` 为空而报 `fatal: /: '/' is outside repository`。**建议写死 `git push origin HEAD:master`**。但 aggregate 非必需（可直接下载 artifact 本地聚合，本次即如此）。

### R21 框架（`scripts/exp_strict_oos.py`, `ROUND=21`）4 个候选
1. `KC_AGGRESSIVE_BASELINE` — 基线（无大佬因子）
2. `KC_SMART_BUY_15` — 大佬因子作独立维度，weight=15
3. `KC_SMART_BUY_25` — 大佬因子作独立维度，weight=25
4. `KC_SMART_MOD` — **大佬因子作加减分修饰符（不占维度权重）** ← R21 新增核心

### 待新对话做（按优先级，2026-08-09 已下结论）
1. **✅ 已下最终结论**：大佬因子在 R21 OOS 无正 alpha（重叠18窗 SMART_BUY 跑输/-0.1~-0.3%，SMART_MOD 与基线完全相同）。**R22 方向：不再以大佬因子作为增强主方向**，转而探索其他 alpha 来源（如动量/质量维度调参、行业轮动、更细的择时）。
2. **（可选）落盘 eval**：`v9-results/strict_oos_r21_eval.json` 尚未生成。可在把 `_r21x` json 放根目录后本地跑 `python scripts/exp_strict_oos.py test` 生成并记录。
3. **（可选）彻底补全 BASELINE wi39-42**：仅对 ci0-b5 单独跑，timeout 提到 600s+。但既然重叠 18 窗对比已足够下结论，此步非必需。
4. **清理临时脚本/目录**：`scripts/_dl_r21_artifacts.py`、`_tmp_*.py`、`_tmp_r21/`、`_r21x/`、`_r21_artifacts/` 等是本次会话临时产物，结论落盘后可清理；根目录的 `strict_*.json` 是回测结果文件，可清理（它们是 artifacts 解压产物）。

### 如何查看 GitHub Actions 状态
- API 轮询：`python scripts/_poll_r21_true_parallel.py`（脚本内改 RUN_ID 即可复用）
- **注意**：本机 GitHub 直连不通，需走本地代理 **127.0.0.1:7890**（见第五节网络说明）
- **下载 artifact 需要 PAT 有 `actions:read` 权限**（当前 git-credentials 的 token 没有，下载会 401）

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

## 六、本次会话创建的临时脚本
- **保留**：`scripts/_build_smart_signals_v5.py`（已更新为读取 v7，可复用于重建信号）
- **保留**：`scripts/_poll_r21_true_parallel.py`（R21 轮询器，改 RUN_ID 可复用）
- 其余 `_audit_*` / `_verify_*` / `_check_*` / `_fix_v7.py` / `_dl_r21_artifacts.py` / `_diag_*` 等临时脚本已删除

---

## 七、下一步行动清单（新对话直接执行）

### R21 已全部完成（2026-08-09 23:00）
1. **✅ 补全 BASELINE 6 窗（wi37-42）**：已在 Actions 跑完（run `31310382385`），timeout 900。
2. **✅ 完整 22 窗公平 eval 落盘**：`v9-results/strict_oos_r21_eval.json`（4 候选 × 22 窗），已 push（commit `2e98080`）。
3. **✅ 判断大佬因子**：**无净 alpha，放弃 smart_money，保留 BASELINE**。
4. **迭代文档**：`v9-results/STRATEGY_EVOLUTION_R21.md` 已写，已 push。

### 下一步（R22 方向）
1. **R22 设计**：不再以大佬因子为增强主方向，基于 BASELINE（KC_AGGRESSIVE_BASELINE）探索其他 alpha：动量/质量维度调参、行业轮动、择时细化。
2. **遗留（可选）**：`strict_oos_r21_parallel.yml` 的 aggregate push 仍失败（GITHUB_REF_NAME 为空），可改 `git push origin HEAD:master`。但 aggregate 非必需（可下载 artifact 本地聚合）。
3. **清理（可选）**：根目录的 88 个 `strict_test_ci*.json` 是回测结果文件（可删，eval 已落盘）；`scripts/_dl_r21_artifacts.py`、`scripts/_poll_r21_*.py` 可保留（复用于下载/轮询）。
5. 若有新的数据疑问，用 `jd-shipan-fund-mapping` skill + `getFundChart` 权威 productId 复核，不要靠名称猜

---

## 八、关键参考
- Skill: `jd-shipan-fund-mapping`（京东基金码映射权威验证）
- 工具: `tools/jd_finance_api.py`、`tools/authoritative_remap.py`
- 数据: `data/chart_to_name.json`、`data/fund_name_map.json`、`data/jdcode_to_chart.json`
- 引擎: `backtest/engine/backtest.py`（加载链已优先 v7）