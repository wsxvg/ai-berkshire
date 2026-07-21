"""验证评分函数在数据不足时返回 weight=0 而非默认值 2.5。"""
import pytest
import sys
from pathlib import Path

_PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT))
sys.path.insert(0, str(_PROJECT / "backtest"))

from backtest.engine.backtest import score_momentum_backtest, score_quality_backtest


class TestScoringNoDefaults:
    """评分函数不应返回默认 2.5 分，数据不足时返回 score=-1, weight=0"""

    def test_momentum_insufficient_data_returns_zero_weight(self):
        """数据不足20天时，momentum 应返回 weight=0"""
        short_chart = [{"xAxis": f"2026-01-{i:02d}", "yAxis": 0.1 * i} for i in range(1, 11)]
        result = score_momentum_backtest(short_chart, "2026-07-21")
        assert result.weight == 0, f"Expected weight=0 for insufficient data, got {result.weight}"
        assert result.score == -1, f"Expected score=-1 for insufficient data, got {result.score}"

    def test_quality_insufficient_data_returns_zero_weight(self):
        """数据不足20天时，quality 应返回 weight=0"""
        short_chart = [{"xAxis": f"2026-01-{i:02d}", "yAxis": 0.1 * i} for i in range(1, 11)]
        result = score_quality_backtest(short_chart, "2026-07-21")
        assert result.weight == 0, f"Expected weight=0 for insufficient data, got {result.weight}"
        assert result.score == -1, f"Expected score=-1 for insufficient data, got {result.score}"

    def test_momentum_empty_chart_returns_zero_weight(self):
        """空数据时返回 weight=0"""
        result = score_momentum_backtest([], "2026-07-21")
        assert result.weight == 0
        assert result.score == -1

    def test_quality_empty_chart_returns_zero_weight(self):
        """空数据时返回 weight=0"""
        result = score_quality_backtest([], "2026-07-21")
        assert result.weight == 0
        assert result.score == -1

    def test_momentum_sufficient_data_returns_nonzero_weight(self):
        """数据充足时返回正常权重"""
        chart = [{"xAxis": f"2026-{m:02d}-{d:02d}", "yAxis": i * 0.1} for i, (m, d) in enumerate(
            [(1, j) for j in range(1, 32)] + [(2, j) for j in range(1, 29)]
        )]
        result = score_momentum_backtest(chart, "2026-07-21")
        assert result.weight > 0, f"Expected non-zero weight for sufficient data, got {result.weight}"

    def test_quality_sufficient_data_returns_nonzero_weight(self):
        """数据充足时返回正常权重"""
        chart = [{"xAxis": f"2026-{m:02d}-{d:02d}", "yAxis": i * 0.1} for i, (m, d) in enumerate(
            [(1, j) for j in range(1, 32)] + [(2, j) for j in range(1, 29)]
        )]
        result = score_quality_backtest(chart, "2026-07-21")
        assert result.weight > 0, f"Expected non-zero weight for sufficient data, got {result.weight}"
