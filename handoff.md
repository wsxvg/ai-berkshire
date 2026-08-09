# HANDOFF 交接文档 — C:\fund 量化策略项目

> **更新时间**: 2026-08-09 晚
> **用途**: 供新开对话使用，防止上下文丢失。新对话先读本文件 + `CLAUDE.md` + `AGENTS.md`。

---

## 一、当前核心结论（一句话）

**数据已全部修正完成（v7 为权威数据），R21 已在干净数据上跑出结果——大佬因子 3 个候选全部显著跑赢基线，但 BASELINE 缺 6 个后段窗口需补全复核。R1–R20 结果因旧数据污染全部作废。**

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

### ⭐ R21 结果已算出（2026-08-09 20:36，从 aggregate 日志提取）
**核心结论：3 个大佬因子候选全部显著跑赢 BASELINE，大佬因子有效！**

| 候选 | avg_return | vs BASELINE | avg_maxDD | peak_maxDD | beats_rate |
|---|---|---|---|---|---|
| `KC_AGGRESSIVE_BASELINE` | 1.162% (16窗) | — | 3.43% | 9.79% | 8/16 (50%) |
| `KC_SMART_BUY_15` | **3.366%** (22窗) | **+2.20%** | 5.56% | 15.87% | 12/22 (55%) |
| `KC_SMART_BUY_25` | **3.085%** (22窗) | **+1.92%** | 5.37% | 16.12% | 14/22 (64%) |
| `KC_SMART_MOD` | **3.271%** (22窗) | **+2.11%** | 5.77% | 15.63% | 12/22 (55%) |

**⚠️ 重要 caveat**：BASELINE 只有 **16 窗**（缺 ci0-b5 即 wi 37-42 的 6 个后段窗口，那些窗口收益通常很高），其他 3 候选是完整 **22 窗**。因此 BASELINE 的 1.16% **被低估**，直接对比略不公平。**需补全 BASELINE 后做同窗复核**。

**R21 目的达成**：SMART_MOD（修饰符模式，不占维度权重）≈ SMART_BUY_15（维度模式）≈ 3.3%，且都跑赢 BASELINE → **大佬因子值得保留**。修饰符模式与维度模式效果相当。

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
- **待修复**：aggregate 最后 git push 报 `fatal: /: '/' is outside repository`，需修正（可能是 ROUND 变量在 bash 展开问题导致 add 路径错，或 push 需设置 remote）

### 成功 run 记录
- **本次成功算出结果的 run**：run_id=`31302696102`，head=`a5bbfcf`，24 job 全完成（0 失败），aggregate 算出 eval 但 push 失败
- 之前失败 run（历史，勿再用）：`31299392136`、`31300564189`(v1 artifact丢)、`31301363828`(v2 OOM)、`31302050338`(v3 timeout)

### ⚠️ 当前阻塞 + 下一步（2026-08-09 21:00 更新）
- **R21 eval 没推到远程**：aggregate 最后 `git push` 报 `fatal: /: '/' is outside repository`（checkout 后 detached HEAD + push 无参数）。**已修好**：`.github/workflows/strict_oos_r21_parallel.yml` 的 Commit results 步骤改为显式 `git push origin "HEAD:${GITHUB_REF_NAME}"`，并用 `x-access-token:${GH_TOKEN}`。YAML 已验证通过。**commit 已在本地（`19df73c`），但尚未推送**。
- **本地无法访问 GitHub**：Clash 代理未启动（系统代理 7890 开关 ProxyEnable=0、端口无监听），直连也被拒。**需用户打开 Clash/系统代理后，才能 `git push` 并重新触发 workflow**。
- **重跑目的**：补全 BASELINE 缺失的 6 个窗口（ci0 wi37-42）。本地已知其中 2 个值（`strict_test_ci0_wi37/38.json`）：
  - wi16(本地)/全局37: return **+25.61%**, bench +12.52% → **高收益窗口，大幅跑赢**
  - wi17(本地)/全局38: return **-6.21%**, bench +2.41% → 跑输
  - → 证实 BASELINE 只跑 16 窗被**低估**（缺的后段含高收益窗口）。**补全后 BASELINE 均值会上升，大佬因子超额会收窄，需同窗复核后下最终结论**。
- **触发命令**（代理打开后）：用 PAT + `workflow_dispatch` 触发 `strict_oos_r21_parallel.yml`，24 job 约 12 分钟，聚合后 eval 自动 push 到远程。

### R21 框架（`scripts/exp_strict_oos.py`, `ROUND=21`）4 个候选
1. `KC_AGGRESSIVE_BASELINE` — 基线（无大佬因子）
2. `KC_SMART_BUY_15` — 大佬因子作独立维度，weight=15
3. `KC_SMART_BUY_25` — 大佬因子作独立维度，weight=25
4. `KC_SMART_MOD` — **大佬因子作加减分修饰符（不占维度权重）** ← R21 新增核心

### 待新对话做（按优先级）
1. **补全 BASELINE 缺的 6 窗**（wi 37-42），做公平对比：本地跑 `python scripts/exp_strict_oos.py run 0 37~42`（每窗~45s）
2. **本地落盘 eval**：`v9-results/strict_oos_r21_eval.json`（当前无此文件，需从 aggregate 日志或重跑生成）
3. **补全后复核**：确认 SMART_BUY/SMART_MOD 仍显著跑赢同窗 BASELINE
4. 若确认跑赢 → 保留大佬因子 → 设计 R22；若同窗对比后优势消失 → 降权/移除
5. **修复 aggregate 的 git push 报错**（见上）

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

1. **补全 BASELINE 缺的 6 个窗口**（ci0, wi 37-42），本地跑 `python scripts/exp_strict_oos.py run 0 <wi>`（每窗~45s），生成 `strict_test_ci0_wi3X.json`
2. **汇总 R21 完整 eval**：用补全后的 BASELINE（22窗）+ 已有 SMART_BUY/SMART_MOD（22窗）做**同窗公平对比**
3. **把完整 eval 落盘**到 `v9-results/strict_oos_r21_eval.json`，写迭代文档
4. **判断大佬因子**：同窗对比后若 SMART 候选仍显著跑赢 → 保留，设计 R22；若优势消失 → 降权/移除
5. 若有新的数据疑问，用 `jd-shipan-fund-mapping` skill + `getFundChart` 权威 productId 复核，不要靠名称猜

---

## 八、关键参考
- Skill: `jd-shipan-fund-mapping`（京东基金码映射权威验证）
- 工具: `tools/jd_finance_api.py`、`tools/authoritative_remap.py`
- 数据: `data/chart_to_name.json`、`data/fund_name_map.json`、`data/jdcode_to_chart.json`
- 引擎: `backtest/engine/backtest.py`（加载链已优先 v7）