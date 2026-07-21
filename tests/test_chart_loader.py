"""Tests for chart_loader — unified fund chart data access."""
from __future__ import annotations
import pytest
import json
import tempfile
import shutil
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
