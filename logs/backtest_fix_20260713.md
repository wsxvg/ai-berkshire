# 2026-07-13 回测"一直不行" — 根因 & 修复

## 根因(单一)
Windows 默认 stdout 编码是 **GBK** (cp936)。
`backtest_v2.py:735` 用中文 `¥`(U+00A5, GBK 中是孤立 0xA5 字节,非法序列),
输出时直接抛 `UnicodeEncodeError`,回测在最后一步崩,看似"跑不通"。

路径: `C:\项目\A基金\基金` (有中文) 加上 PowerShell 默认 GBK 转发 = 100% 必崩。
切到 `C:\fund` 仍然崩,因为 **GBK 是 Windows 进程级行为,与工作目录无关**。

## 修复
在 `scripts/backtest_v2.py` 和 `scripts/backtest_daily_check.py` 的
`import sys` 之后插入 UTF-8 强制重封装:

```python
import io
...
if sys.platform == 'win32' and hasattr(sys.stdout, 'buffer'):
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    except Exception:
        pass
```

不依赖 `PYTHONIOENCODING` 环境变量 — PowerShell `python` 透传不带 env 时
会回退到系统默认 GBK,设 env 也只在子进程有效,跨 import 调用链未必传到。
直接在脚本顶部重封装最稳。

## 验证 (2026-07-13)
| 脚本 | 区间 | 结果 |
|---|---|---|
| backtest_v2.py (smoke) | 2025-01-01 ~ 2025-12-31 | ✅ +20.74% / 夏普 1.55 / 23买20卖 |
| backtest_v2.py (full) | 2024-03-11 ~ 2026-07-01 | ✅ +60.07% / 年化22.64% / 夏普1.45 / Alpha+5.43% |
| backtest_daily_check.py | 2025-01-01 ~ 2025-12-31 | ✅ 跑通(信号稀缺,5买0卖,这是数据特征非bug) |

落盘: `reports\backtest_v2_full_20260713_165053.json`

## 教训
1. 任何带 `¥` 中文 print 的 Python 脚本,在 Windows 跑都要加 UTF-8 stdout
   (或改用 ASCII `CNY` / `RMB` / `$`)。批量扫一遍 `scripts/`,把 14 个含
   中文 print 的脚本都加上同样防护可避免再踩。
2. `PYTHONIOENCODING` 不是万能 — IDE 内的 python 透传可能不传 env,
   直接重封装 stdout.buffer 才是 portable 解。
