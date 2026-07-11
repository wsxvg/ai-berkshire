"""Tests for fund_scorer.py — 评分引擎"""
from __future__ import annotations
import pytest
from pathlib import Path
import sys

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from tools.fund_scorer import (
    DimensionScore,
    FundScore,
    calc_sharpe,
    nav_to_daily_returns,
    chart_to_daily_returns,
    sharpe_to_score,
    calc_max_drawdown,
    chart_to_nav_index,
    _float,
    scale_penalty,
    score_quality,
    score_cost,
    score_manager,
    score_momentum,
    score_smart_money,
    _valuation_modifier,
    _read_json,
    _stock_to_unique_code,
    score_penetration_valuation,
)


class TestDimensionScore:
    """测试维度评分"""

    def test_creation(self):
        """创建维度评分"""
        ds = DimensionScore(score=4.0, weight=0.25, freshness_days=30)
        assert ds.score == 4.0
        assert ds.weight == 0.25
        assert ds.stale is False

    def test_stale_detection(self):
        """过期检测"""
        ds = DimensionScore(score=4.0, weight=0.25, freshness_days=100)
        assert ds.stale is True

    def test_effective_score_fresh(self):
        """新鲜数据的有效分数"""
        ds = DimensionScore(score=4.0, weight=0.25, freshness_days=30)
        assert ds.effective_score() == 4.0

    def test_effective_score_stale(self):
        """过期数据的有效分数（90%）"""
        ds = DimensionScore(score=4.0, weight=0.25, freshness_days=100)
        assert ds.effective_score() == 3.6


class TestFundScore:
    """测试基金评分"""

    def test_creation(self):
        """创建基金评分"""
        fs = FundScore(
            fund_code="006105",
            fund_type="active",
            quality=DimensionScore(4.0, 0.25, 30),
            cost=DimensionScore(3.5, 0.20, 30),
            manager=DimensionScore(4.0, 0.20, 30),
            momentum=DimensionScore(3.5, 0.15, 30),
            smart_money=DimensionScore(4.0, 0.20, 30),
        )
        assert fs.fund_code == "006105"
        assert fs.verdict == "pass"

    def test_compute_buy_verdict(self):
        """计算后 verdict=buy"""
        fs = FundScore(
            fund_code="006105",
            fund_type="active",
            quality=DimensionScore(4.5, 0.25, 30),
            cost=DimensionScore(4.0, 0.20, 30),
            manager=DimensionScore(4.5, 0.20, 30),
            momentum=DimensionScore(4.0, 0.15, 30),
            smart_money=DimensionScore(4.5, 0.20, 30),
        )
        fs.compute()
        assert fs.verdict == "buy"
        assert fs.total >= 4.0

    def test_compute_watch_verdict(self):
        """计算后 verdict=watch"""
        fs = FundScore(
            fund_code="006105",
            fund_type="active",
            quality=DimensionScore(3.5, 0.25, 30),
            cost=DimensionScore(3.0, 0.20, 30),
            manager=DimensionScore(3.5, 0.20, 30),
            momentum=DimensionScore(3.0, 0.15, 30),
            smart_money=DimensionScore(3.5, 0.20, 30),
        )
        fs.compute()
        assert fs.verdict == "watch"
        assert 3.3 <= fs.total < 4.0

    def test_compute_pass_verdict(self):
        """计算后 verdict=pass"""
        fs = FundScore(
            fund_code="006105",
            fund_type="active",
            quality=DimensionScore(2.5, 0.25, 30),
            cost=DimensionScore(2.0, 0.20, 30),
            manager=DimensionScore(2.5, 0.20, 30),
            momentum=DimensionScore(2.0, 0.15, 30),
            smart_money=DimensionScore(2.5, 0.20, 30),
        )
        fs.compute()
        assert fs.verdict == "pass"
        assert fs.total < 3.3

    def test_compare_returns_deltas(self):
        """比较两个评分返回差值"""
        fs1 = FundScore(
            fund_code="006105", fund_type="active",
            quality=DimensionScore(4.0, 0.25, 30),
            cost=DimensionScore(3.5, 0.20, 30),
            manager=DimensionScore(4.0, 0.20, 30),
            momentum=DimensionScore(3.5, 0.15, 30),
            smart_money=DimensionScore(4.0, 0.20, 30),
        )
        fs1.total = 3.8
        fs2 = FundScore(
            fund_code="006105", fund_type="active",
            quality=DimensionScore(3.5, 0.25, 30),
            cost=DimensionScore(3.5, 0.20, 30),
            manager=DimensionScore(4.0, 0.20, 30),
            momentum=DimensionScore(3.5, 0.15, 30),
            smart_money=DimensionScore(4.0, 0.20, 30),
        )
        fs2.total = 3.6
        result = fs1.compare(fs2)
        assert "total_delta" in result
        assert "main_driver" in result
        assert result["total_delta"] == pytest.approx(0.2, 0.01)

    def test_compare_cooldown(self):
        """微小变化触发 hold 覆盖"""
        fs1 = FundScore(
            fund_code="006105", fund_type="active",
            quality=DimensionScore(4.0, 0.25, 30),
            cost=DimensionScore(3.5, 0.20, 30),
            manager=DimensionScore(4.0, 0.20, 30),
            momentum=DimensionScore(3.5, 0.15, 30),
            smart_money=DimensionScore(4.0, 0.20, 30),
        )
        fs1.total = 3.8
        fs2 = FundScore(
            fund_code="006105", fund_type="active",
            quality=DimensionScore(3.9, 0.25, 30),
            cost=DimensionScore(3.5, 0.20, 30),
            manager=DimensionScore(4.0, 0.20, 30),
            momentum=DimensionScore(3.5, 0.15, 30),
            smart_money=DimensionScore(4.0, 0.20, 30),
        )
        fs2.total = 3.75
        result = fs1.compare(fs2)
        assert result["override"] == "hold"

    def test_falsify_smart_money_zero(self):
        """聪明钱分为0时总分 cap 3.3"""
        fs = FundScore(
            fund_code="006105", fund_type="active",
            quality=DimensionScore(4.5, 0.25, 30),
            cost=DimensionScore(4.0, 0.20, 30),
            manager=DimensionScore(4.5, 0.20, 30),
            momentum=DimensionScore(4.0, 0.15, 30),
            smart_money=DimensionScore(0, 0.20, 30),
        )
        fs.compute()
        assert fs.total <= 3.3

    def test_falsify_new_fund(self):
        """成立不足1年 → pass"""
        fs = FundScore(
            fund_code="006105", fund_type="active",
            quality=DimensionScore(4.5, 0.25, 30),
            cost=DimensionScore(4.0, 0.20, 30),
            manager=DimensionScore(4.5, 0.20, 30),
            momentum=DimensionScore(4.0, 0.15, 30),
            smart_money=DimensionScore(4.5, 0.20, 30),
        )
        fs.compute(established_days=180)
        assert fs.verdict == "pass"
        assert fs.total <= 2.5


class TestCalcSharpe:
    """测试夏普比率计算"""

    def test_positive_returns(self):
        """正收益序列"""
        returns = [0.01, 0.02, 0.015, 0.005, 0.01] * 20
        sharpe = calc_sharpe(returns)
        assert sharpe > 0

    def test_negative_returns(self):
        """负收益序列"""
        returns = [-0.01, -0.02, -0.015, -0.005, -0.01] * 20
        sharpe = calc_sharpe(returns)
        assert sharpe < 0

    def test_zero_returns(self):
        """零收益序列"""
        returns = [0.0] * 50
        sharpe = calc_sharpe(returns)
        assert sharpe == 0.0

    def test_insufficient_data(self):
        """数据不足"""
        returns = [0.01, 0.02]
        sharpe = calc_sharpe(returns)
        assert sharpe == 0.0


class TestSharpeToScore:
    """测试夏普比率转评分"""

    def test_high_sharpe(self):
        """高夏普 → 高分"""
        score = sharpe_to_score(2.0)
        assert score >= 4.0

    def test_medium_sharpe(self):
        """中等夏普 → 中分"""
        score = sharpe_to_score(1.0)
        assert 3.0 <= score <= 4.0

    def test_low_sharpe(self):
        """低夏普 → 低分"""
        score = sharpe_to_score(0.0)
        assert score <= 3.0

    def test_negative_sharpe(self):
        """负夏普 → 低分"""
        score = sharpe_to_score(-1.0)
        assert score <= 2.0


class TestCalcMaxDrawdown:
    """测试最大回撤计算"""

    def test_no_drawdown(self):
        """无回撤（持续上涨）"""
        values = [100, 110, 120, 130, 140]
        mdd = calc_max_drawdown(values)
        assert mdd == 0.0

    def test_with_drawdown(self):
        """有回撤"""
        values = [100, 120, 110, 130, 100]
        mdd = calc_max_drawdown(values)
        assert mdd > 0

    def test_empty_values(self):
        """空列表"""
        mdd = calc_max_drawdown([])
        assert mdd == 0.0


class TestChartToNavIndex:
    """测试 chart_points 转 nav_index"""

    def test_conversion(self):
        """基本转换"""
        chart_points = [
            {"xAxis": "2026-01-01", "yAxis": 0},
            {"xAxis": "2026-01-02", "yAxis": 1},
            {"xAxis": "2026-01-03", "yAxis": 2},
        ]
        nav = chart_to_nav_index(chart_points)
        assert len(nav) == 3
        assert nav[0] == 100.0  # (100 + 0) / 100 * 100


class TestFloat:
    """测试浮点数转换"""

    def test_int_to_float(self):
        """整数转浮点"""
        assert _float(100) == 100.0

    def test_string_to_float(self):
        """字符串转浮点"""
        assert _float("3.14") == 3.14

    def test_none_to_zero(self):
        """None 转 0"""
        assert _float(None) == 0.0

    def test_percentage_string(self):
        """百分比字符串"""
        assert _float("8.5%") == 8.5


class TestScalePenalty:
    """测试规模惩罚"""

    def test_small_scale(self):
        """小规模基金（<=100亿）无惩罚"""
        penalty = scale_penalty("0.3亿元")
        assert penalty == 1.0  # <=100亿无惩罚

    def test_medium_scale(self):
        """中等规模基金（100-200亿）轻微惩罚"""
        penalty = scale_penalty("150亿元")
        assert penalty == 0.9

    def test_large_scale(self):
        """大规模基金（200-500亿）"""
        penalty = scale_penalty("300亿元")
        assert penalty == 0.8

    def test_very_large_scale(self):
        """超大规模基金（>500亿）"""
        penalty = scale_penalty("600亿元")
        assert penalty == 0.7

    def test_normal_scale(self):
        """正常规模基金"""
        penalty = scale_penalty("10亿元")
        assert penalty == 1.0

    def test_no_scale(self):
        """无规模信息"""
        penalty = scale_penalty(None)
        assert penalty == 1.0


class TestScoreCost:
    """测试成本评分"""

    def test_low_cost(self):
        """低成本基金"""
        rules = {"manage_fee": 0.5, "custody_fee": 0.1}
        ds = score_cost(rules)
        assert ds.score >= 4.0

    def test_high_cost(self):
        """高成本基金"""
        rules = {"manage_fee": 2.0, "custody_fee": 0.5}
        ds = score_cost(rules)
        assert ds.score <= 3.0


class TestScoreManager:
    """测试经理评分"""

    def test_experienced_manager(self):
        """经验丰富经理（需要正确的数据格式）"""
        mgr = {
            "managers": [{
                "employment_date": "5年7个月",
                "employ_performance": 85.5,
            }]
        }
        ds = score_manager(mgr)
        assert ds.score >= 3.0  # 5年经验 + 正收益

    def test_new_manager(self):
        """新经理"""
        mgr = {
            "managers": [{
                "employment_date": "0年6个月",
                "employ_performance": 10.0,
            }]
        }
        ds = score_manager(mgr)
        assert ds.score <= 3.0

    def test_no_manager_data(self):
        """无经理数据"""
        ds = score_manager({})
        assert ds.score == 2.5

    def test_managers_list_empty(self):
        """managers 列表为空"""
        ds = score_manager({"managers": []})
        assert ds.score == 2.5
