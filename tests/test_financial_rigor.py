"""Tests for financial_rigor.py — 金融严谨性工具"""
from __future__ import annotations
import pytest
from pathlib import Path
import sys

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from tools.financial_rigor import (
    verify_market_cap,
    verify_valuation,
    cross_validate,
    benford_check,
    exact,
    fmt_number,
)


class TestVerifyMarketCap:
    """测试市值验算"""

    def test_market_cap_verified(self):
        """市值验算通过"""
        result = verify_market_cap(
            price=510, shares=9.11e9, reported_cap=4.65e12, currency="HKD"
        )
        assert result is True

    def test_market_cap_deviation_large(self):
        """偏差过大返回 False"""
        result = verify_market_cap(
            price=510, shares=9.11e9, reported_cap=5.0e12, currency="HKD"
        )
        assert result is False

    def test_market_cap_deviation_medium(self):
        """偏差在1-5%之间返回 True（警告）"""
        result = verify_market_cap(
            price=510, shares=9.11e9, reported_cap=4.8e12, currency="HKD"
        )
        assert result is True


class TestVerifyValuation:
    """测试估值指标验算"""

    def test_valuation_with_eps(self):
        """有 EPS 时计算 PE"""
        result = verify_valuation(price=50, eps=5.0)
        assert result is not None

    def test_valuation_with_bvps(self):
        """有 BVPS 时计算 PB"""
        result = verify_valuation(price=50, bvps=25.0)
        assert result is not None

    def test_valuation_with_all_metrics(self):
        """所有指标都提供"""
        result = verify_valuation(
            price=50, eps=5.0, bvps=25.0, fcf_per_share=3.0, dividend=1.0
        )
        assert result is not None


class TestCrossValidate:
    """测试多源交叉验证"""

    def test_cross_validate_consistent(self):
        """数据一致时通过"""
        result = cross_validate(
            field_name="revenue",
            source_values={"年报": 7518, "Yahoo": 7500, "StockAnalysis": 7520},
            unit="亿"
        )
        assert result is not None
        assert "consensus" in result
        assert "all_consistent" in result

    def test_cross_validate_with_deviation(self):
        """数据有偏差时标记"""
        result = cross_validate(
            field_name="market_cap",
            source_values={"来源1": 1000, "来源2": 1100},
            unit="亿"
        )
        assert result is not None
        assert result["all_consistent"] is False


class TestBenford:
    """测试 Benford 定律检测"""

    def test_benford_normal(self):
        """正常数据分布（需要 >= 50 个样本）"""
        # 模拟符合 Benford 定律的数据（真实财务数据通常是这样）
        import random
        random.seed(42)
        values = [int(10 ** (1 + random.random() * 2)) for _ in range(100)]
        result = benford_check(values)
        assert result is not None

    def test_benford_suspicious(self):
        """可疑数据分布"""
        # 模拟不符合 Benford 定律的数据（均匀分布）
        values = [100, 200, 300, 400, 500, 600, 700, 800, 900] * 10
        result = benford_check(values)
        assert result is not None


class TestExact:
    """测试精确十进制转换"""

    def test_exact_from_int(self):
        """整数转 Decimal"""
        d = exact(100)
        assert str(d) == "100"

    def test_exact_from_float(self):
        """浮点数转 Decimal（避免精度问题）"""
        # 注意：exact() 将 float 转为 str 再转 Decimal
        # 0.1 + 0.2 在 Python 中是 0.30000000000000004
        d = exact(0.1 + 0.2)
        # 验证 Decimal 类型正确
        from decimal import Decimal
        assert isinstance(d, Decimal)
        # 验证精度保留
        assert float(d) == 0.1 + 0.2

    def test_exact_from_string_preserves_precision(self):
        """字符串传入避免浮点精度问题"""
        d = exact("0.3")
        assert str(d) == "0.3"

    def test_exact_from_string(self):
        """字符串转 Decimal"""
        d = exact("3.14159")
        assert str(d) == "3.14159"


class TestFmtNumber:
    """测试数字格式化"""

    def test_fmt_number_large(self):
        """大数字格式化"""
        result = fmt_number(1.5e12)
        assert "T" in result

    def test_fmt_number_billion(self):
        """十亿级格式化"""
        result = fmt_number(5.5e9)
        assert "B" in result

    def test_fmt_number_million(self):
        """百万级格式化"""
        result = fmt_number(2.5e6)
        assert "M" in result

    def test_fmt_number_with_unit(self):
        """带单位格式化"""
        result = fmt_number(1500, unit="亿")
        assert "亿" in result
