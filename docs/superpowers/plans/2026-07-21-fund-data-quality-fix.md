# 基金数据质量修复与全策略回测重验证 — 实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 修复回测数据质量问题（2187只基金中99.9%只有20天数据），统一回测与实盘数据源，移除评分默认值，全策略重新回测验证Y5策略是否仍然有效。

**架构：** 将分散的两个 `fund_charts.json` 文件统一为按基金拆分的 `data/fund_charts/{code}.json` 目录结构，通过 `tools/chart_loader.py` 统一加载。JD API（无需Cookie）拉取全量历史净值。移除评分函数中的默认值2.5，改为 `score=-1, weight=0` 使数据缺失可见。GitHub Actions 运行全策略回测。

**技术栈：** Python 3.11, stdlib only（jd_finance_api.py 零外部依赖）, GitHub Actions matrix, pytest

**设计文档：** `docs/superpowers/specs/2026-07-21-fund-data-quality-fix-design.md`

---

## 文件结构

### 新建文件

| 文件 | 职责 |
|------|------|
| `tools/chart_loader.py` | 统一数据加载模块：load_all_charts / load_single_chart / update_chart / get_chart_index |
| `scripts/bulk_fetch_charts.py` | 批量拉取全量历史净值脚本 |
| `scripts/preflight_check.py` | 回测前数据准确性预检脚本 |
| `tests/test_chart_loader.py` | chart_loader 单元测试 |
| `tests/test_scoring_no_defaults.py` | 评分默认值移除验证测试 |
| `.github/workflows/backtest-full-revalidation.yml` | 全策略回测 GitHub Actions 工作流 |
| `.github/workflows/daily-chart-update.yml` | 每日净值增量更新工作流 |

### 修改文件

| 文件 | 改动 |
|------|------|
| `backtest/engine/backtest.py` | L1321 数据加载改为 `load_all_charts()`；L110-111/L148-149 移除默认值2.5；L811-812 总分计算权重归一化 |
| `scripts/daily_live.py` | L70 数据加载改为 `load_all_charts()`；L155-172 替换 eastmoney_api 为 JD API；L240-243 增量更新改为写 per-fund 文件 |
| `scripts/update_fund_charts.py` | 改为操作 `data/fund_charts/` 目录而非单文件 |

---

## 任务 1：创建 `tools/chart_loader.py` — 统一数据加载模块

**文件：**
- 创建：`tools/chart_loader.py`
- 测试：`tests/test_chart_loader.py`

- [ ] **步骤 1：编写失败的测试**

创建 `tests/test_chart_loader.py`：

```python
"""Tests for chart_loader — unified fund chart data access."""
from __future__ import annotations
import pytest
import json
import tempfile
from pathlib import Path
import sys

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from tools.chart_loader import load_all_charts, load_single_chart, update_chart, get_chart_index


class TestChartLoader:
    """chart_loader 核心功能测试"""

    def setup_method(self):
        """用临时目录测试，不碰真实数据"""
        self.tmpdir = tempfile.mkdtemp()
        self.charts_dir = Path(self.tmpdir) / "fund_charts"
        self.charts_dir.mkdir(parents=True, exist_ok=True)

    def teardown_method(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_load_single_chart_returns_empty_for_nonexistent(self):
        """不存在的基金返回空列表"""
        result = load_single_chart("999999", self.charts_dir)
        assert result == []

    def test_update_chart_creates_file(self):
        """update_chart 创建基金文件"""
        pts = [{"xAxis": "2026-01-15", "yAxis": 5.23}, {"xAxis": "2026-01-16", "yAxis": 5.50}]
        update_chart("110020", pts, self.charts_dir)
        assert (self.charts_dir / "110020.json").exists()
        loaded = json.loads((self.charts_dir / "110020.json").read_text("utf-8"))
        assert loaded == pts

    def test_load_single_chart_returns_data(self):
        """load_single_chart 读取已存在文件"""
        pts = [{"xAxis": "2026-01-15", "yAxis": 5.23}]
        update_chart("110020", pts, self.charts_dir)
        result = load_single_chart("110020", self.charts_dir)
        assert result == pts

    def test_load_all_charts_returns_dict(self):
        """load_all_charts 返回 {code: [points]} 字典"""
        update_chart("110020", [{"xAxis": "2026-01-15", "yAxis": 5.23}], self.charts_dir)
        update_chart("005698", [{"xAxis": "2026-01-15", "yAxis": 10.0}], self.charts_dir)
        result = load_all_charts(self.charts_dir)
        assert isinstance(result, dict)
        assert len(result) == 2
        assert "110020" in result
        assert "005698" in result
        assert result["110020"] == [{"xAxis": "2026-01-15", "yAxis": 5.23}]

    def test_load_all_charts_empty_dir_returns_empty_dict(self):
        """空目录返回空字典"""
        result = load_all_charts(self.charts_dir)
        assert result == {}

    def test_update_chart_creates_index(self):
        """update_chart 同时更新索引文件"""
        pts = [{"xAxis": "2026-01-15", "yAxis": 5.23}, {"xAxis": "2026-07-21", "yAxis": 10.0}]
        update_chart("110020", pts, self.charts_dir)
        index = get_chart_index(self.charts_dir)
        assert "110020" in index
        assert index["110020"]["count"] == 2
        assert index["110020"]["first_date"] == "2026-01-15"
        assert index["110020"]["last_date"] == "2026-07-21"

    def test_update_chart_overwrites_existing(self):
        """update_chart 覆盖已有文件"""
        update_chart("110020", [{"xAxis": "2026-01-15", "yAxis": 5.23}], self.charts_dir)
        update_chart("110020", [{"xAxis": "2026-01-15", "yAxis": 5.23}, {"xAxis": "2026-01-16", "yAxis": 5.50}], self.charts_dir)
        result = load_single_chart("110020", self.charts_dir)
        assert len(result) == 2
```

- [ ] **步骤 2：运行测试验证失败**

运行：`python -m pytest tests/test_chart_loader.py -v`
预期：FAIL，报错 `ModuleNotFoundError: No module named 'tools.chart_loader'`

- [ ] **步骤 3：编写实现代码**

创建 `tools/chart_loader.py`：

```python
"""统一基金净值数据加载模块。

回测引擎和实盘模拟共用此模块，确保数据一致性。
数据存储: data/fund_charts/{code}.json (每只基金一个文件)
索引文件: data/fund_charts_index.json (轻量元数据)

文件格式: [{xAxis: "2026-01-15", yAxis: 5.23}, ...]
yAxis = 累计收益率% (与回测引擎完全兼容)
"""
import json
from pathlib import Path
from datetime import datetime

PROJECT = Path(__file__).resolve().parent.parent
DEFAULT_CHARTS_DIR = PROJECT / "data" / "fund_charts"


def load_all_charts(charts_dir: Path = None) -> dict:
    """加载目录下所有基金chart数据。

    返回 {code: [{xAxis, yAxis}, ...]} 字典。
    与回测引擎的 fund_charts 变量格式完全兼容。
    """
    charts_dir = Path(charts_dir) if charts_dir else DEFAULT_CHARTS_DIR
    if not charts_dir.exists():
        return {}
    result = {}
    for f in charts_dir.glob("*.json"):
        try:
            result[f.stem] = json.loads(f.read_text("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
    return result


def load_single_chart(code: str, charts_dir: Path = None) -> list:
    """加载单只基金chart数据。

    返回 [{xAxis, yAxis}, ...] 列表，不存在则返回空列表。
    """
    charts_dir = Path(charts_dir) if charts_dir else DEFAULT_CHARTS_DIR
    f = charts_dir / f"{code}.json"
    if not f.exists():
        return []
    try:
        return json.loads(f.read_text("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return []


def update_chart(code: str, points: list, charts_dir: Path = None) -> None:
    """更新单只基金chart数据 + 索引。

    覆盖写入 data/fund_charts/{code}.json，同时更新索引文件。
    """
    charts_dir = Path(charts_dir) if charts_dir else DEFAULT_CHARTS_DIR
    charts_dir.mkdir(parents=True, exist_ok=True)

    # 写入基金数据文件
    f = charts_dir / f"{code}.json"
    f.write_text(json.dumps(points, ensure_ascii=False), encoding="utf-8")

    # 更新索引
    _update_index(code, points, charts_dir)


def _update_index(code: str, points: list, charts_dir: Path) -> None:
    """更新索引文件中的单条记录。"""
    index_file = charts_dir.parent / "fund_charts_index.json"
    try:
        index = json.loads(index_file.read_text("utf-8")) if index_file.exists() else {}
    except (json.JSONDecodeError, UnicodeDecodeError):
        index = {}

    if points:
        dates = [p.get("xAxis", "") for p in points]
        index[code] = {
            "count": len(points),
            "first_date": min(dates) if dates else "",
            "last_date": max(dates) if dates else "",
            "last_update": datetime.now().strftime("%Y-%m-%d"),
        }
    else:
        index.pop(code, None)

    index_file.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")


def get_chart_index(charts_dir: Path = None) -> dict:
    """读取索引文件，返回 {code: {count, first_date, last_date, last_update}}。"""
    charts_dir = Path(charts_dir) if charts_dir else DEFAULT_CHARTS_DIR
    index_file = charts_dir.parent / "fund_charts_index.json"
    if not index_file.exists():
        return {}
    try:
        return json.loads(index_file.read_text("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {}
```

- [ ] **步骤 4：运行测试验证通过**

运行：`python -m pytest tests/test_chart_loader.py -v`
预期：7 passed

- [ ] **步骤 5：Commit**

```bash
git add tools/chart_loader.py tests/test_chart_loader.py
git commit -m "添加统一基金数据加载模块 chart_loader"
```

---

## 任务 2：迁移现有数据到 per-fund 文件

**文件：**
- 创建：`scripts/migrate_charts.py`（一次性迁移脚本，用完可删）

- [ ] **步骤 1：编写迁移脚本**

创建 `scripts/migrate_charts.py`：

```python
"""一次性迁移：把两个 fund_charts.json 合并到 data/fund_charts/ 目录。

数据源：
  1. data/fund_charts.json (实盘, 273只, 数据良好)
  2. backtest/data/fund_charts.json (回测, 2187只, 大部分只有20天)

合并策略：同基金取数据点更多的版本。
"""
import json
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))

from tools.chart_loader import update_chart

LIVE_FILE = PROJECT / "data" / "fund_charts.json"
BACKTEST_FILE = PROJECT / "backtest" / "data" / "fund_charts.json"
TARGET_DIR = PROJECT / "data" / "fund_charts"


def main():
    live = json.loads(LIVE_FILE.read_text("utf-8")) if LIVE_FILE.exists() else {}
    bt = json.loads(BACKTEST_FILE.read_text("utf-8")) if BACKTEST_FILE.exists() else {}

    print(f"实盘数据: {len(live)} 只")
    print(f"回测数据: {len(bt)} 只")

    all_codes = set(live.keys()) | set(bt.keys())
    print(f"合并去重: {len(all_codes)} 只")

    migrated = 0
    for code in sorted(all_codes):
        live_pts = live.get(code, [])
        bt_pts = bt.get(code, [])
        # 取数据点更多的版本
        pts = live_pts if len(live_pts) >= len(bt_pts) else bt_pts
        if pts:
            update_chart(code, pts, TARGET_DIR)
            migrated += 1

    print(f"已迁移: {migrated} 只 → {TARGET_DIR}")

    # 重命名旧文件为 .bak
    if LIVE_FILE.exists():
        LIVE_FILE.rename(str(LIVE_FILE) + ".bak")
        print(f"  {LIVE_FILE.name} → {LIVE_FILE.name}.bak")
    if BACKTEST_FILE.exists():
        BACKTEST_FILE.rename(str(BACKTEST_FILE) + ".bak")
        print(f"  {BACKTEST_FILE.name} → {BACKTEST_FILE.name}.bak")

    print("迁移完成。旧文件已重命名为 .bak")


if __name__ == "__main__":
    main()
```

- [ ] **步骤 2：运行迁移脚本**

运行：`python scripts/migrate_charts.py`
预期输出：`已迁移: 2187 只 → data/fund_charts`

- [ ] **步骤 3：验证迁移结果**

运行：
```bash
python -c "import json; from pathlib import Path; d=Path('data/fund_charts'); print(f'Files: {len(list(d.glob(\"*.json\")))}'); idx=json.loads(Path('data/fund_charts_index.json').read_text('utf-8')); print(f'Index entries: {len(idx)}')"
```
预期：Files 和 Index entries 都 ≈ 2187

- [ ] **步骤 4：Commit**

```bash
git add scripts/migrate_charts.py data/fund_charts_index.json
git commit -m "迁移基金净值数据到 per-fund 文件结构"
```

---

## 任务 3：修改回测引擎数据加载方式

**文件：**
- 修改：`backtest/engine/backtest.py:1321-1322`

- [ ] **步骤 1：修改数据加载行**

在 `backtest/engine/backtest.py` 中，找到第 1321-1322 行：

```python
with open(DATA_DIR / "fund_charts.json", "r", encoding="utf-8") as f:
    fund_charts = json.load(f)
```

替换为：

```python
from tools.chart_loader import load_all_charts
fund_charts = load_all_charts()
print(f"[DATA] 加载 {len(fund_charts)} 只基金净值数据")
```

- [ ] **步骤 2：验证回测引擎能加载数据**

运行：
```bash
python -c "import sys; sys.path.insert(0,'.'); from tools.chart_loader import load_all_charts; charts=load_all_charts(); print(f'Loaded {len(charts)} funds'); lens=[len(v) for v in charts.values()]; print(f'Min:{min(lens)} Max:{max(lens)} Avg:{sum(lens)/len(lens):.1f}')"
```
预期：Loaded ~2187 funds, 数据点分布与迁移前一致

- [ ] **步骤 3：运行现有回测测试确保无回归**

运行：`python -m pytest tests/test_backtest_integrity.py -v`
预期：所有测试通过

- [ ] **步骤 4：Commit**

```bash
git add backtest/engine/backtest.py
git commit -m "回测引擎改用 chart_loader 统一加载基金数据"
```

---

## 任务 4：修改 daily_live.py 数据加载方式

**文件：**
- 修改：`scripts/daily_live.py:70` 和 `scripts/daily_live.py:240-243`

- [ ] **步骤 1：修改数据加载行（L70）**

找到第 70 行：

```python
fund_charts = json.loads((PROJECT / "data" / "fund_charts.json").read_text("utf-8"))
```

替换为：

```python
from tools.chart_loader import load_all_charts
fund_charts = load_all_charts()
```

- [ ] **步骤 2：修改增量更新后的重载逻辑（L240-243）**

找到第 239-243 行：

```python
            update_charts_file(PROJECT / "data" / "fund_charts.json", max_funds=0)
            # 重新加载更新后的 fund_charts
            global fund_charts
            fund_charts = json.loads((PROJECT / "data" / "fund_charts.json").read_text("utf-8"))
```

替换为：

```python
            from tools.chart_loader import load_all_charts as _lac
            # update_fund_charts.py 现在直接写 per-fund 文件
            update_charts_file(PROJECT / "data" / "fund_charts", max_funds=0)
            # 重新加载更新后的 fund_charts
            global fund_charts
            fund_charts = _lac()
```

- [ ] **步骤 3：验证 daily_live.py 能正常 import**

运行：
```bash
python -c "import sys; sys.path.insert(0,'.'); from scripts.daily_live import *; print('daily_live import OK')"
```
预期：无报错（可能有 best_config.json 相关的打印输出）

- [ ] **步骤 4：Commit**

```bash
git add scripts/daily_live.py
git commit -m "daily_live 改用 chart_loader 加载数据"
```

---

## 任务 5：修改 update_fund_charts.py 操作 per-fund 目录

**文件：**
- 修改：`scripts/update_fund_charts.py:186-285`（`update_charts_file` 函数）

- [ ] **步骤 1：修改 update_charts_file 函数**

读取 `scripts/update_fund_charts.py` 的 `update_charts_file` 函数（约 L186 开始），将其改为操作 per-fund 目录而非单文件。

核心改动：
- 输入参数 `charts_path` 改为接受目录路径或文件路径（向后兼容）
- 如果是目录：逐基金写入 `{dir}/{code}.json`，用 `update_chart()` 函数
- 如果是文件（旧模式）：保持原逻辑，打 deprecation 警告

找到 `def update_charts_file(charts_path: Path, max_funds: int = 0, force_full: bool = False):` 函数，在函数开头添加路径判断：

```python
def update_charts_file(charts_path: Path, max_funds: int = 0, force_full: bool = False):
    """更新基金净值数据。

    charts_path 可以是目录 (data/fund_charts/) 或文件 (旧 data/fund_charts.json)。
    目录模式: 每只基金写入 {dir}/{code}.json (推荐)
    文件模式: 写入单个 JSON 文件 (兼容旧代码, 会打 deprecation 警告)
    """
    charts_path = Path(charts_path)
    is_dir_mode = charts_path.is_dir() or (not charts_path.exists() and not charts_path.suffix)

    if is_dir_mode:
        _update_charts_dir(charts_path, max_funds, force_full)
        return
    # 旧文件模式
    import warnings
    warnings.warn("单文件模式已废弃，请改用目录模式", DeprecationWarning, stacklevel=2)
    # ... 原有单文件逻辑保持不变 ...
```

新增 `_update_charts_dir` 函数：

```python
def _update_charts_dir(charts_dir: Path, max_funds: int = 0, force_full: bool = False):
    """目录模式：逐基金增量更新。"""
    from tools.chart_loader import load_single_chart, update_chart
    charts_dir.mkdir(parents=True, exist_ok=True)
    cookies = _get_cookies()

    # 获取已有基金列表
    existing_codes = [f.stem for f in charts_dir.glob("*.json")]
    if max_funds > 0:
        existing_codes = existing_codes[:max_funds]

    print(f"  目录模式: 更新 {len(existing_codes)} 只基金 ({charts_dir})")

    updated = 0
    failed = 0
    for i, code in enumerate(existing_codes):
        pts = load_single_chart(code, charts_dir)
        new_pts, new_days = update_single_fund(code, pts, cookies, force_full)
        if new_days > 0:
            update_chart(code, new_pts, charts_dir)
            updated += 1
        elif new_days == 0 and new_pts != pts:
            update_chart(code, new_pts, charts_dir)
            updated += 1
        else:
            failed += 1

        if (i + 1) % 50 == 0:
            print(f"  [{i+1}/{len(existing_codes)}] updated={updated} failed={failed}")
        time.sleep(0.1)

    print(f"  完成: updated={updated} failed={failed} total={len(existing_codes)}")
```

- [ ] **步骤 2：测试增量更新**

运行：
```bash
python -c "
import sys; sys.path.insert(0, '.')
from scripts.update_fund_charts import update_charts_file
from pathlib import Path
update_charts_file(Path('data/fund_charts'), max_funds=3)
"
```
预期：更新 3 只基金，无报错

- [ ] **步骤 3：Commit**

```bash
git add scripts/update_fund_charts.py
git commit -m "update_fund_charts 支持目录模式写入 per-fund 文件"
```

---

## 任务 6：创建批量拉取脚本

**文件：**
- 创建：`scripts/bulk_fetch_charts.py`

- [ ] **步骤 1：编写批量拉取脚本**

创建 `scripts/bulk_fetch_charts.py`：

```python
"""批量拉取所有基金的全量历史净值。

数据源: JD API getFundHistoryNetValuePageInfo (无需 Cookie)
输出: data/fund_charts/{code}.json + 更新索引

用法:
  python scripts/bulk_fetch_charts.py                    # 拉取所有缺失的基金
  python scripts/bulk_fetch_charts.py --force             # 全量重拉
  python scripts/bulk_fetch_charts.py --code 110020       # 拉单只
  python scripts/bulk_fetch_charts.py --max 50            # 最多拉50只
"""
import json
import sys
import time
import argparse
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))

from tools.jd_finance_api import _api_post
from tools.chart_loader import load_single_chart, update_chart, get_chart_index
from tools.eastmoney_api import get_all_funds

CHARTS_DIR = PROJECT / "data" / "fund_charts"
TRADING_FILE = PROJECT / "backtest" / "data" / "trading_by_date_fixed.json"
NAME_MAP_FILE = PROJECT / "data" / "fund_name_map.json"


def fetch_full_nav(code: str, max_pages: int = 10) -> list:
    """JD API 拉取全量净值，返回 [{xAxis, yAxis}, ...] 格式。"""
    all_nav = []
    for page in range(1, max_pages + 1):
        data = _api_post(
            "gw/generic/jj/h5/m/getFundHistoryNetValuePageInfo",
            {"fundCode": code, "pageNum": page, "pageSize": 2000},
            cookies={},
        )
        nav_list = data.get("resultData", {}).get("datas", {}).get("netValueList", [])
        if not nav_list:
            break
        all_nav.extend(nav_list)
        if len(nav_list) < 2000:
            break
        time.sleep(0.15)

    if not all_nav:
        return []

    # 按日期升序
    all_nav.sort(key=lambda x: x.get("date", ""))

    # 用最早的有效净值作为基准
    base_nav = None
    for n in all_nav:
        try:
            v = float(n.get("netValue", 0))
            if v > 0:
                base_nav = v
                break
        except (ValueError, TypeError):
            continue

    if not base_nav:
        return []

    # 转换为 chart 格式
    pts = []
    for n in all_nav:
        try:
            v = float(n.get("netValue", 0))
            if v <= 0:
                continue
            yaxis = (v / base_nav - 1.0) * 100
            pts.append({"xAxis": n.get("date", ""), "yAxis": round(yaxis, 4)})
        except (ValueError, TypeError):
            continue
    return pts


def collect_fund_codes() -> set:
    """合并三来源基金代码列表。"""
    codes = set()

    # 来源1: 交易记录
    if TRADING_FILE.exists():
        data = json.loads(TRADING_FILE.read_text("utf-8"))
        for d, recs in data.items():
            for r in recs:
                c = r.get("fund_code", "")
                if c:
                    codes.add(c)

    # 来源2: 名称映射
    if NAME_MAP_FILE.exists():
        nm = json.loads(NAME_MAP_FILE.read_text("utf-8"))
        codes.update(nm.values())

    # 来源3: 现有 charts 目录
    if CHARTS_DIR.exists():
        for f in CHARTS_DIR.glob("*.json"):
            codes.add(f.stem)

    # 来源4: 全市场 Top 2000
    print("拉取全市场基金列表 (Top 2000)...")
    try:
        r = get_all_funds(sort_by="1n", max_funds=2000)
        for item in r["rankings"]:
            codes.add(item["code"])
        print(f"  全市场获取 {len(r['rankings'])} 只")
    except Exception as e:
        print(f"  全市场拉取失败(非致命): {e}")

    # 过滤空字符串
    codes.discard("")
    return codes


def main():
    parser = argparse.ArgumentParser(description="批量拉取基金全量历史净值")
    parser.add_argument("--code", type=str, help="只拉单只基金")
    parser.add_argument("--force", action="store_true", help="强制重拉已有基金")
    parser.add_argument("--max", type=int, default=0, help="最多拉取数量 (0=全部)")
    args = parser.parse_args()

    CHARTS_DIR.mkdir(parents=True, exist_ok=True)

    if args.code:
        codes = {args.code}
    else:
        codes = collect_fund_codes()

    # 过滤已存在的（除非 --force）
    if not args.force:
        index = get_chart_index(CHARTS_DIR)
        existing = {c for c, info in index.items() if info.get("count", 0) >= 20}
        codes = codes - existing
        print(f"已有足够数据: {len(existing)} 只, 待拉取: {len(codes)} 只")
    else:
        print(f"强制重拉: {len(codes)} 只")

    if args.max > 0:
        codes = set(sorted(codes)[:args.max])
        print(f"限制最多 {args.max} 只")

    if not codes:
        print("无待拉取基金")
        return

    print(f"\n开始拉取 {len(codes)} 只基金...")
    ok = fail = 0
    failed_list = []

    for i, code in enumerate(sorted(codes)):
        try:
            pts = fetch_full_nav(code)
            if pts:
                update_chart(code, pts, CHARTS_DIR)
                ok += 1
                if (i + 1) % 50 == 0:
                    print(f"  [{i+1}/{len(codes)}] ok={ok} fail={fail} (last: {code} {len(pts)}天)")
            else:
                fail += 1
                failed_list.append(code)
        except Exception as e:
            fail += 1
            failed_list.append(code)
            if (i + 1) % 50 == 0:
                print(f"  [{i+1}/{len(codes)}] ok={ok} fail={fail} ERR: {e}")

        time.sleep(0.15)

    print(f"\n=== 完成 ===")
    print(f"成功: {ok}, 失败: {fail}, 总计: {ok + fail}")

    if failed_list:
        print(f"\n失败列表 (前20个): {failed_list[:20]}")
        # 保存失败列表供后续重试
        (PROJECT / "data" / "bulk_fetch_failed.json").write_text(
            json.dumps(failed_list, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
```

- [ ] **步骤 2：测试单只基金拉取**

运行：`python scripts/bulk_fetch_charts.py --code 110020`
预期：成功拉取 110020 的全量历史净值

- [ ] **步骤 3：验证拉取结果**

运行：
```bash
python -c "import sys; sys.path.insert(0,'.'); from tools.chart_loader import load_single_chart; pts=load_single_chart('110020'); print(f'Points: {len(pts)}, First: {pts[0]}, Last: {pts[-1]}')"
```
预期：Points > 1000（110020 是老基金，应该有很多数据）

- [ ] **步骤 4：Commit**

```bash
git add scripts/bulk_fetch_charts.py
git commit -m "添加批量拉取基金全量历史净值脚本"
```

---

## 任务 7：运行批量拉取

**文件：**
- 无新建文件（运行任务 6 的脚本）

- [ ] **步骤 1：运行批量拉取（全部缺失基金）**

运行：`python scripts/bulk_fetch_charts.py`

预期耗时：约 1 小时（~4000 只基金）
预期输出：`成功: ~3500, 失败: ~500`

- [ ] **步骤 2：重试失败列表**

运行：`python scripts/bulk_fetch_charts.py`（再次运行会自动跳过已成功的）

- [ ] **步骤 3：验证数据质量**

运行：
```bash
python -c "
import sys, collections; sys.path.insert(0, '.')
from tools.chart_loader import load_all_charts
charts = load_all_charts()
lens = [len(v) for v in charts.values()]
c = collections.Counter()
for l in lens:
    bucket = next((b for b in [1,20,63,126,252,500,1000,99999] if l <= b), 99999)
    c[bucket] += 1
print(f'Total funds: {len(charts)}')
print('Distribution:')
for b in sorted(c.keys()):
    print(f'  <= {b} points: {c[b]} funds')
"
```
预期：大部分基金 ≥ 252 天数据

- [ ] **步骤 4：Commit**

```bash
git add data/fund_charts/ data/fund_charts_index.json
git commit -m "批量拉取基金全量历史净值数据"
```

---

## 任务 8：创建数据预检脚本

**文件：**
- 创建：`scripts/preflight_check.py`

- [ ] **步骤 1：编写预检脚本**

创建 `scripts/preflight_check.py`：

```python
"""回测前数据准确性预检。

检查所有交易记录涉及的基金是否具备：
1. 净值数据 (≥252天)
2. 交易规则 (trade_rules)
3. 基金档案 (fund_profile)
4. 基金经理 (fund_manager)
5. 持仓分布 (fund_holdings)

缺失则自动批量拉取。
"""
import json
import sys
import time
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))

from tools.chart_loader import get_chart_index, load_single_chart
from tools.jd_finance_api import (
    get_fund_trade_rules, get_fund_detail, get_fund_manager_detail,
    get_fund_holdings_distribution,
)

TRADING_FILE = PROJECT / "backtest" / "data" / "trading_by_date_fixed.json"
CACHE_DIR = PROJECT / "data" / "fund_cache"
CHARTS_DIR = PROJECT / "data" / "fund_charts"


def get_trading_fund_codes() -> set:
    """从交易记录提取所有基金代码。"""
    data = json.loads(TRADING_FILE.read_text("utf-8"))
    codes = set()
    for d, recs in data.items():
        for r in recs:
            c = r.get("fund_code", "")
            if c:
                codes.add(c)
    return codes


def check_charts(codes: set) -> dict:
    """检查净值数据完整性。"""
    index = get_chart_index(CHARTS_DIR)
    sufficient = set()
    insufficient = set()
    missing = set()

    for code in codes:
        info = index.get(code, {})
        count = info.get("count", 0)
        if count >= 252:
            sufficient.add(code)
        elif count >= 20:
            insufficient.add(code)
        else:
            missing.add(code)

    return {
        "sufficient": sufficient,
        "insufficient": insufficient,
        "missing": missing,
    }


def check_cache(codes: set, prefix: str) -> set:
    """检查 fund_cache 中某类数据是否存在。"""
    existing = set()
    for f in CACHE_DIR.glob(f"{prefix}_*.json"):
        existing.add(f.stem.replace(f"{prefix}_", "", 1))
    return codes - existing


def fetch_missing(codes: set, data_type: str) -> None:
    """批量拉取缺失数据。"""
    if not codes:
        print(f"  {data_type}: 全部就绪")
        return

    print(f"  {data_type}: 缺失 {len(codes)} 只，正在拉取...")
    ok = fail = 0
    for i, code in enumerate(sorted(codes)):
        try:
            if data_type == "trade_rules":
                get_fund_trade_rules(code)
            elif data_type == "fund_profile":
                get_fund_detail(code)
            elif data_type == "fund_manager":
                get_fund_manager_detail(code)
            elif data_type == "fund_holdings":
                get_fund_holdings_distribution(code)
            ok += 1
        except Exception:
            fail += 1
        time.sleep(0.1)
        if (i + 1) % 50 == 0:
            print(f"    [{i+1}/{len(codes)}] ok={ok} fail={fail}")
    print(f"    完成: ok={ok} fail={fail}")


def main():
    print("=== 数据准确性预检 ===")
    codes = get_trading_fund_codes()
    print(f"交易记录涉及基金: {len(codes)} 只\n")

    # 1. 检查净值数据
    print("[1/5] 净值数据 (fund_charts)")
    chart_status = check_charts(codes)
    print(f"  ≥252天: {len(chart_status['sufficient'])} 只")
    print(f"  20-251天: {len(chart_status['insufficient'])} 只")
    print(f"  缺失: {len(chart_status['missing'])} 只")

    if chart_status["missing"] or chart_status["insufficient"]:
        need_fetch = chart_status["missing"] | chart_status["insufficient"]
        print(f"  正在拉取 {len(need_fetch)} 只基金的全量历史...")
        from scripts.bulk_fetch_charts import fetch_full_nav
        from tools.chart_loader import update_chart
        for i, code in enumerate(sorted(need_fetch)):
            try:
                pts = fetch_full_nav(code)
                if pts:
                    update_chart(code, pts, CHARTS_DIR)
            except Exception:
                pass
            time.sleep(0.15)
            if (i + 1) % 50 == 0:
                print(f"    [{i+1}/{len(need_fetch)}]")

    # 2-5. 检查缓存数据
    print("\n[2/5] 交易规则 (trade_rules)")
    missing = check_cache(codes, "trade_rules")
    fetch_missing(missing, "trade_rules")

    print("\n[3/5] 基金档案 (fund_profile)")
    missing = check_cache(codes, "fund_profile")
    fetch_missing(missing, "fund_profile")

    print("\n[4/5] 基金经理 (fund_manager)")
    missing = check_cache(codes, "fund_manager")
    fetch_missing(missing, "fund_manager")

    print("\n[5/5] 持仓分布 (fund_holdings)")
    missing = check_cache(codes, "fund_holdings")
    fetch_missing(missing, "fund_holdings")

    # 最终汇总
    print("\n=== 预检完成 ===")
    chart_status = check_charts(codes)
    print(f"净值 ≥252天: {len(chart_status['sufficient'])}/{len(codes)} ({len(chart_status['sufficient'])/len(codes)*100:.1f}%)")
    print(f"交易规则: {len(codes) - len(check_cache(codes, 'trade_rules'))}/{len(codes)}")
    print(f"基金档案: {len(codes) - len(check_cache(codes, 'fund_profile'))}/{len(codes)}")
    print(f"基金经理: {len(codes) - len(check_cache(codes, 'fund_manager'))}/{len(codes)}")
    print(f"持仓分布: {len(codes) - len(check_cache(codes, 'fund_holdings'))}/{len(codes)}")


if __name__ == "__main__":
    main()
```

- [ ] **步骤 2：测试预检脚本**

运行：`python scripts/preflight_check.py`
预期：输出各类数据覆盖率

- [ ] **步骤 3：Commit**

```bash
git add scripts/preflight_check.py
git commit -m "添加回测前数据准确性预检脚本"
```

---

## 任务 9：移除评分默认值

**文件：**
- 修改：`backtest/engine/backtest.py:110-111` 和 `backtest/engine/backtest.py:148-149`
- 测试：`tests/test_scoring_no_defaults.py`

- [ ] **步骤 1：编写失败的测试**

创建 `tests/test_scoring_no_defaults.py`：

```python
"""Tests for scoring default value removal — data insufficiency must be visible."""
from __future__ import annotations
import pytest
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from tools.fund_scorer import DimensionScore
from backtest.engine.backtest import score_momentum_backtest, score_quality_backtest


class TestScoringNoDefaults:
    """验证评分函数不再用默认值2.5掩盖数据不足"""

    def test_momentum_insufficient_data_returns_zero_weight(self):
        """数据<20天时，动量分weight=0（不参与加权）"""
        few_points = [{"xAxis": f"2026-01-{i:02d}", "yAxis": float(i)} for i in range(1, 11)]
        result = score_momentum_backtest(few_points, "2026-01-15")
        assert result.weight == 0, f"数据不足时weight应为0, 实际={result.weight}"

    def test_quality_insufficient_data_returns_zero_weight(self):
        """数据<20天时，质量分weight=0（不参与加权）"""
        few_points = [{"xAxis": f"2026-01-{i:02d}", "yAxis": float(i)} for i in range(1, 11)]
        result = score_quality_backtest(few_points, "2026-01-15")
        assert result.weight == 0, f"数据不足时weight应为0, 实际={result.weight}"

    def test_momentum_sufficient_data_returns_normal_weight(self):
        """数据≥20天时，动量分weight>0（正常参与加权）"""
        points = [{"xAxis": f"2026-01-{i:02d}", "yAxis": float(i) * 0.1} for i in range(1, 31)]
        result = score_momentum_backtest(points, "2026-01-30")
        assert result.weight > 0, f"数据充足时weight应>0, 实际={result.weight}"

    def test_quality_sufficient_data_returns_normal_weight(self):
        """数据≥20天时，质量分weight>0（正常参与加权）"""
        points = [{"xAxis": f"2026-01-{i:02d}", "yAxis": float(i) * 0.1} for i in range(1, 31)]
        result = score_quality_backtest(points, "2026-01-30")
        assert result.weight > 0, f"数据充足时weight应>0, 实际={result.weight}"

    def test_momentum_empty_data_returns_zero_weight(self):
        """空数据时weight=0"""
        result = score_momentum_backtest([], "2026-01-15")
        assert result.weight == 0

    def test_quality_empty_data_returns_zero_weight(self):
        """空数据时weight=0"""
        result = score_quality_backtest([], "2026-01-15")
        assert result.weight == 0
```

- [ ] **步骤 2：运行测试验证失败**

运行：`python -m pytest tests/test_scoring_no_defaults.py -v`
预期：FAIL，因为当前数据不足时返回 `weight=0.15` 或 `weight=0.25`

- [ ] **步骤 3：修改 score_momentum_backtest（L110-111）**

找到 `backtest/engine/backtest.py` 第 110-111 行：

```python
    if len(valid) < 20:
        return DimensionScore(score=2.5, weight=0.15, freshness_days=0)
```

替换为：

```python
    if len(valid) < 20:
        return DimensionScore(score=-1, weight=0, freshness_days=0)
```

- [ ] **步骤 4：修改 score_quality_backtest（L148-149）**

找到第 148-149 行：

```python
    if len(valid) < 20:
        return DimensionScore(score=2.5, weight=0.25, freshness_days=0)
```

替换为：

```python
    if len(valid) < 20:
        return DimensionScore(score=-1, weight=0, freshness_days=0)
```

- [ ] **步骤 5：修改总分计算中的权重归一化（L811-812）**

找到第 811-812 行：

```python
    dims = [quality, cost, manager_dim, momentum, smart]
    raw = sum(d.score * d.weight for d in dims) / max(sum(d.weight for d in dims), 0.01)
```

替换为：

```python
    dims = [quality, cost, manager_dim, momentum, smart]
    # 过滤掉数据不足的维度（weight=0），只用有效维度加权
    valid_dims = [d for d in dims if d.weight > 0]
    total_weight = sum(d.weight for d in valid_dims)
    if total_weight > 0:
        raw = sum(d.score * d.weight for d in valid_dims) / total_weight
    else:
        raw = 0  # 所有维度都数据不足，得0分
```

- [ ] **步骤 6：运行测试验证通过**

运行：`python -m pytest tests/test_scoring_no_defaults.py -v`
预期：6 passed

- [ ] **步骤 7：运行所有回测测试确保无回归**

运行：`python -m pytest tests/test_backtest_integrity.py tests/test_scoring_no_defaults.py tests/test_chart_loader.py -v`
预期：全部通过

- [ ] **步骤 8：Commit**

```bash
git add backtest/engine/backtest.py tests/test_scoring_no_defaults.py
git commit -m "移除评分默认值，数据不足时weight=0不参与加权"
```

---

## 任务 10：修复 daily_live.py 新基金获取流程

**文件：**
- 修改：`scripts/daily_live.py:152-172`

- [ ] **步骤 1：替换 eastmoney_api 为 JD API**

找到 `scripts/daily_live.py` 第 152-172 行：

```python
    # 自动拉取新基金的历史净值
    if new_fund_codes:
        print(f"  发现 {len(new_fund_codes)} 只新基金，自动拉取历史净值...")
        from tools.eastmoney_api import get_fund_nav_history
        for code in new_fund_codes:
            try:
                nav = get_fund_nav_history(code, max_pages=40)
                if nav:
                    # 转换为chart格式 (累计收益率%)
                    if nav:
                        base = nav[0]["nav"]
                        pts = [{"xAxis": n["date"], "yAxis": (n["nav"] / base - 1) * 100} for n in nav]
                        fund_charts[code] = pts
                        print(f"    {code}: 拉取 {len(pts)} 天历史")
            except Exception as e:
                print(f"    {code}: 拉取失败 {e}")
            time.sleep(0.3)
        # 保存更新后的fund_charts
        (PROJECT / "data" / "fund_charts.json").write_text(
            json.dumps(fund_charts, ensure_ascii=False), encoding="utf-8")
        print(f"  fund_charts.json 已更新 ({len(fund_charts)} 只)")
```

替换为：

```python
    # 自动拉取新基金的历史净值（使用 JD API，无需 Cookie）
    if new_fund_codes:
        print(f"  发现 {len(new_fund_codes)} 只新基金，自动拉取历史净值...")
        from scripts.bulk_fetch_charts import fetch_full_nav
        from tools.chart_loader import update_chart
        for code in new_fund_codes:
            try:
                pts = fetch_full_nav(code)
                if pts:
                    update_chart(code, pts)
                    fund_charts[code] = pts
                    print(f"    {code}: 拉取 {len(pts)} 天历史")
                else:
                    print(f"    {code}: 无数据返回")
            except Exception as e:
                print(f"    {code}: 拉取失败 {e}")
            time.sleep(0.3)
        print(f"  fund_charts 已更新 ({len(fund_charts)} 只)")
```

- [ ] **步骤 2：验证 daily_live.py import 正常**

运行：
```bash
python -c "import sys; sys.path.insert(0, '.'); import scripts.daily_live; print('import OK')"
```
预期：无报错

- [ ] **步骤 3：Commit**

```bash
git add scripts/daily_live.py
git commit -m "daily_live 新基金获取改用 JD API 替换失效的 eastmoney_api"
```

---

## 任务 11：创建 GitHub Actions 全策略回测工作流

**文件：**
- 创建：`.github/workflows/backtest-full-revalidation.yml`

- [ ] **步骤 1：编写 GitHub Actions 工作流**

创建 `.github/workflows/backtest-full-revalidation.yml`：

```yaml
name: Full Strategy Revalidation (Data Quality Fix)

on:
  workflow_dispatch:
    inputs:
      fund_type_filter:
        description: 'Fund type filter (active/all/none)'
        required: false
        default: 'all'

jobs:
  # ── 先拉取数据 ──
  prepare-data:
    runs-on: ubuntu-latest
    timeout-minutes: 120
    outputs:
      fund_count: ${{ steps.count.outputs.count }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - name: Install dependencies
        run: pip install lightgbm scikit-learn numpy pandas
      - name: Fetch all fund charts
        run: |
          python scripts/bulk_fetch_charts.py --max 100
      - name: Run preflight check
        run: |
          python scripts/preflight_check.py
      - name: Count funds
        id: count
        run: |
          COUNT=$(python -c "import json; from pathlib import Path; idx=json.loads(Path('data/fund_charts_index.json').read_text('utf-8')); print(len(idx))")
          echo "count=$COUNT" >> $GITHUB_OUTPUT
      - name: Upload charts
        uses: actions/upload-artifact@v4
        with:
          name: fund-charts
          path: data/fund_charts/

  # ── 全策略回测 (matrix) ──
  backtest:
    needs: prepare-data
    runs-on: ubuntu-latest
    timeout-minutes: 30
    strategy:
      fail-fast: false
      max-parallel: 20
      matrix:
        test_name: [
          # 基线
          baseline,
          # Round 1-4 策略
          A1_macd_div, A2_bollinger, A3_yearly_ma, A4_rsi70, A5_all_combined,
          B1_risk60, B2_risk50, B3_risk40,
          OC_time_stop120, OC_rsi_sell80, OC_no_new_high20, OC_ma_cross, OC_dd_breaker12,
          D1_step_tp, D2_atr_stop, D3_macd_buy, D4_dyn_kelly,
          E1_A5_B1, F1_rsi65, F2_rsi75, F3_tp40, F4_tp60, F5_trail5, F6_trail12, F7_sector30,
          G1_atr_risk, G2_step_atr, H1_all_in,
          I1_ma20_buy, I2_rsi_oversold, I3_breakout60,
          J1_stop15, J2_stop50, J3_score4, J4_consensus1, J5_consensus3,
          J6_maxpos50, J7_cash3, J8_nostop, J9_hold60, J10_hold15,
          K1_value_trend, K2_event_v2, K3_all_buy_filters,
          S1_mom_adj, S2_loss_hold30, S2b_loss_hold15, S3_tp_trail_dyn,
          S4_mom_decay5, S4b_mom_decay10, S5_mom_adj_trail, S6_trail_atr,
          S7_mom_adj_decay, S8_profit_all, S9_profit_quarter,
          S10_no_mom_crash, S11_mom_crash_bull,
          S12_trail_act15, S13_trail_act30, S14_trail_act10_dd5, S15_combo,
          # Matrix 8 (AA-AE)
          AA1_hold30, AA2_hold90, AA3_hold120, AA4_slip05, AA5_slip10,
          AB1_sellcons2, AB2_sellcons3, AB3_topn5, AB4_topn10,
          AB5_consprio, AB6_costpen, AB7_limitboost,
          AC1_inject1k, AC2_inject5k, AC3_nodynsl, AC4_noregime, AC5_qdii50,
          AD1_nopenalty, AD2_pen03, AD3_pen10,
          AE1_bear_dynpos, AE2_dynrank_netsig_w, AE3_sellcons_dynrank, AE4_topn_consprio,
          # Matrix 9 (BA-BE)
          BA1_w_cons1, BA2_w_cons3, BA3_w_cons4,
          BA4_w_thr15, BA5_w_thr20, BA6_w_thr25, BA7_w_thr30, BA8_w_thr35,
          BA9_w_adaptive, BA10_w_cons2_topn10, BA11_w_cons2_consprio, BA12_w_cons2_maxhold10,
          BB1_net_ratio15, BB2_net_ratio2, BB3_net_ratio3,
          BB4_net_diff2, BB5_net_diff3, BB6_net_diff4,
          BB7_net_cons1, BB8_net_cons3, BB9_net_adaptive,
          BB10_net_topn10, BB11_net_consprio, BB12_net_maxhold10,
          BC1_w_net, BC3_w_net_cons3, BC4_w_net_thr20, BC5_w_net_thr25,
          BC6_w_net_diff2, BC7_w_net_ratio2, BC8_w_net_adaptive,
          BC9_w_net_topn10, BC10_w_net_consprio, BC11_w_net_maxhold10, BC12_w_net_sellcons2,
          BD1_w_net_score4, BD2_w_net_costpen, BD3_w_net_limitboost,
          BD4_w_net_qdii50, BD5_w_net_corr04, BD6_w_net_sector30,
          BE1_w_net_topn_consprio, BE2_w_net_thr25_diff2,
          BE3_w_net_adaptive_consprio, BE4_w_net_maxhold10_consprio,
          BE5_w_net_thr20_adaptive, BE6_w_net_thr30_diff3,
          # Y/Z 系列
          Y1_dynrank, Y2_dynrank_w60, Y3_dynrank_w180, Y4_dynrank_hl30,
          Y5_weighted, Y6_net_signal, Y7_dynrank_weighted, Y8_dynrank_netsig,
          Z1_bear_nobuy, Z2_dyn_maxpos, Z3_dyn_maxpos_cash, Z4_no_timing, Z5_no_overbought,
          # KDJ/动量 (Matrix 10-11)
          FA1_kdj_block80, FA2_kdj_block70, FA6_kdj_golden,
          FC1_maccel_block, FC6_maccel_sell,
          GA1_mom63_top10, GA7_mom126_top20
        ]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - name: Install dependencies
        run: pip install lightgbm scikit-learn numpy pandas

      - name: Download charts
        uses: actions/download-artifact@v4
        with:
          name: fund-charts
          path: data/fund_charts/

      - name: Run backtest
        run: python backtest/run_single_test.py ${{ matrix.test_name }}
        env:
          FUND_TYPE_FILTER: ${{ github.event.inputs.fund_type_filter }}

      - name: Upload result
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: result-${{ matrix.test_name }}
          path: backtest/results/${{ matrix.test_name }}.json

  # ── 汇总结果 ──
  collect-results:
    needs: backtest
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/download-artifact@v4
        with:
          path: backtest/results
          merge-multiple: true
      - name: Generate summary
        run: |
          python backtest/collect_results.py
      - name: Upload summary
        uses: actions/upload-artifact@v4
        with:
          name: backtest-full-revalidation-summary
          path: |
            backtest/reports/unified_backtest_summary.json
```

- [ ] **步骤 2：验证 YAML 语法**

运行：
```bash
python -c "import yaml; yaml.safe_load(open('.github/workflows/backtest-full-revalidation.yml', encoding='utf-8')); print('YAML OK')"
```
预期：`YAML OK`（如果没装 pyyaml，跳过此步）

- [ ] **步骤 3：Commit**

```bash
git add .github/workflows/backtest-full-revalidation.yml
git commit -m "添加全策略回测重验证 GitHub Actions 工作流"
```

---

## 任务 12：创建每日净值增量更新工作流

**文件：**
- 创建：`.github/workflows/daily-chart-update.yml`

- [ ] **步骤 1：编写工作流**

创建 `.github/workflows/daily-chart-update.yml`：

```yaml
name: Daily Fund Chart Update

on:
  schedule:
    # 每个交易日北京时间 15:00 (UTC 07:00) 运行
    - cron: '0 7 * * 1-5'
  workflow_dispatch:

jobs:
  update-charts:
    runs-on: ubuntu-latest
    timeout-minutes: 30
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Restore fund charts cache
        uses: actions/cache@v4
        with:
          path: data/fund_charts/
          key: fund-charts-${{ github.run_id }}
          restore-keys: |
            fund-charts-

      - name: Update all fund charts (incremental)
        run: |
          python scripts/update_fund_charts.py --both
        continue-on-error: true

      - name: Check for new funds from trading records
        run: |
          python tools/fund_data_manager.py --expand
          python scripts/bulk_fetch_charts.py
        continue-on-error: true

      - name: Save updated charts
        uses: actions/cache@v4
        with:
          path: data/fund_charts/
          key: fund-charts-${{ github.run_id }}

      - name: Upload index
        uses: actions/upload-artifact@v4
        with:
          name: fund-charts-index
          path: data/fund_charts_index.json
```

- [ ] **步骤 2：Commit**

```bash
git add .github/workflows/daily-chart-update.yml
git commit -m "添加每日净值增量更新 GitHub Actions 工作流"
```

---

## 任务 13：运行全策略回测

**文件：**
- 无新建文件

- [ ] **步骤 1：推送代码到 GitHub**

```bash
git push origin master
```

- [ ] **步骤 2：手动触发 GitHub Actions**

在 GitHub 仓库页面手动触发 `Full Strategy Revalidation (Data Quality Fix)` 工作流。

或者用命令行：
```bash
gh workflow run backtest-full-revalidation.yml -f fund_type_filter=all
```

- [ ] **步骤 3：等待回测完成**

预计耗时：约 1-2 小时（取决于 GitHub Actions 并行度）
可在 GitHub Actions 页面监控进度。

- [ ] **步骤 4：下载回测结果**

```bash
gh run download <run-id> --dir backtest/results_m10/
```

---

## 任务 14：生成对比分析报告

**文件：**
- 创建：`backtest/analyze_revalidation.py`

- [ ] **步骤 1：编写分析脚本**

创建 `backtest/analyze_revalidation.py`：

```python
"""分析全策略回测重验证结果，生成对比排行榜。"""
import json
import sys
import glob
from pathlib import Path
from datetime import datetime

PROJECT = Path(__file__).resolve().parent.parent

# 旧结果（数据修复前）
OLD_SUMMARY = PROJECT / "backtest" / "reports" / "unified_backtest_summary.json"
# 新结果目录
NEW_RESULTS_DIR = PROJECT / "backtest" / "results"


def main():
    # 加载旧结果
    old = {}
    if OLD_SUMMARY.exists():
        old_data = json.loads(OLD_SUMMARY.read_text("utf-8"))
        old = {r["name"]: r for r in old_data.get("results", [])}

    # 加载新结果
    new = {}
    for f in sorted(glob.glob(str(NEW_RESULTS_DIR / "*.json"))):
        try:
            r = json.loads(Path(f).read_text("utf-8"))
            if "total_return" in r:
                new[r["name"]] = r
        except Exception:
            continue

    # 对比表
    print(f"\n{'='*100}")
    print(f"全策略回测重验证结果 ({datetime.now().strftime('%Y-%m-%d %H:%M')})")
    print(f"{'='*100}")
    print(f"{'策略':<30} {'旧收益%':>8} {'新收益%':>8} {'变化':>8} {'新回撤%':>8} {'新夏普':>6} {'新交易':>6}")
    print(f"{'-'*100}")

    all_names = sorted(set(old.keys()) | set(new.keys()))
    rows = []
    for name in all_names:
        o = old.get(name, {})
        n = new.get(name, {})
        old_ret = o.get("total_return", None)
        new_ret = n.get("total_return", None)
        diff = (new_ret - old_ret) if (old_ret is not None and new_ret is not None) else None
        diff_str = f"{diff:+.2f}pp" if diff is not None else "N/A"
        old_str = f"{old_ret:.2f}" if old_ret is not None else "N/A"
        new_str = f"{new_ret:.2f}" if new_ret is not None else "N/A"
        new_dd = n.get("max_drawdown", 0)
        new_sharpe = n.get("sharpe", 0)
        new_trades = n.get("trade_count", 0)
        print(f"{name:<30} {old_str:>8} {new_str:>8} {diff_str:>8} {new_dd:>7.2f}% {new_sharpe:>5.2f} {new_trades:>6}")
        if new_ret is not None:
            rows.append({
                "name": name,
                "old_return": old_ret,
                "new_return": new_ret,
                "diff": diff,
                "new_dd": new_dd,
                "new_sharpe": new_sharpe,
                "new_trades": new_trades,
            })

    # 排行榜
    rows.sort(key=lambda x: x["new_return"], reverse=True)
    print(f"\n{'='*60}")
    print(f"TOP 10 (数据修复后)")
    print(f"{'='*60}")
    for i, r in enumerate(rows[:10]):
        print(f"  {i+1}. {r['name']}: {r['new_return']:+.2f}% (旧: {r['old_return']})")

    # Y5 对比
    y5_old = old.get("Y5_weighted", {}).get("total_return", 58.94)
    y5_new = new.get("Y5_weighted", {}).get("total_return", None)
    print(f"\n{'='*60}")
    print(f"Y5 冠军策略对比")
    print(f"{'='*60}")
    print(f"  旧 (数据缺陷): {y5_old:.2f}%")
    print(f"  新 (数据修复): {y5_new:.2f}%" if y5_new else "  新: 未找到结果")
    if y5_new:
        change = y5_new - y5_old
        print(f"  变化: {change:+.2f}pp")

    # 保存报告
    report = {
        "timestamp": datetime.now().isoformat(),
        "total_strategies": len(rows),
        "top10": rows[:10],
        "y5_comparison": {"old": y5_old, "new": y5_new},
        "all_results": rows,
    }
    report_path = PROJECT / "backtest" / "reports" / "revalidation_report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n报告已保存: {report_path}")


if __name__ == "__main__":
    main()
```

- [ ] **步骤 2：运行分析脚本**

运行：`python backtest/analyze_revalidation.py`
预期：输出对比排行榜和 Y5 策略新旧对比

- [ ] **步骤 3：Commit**

```bash
git add backtest/analyze_revalidation.py backtest/reports/revalidation_report.json
git commit -m "添加回测重验证对比分析报告"
```

---

## 任务 15：清理临时文件和旧数据

**文件：**
- 删除：`data/fund_charts.json.bak`、`backtest/data/fund_charts.json.bak`
- 删除：`scripts/migrate_charts.py`（一次性脚本）

- [ ] **步骤 1：确认迁移无误后删除备份文件**

```bash
# 确认 per-fund 目录数据完整
python -c "from tools.chart_loader import load_all_charts; c=load_all_charts(); print(f'Funds: {len(c)}')"

# 删除旧备份
rm data/fund_charts.json.bak
rm backtest/data/fund_charts.json.bak
```

- [ ] **步骤 2：删除一次性迁移脚本**

```bash
rm scripts/migrate_charts.py
```

- [ ] **步骤 3：Commit**

```bash
git add -A
git commit -m "清理迁移临时文件和旧数据备份"
```

---

## 自检

### 1. 规格覆盖度

| 规格章节 | 对应任务 | 状态 |
|----------|----------|------|
| 2.1 统一数据存储架构 | 任务 1-2 | ✅ |
| 2.2 chart_loader 模块 | 任务 1 | ✅ |
| 2.3 批量历史数据拉取 | 任务 6-7 | ✅ |
| 2.4 daily_live.py 修复 | 任务 4, 10 | ✅ |
| 2.5 回测引擎适配 | 任务 3 | ✅ |
| 2.6 数据准确性预检 | 任务 8 | ✅ |
| 2.7 移除评分默认值 | 任务 9 | ✅ |
| 2.8 全策略回测 | 任务 11-14 | ✅ |
| update_fund_charts.py 适配 | 任务 5 | ✅ |
| 每日增量更新 CI | 任务 12 | ✅ |
| 清理 | 任务 15 | ✅ |

### 2. 占位符扫描

- 无 "待定"、"TODO" 或模糊描述
- 每个步骤都有完整代码或精确命令
- 测试代码完整可运行

### 3. 类型一致性

- `load_all_charts()` 在任务 1 定义，任务 3/4/5/10 中使用，签名一致
- `update_chart(code, points, charts_dir)` 在任务 1 定义，任务 2/5/6/8/10 中使用，签名一致
- `fetch_full_nav(code)` 在任务 6 定义，任务 8/10 中使用，签名一致
- `DimensionScore(score=-1, weight=0)` 在任务 9 定义，与 `fund_scorer.py` 中的 dataclass 兼容

### 4. 依赖顺序

```
任务 1 (chart_loader) → 任务 2 (迁移) → 任务 3 (回测引擎) → 任务 4 (daily_live加载)
                                                              → 任务 5 (update_fund_charts)
任务 6 (批量拉取脚本) → 任务 7 (运行拉取) → 任务 8 (预检)
任务 9 (移除默认值) — 独立，但需在任务 3 之后
任务 10 (daily_live JD API) — 需在任务 6 之后
任务 11-14 (GitHub Actions 回测) — 需在任务 1-10 之后
任务 15 (清理) — 最后
```
