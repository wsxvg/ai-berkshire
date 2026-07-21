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
