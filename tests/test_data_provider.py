"""Tests for data_provider models and factory"""
from __future__ import annotations
import pytest
from tools.data_provider import NavPoint, Holdings, StockHolding, FeeStructure, ManagerInfo, FundProfile
from tools.data_provider.factory import FundDataSourceFactory
from tools.data_provider.base import IFundDataProvider


class TestModels:
    """Test dataclass creation and serialization"""

    def test_navpoint_creation(self):
        n = NavPoint(date="2026-01-15", nav=1.234, accumulated_nav=1.5, daily_return=0.5)
        assert n.date == "2026-01-15"
        assert n.nav == 1.234
        d = n.to_dict()
        assert d["date"] == "2026-01-15"

    def test_stock_holding_creation(self):
        s = StockHolding(code="600519", name="茅台", ratio=8.5, pe=30.0, pb=10.0)
        assert s.code == "600519"
        assert s.ratio == 8.5

    def test_holdings_creation(self):
        stocks = [
            StockHolding(code="600519", name="茅台", ratio=8.5),
            StockHolding(code="000858", name="五粮液", ratio=6.2),
        ]
        h = Holdings(quarter="2025Q4", publish_date="2026-01-21", top_stocks=stocks)
        assert h.quarter == "2025Q4"
        assert len(h.top_stocks) == 2

    def test_fee_structure(self):
        f = FeeStructure(manage_fee=1.5, custody_fee=0.25, service_fee=0.0)
        assert f.total_annual_fee == 1.75
        assert pytest.approx(f.total_annual_fee, 0.01) == 1.75

    def test_fee_with_redeem(self):
        f = FeeStructure(
            manage_fee=1.5, custody_fee=0.25,
            redeem_fee_rates=[
                {"min_days": 0, "max_days": 7, "rate": 1.5},
                {"min_days": 7, "max_days": 30, "rate": 0.75},
            ],
        )
        assert f.total_annual_fee == 1.75
        assert len(f.redeem_fee_rates) == 2

    def test_manager_info(self):
        m = ManagerInfo(name="张三", start_date="2020-01-01", tenure_return=85.5)
        assert m.name == "张三"
        assert m.tenure_return == 85.5

    def test_fund_profile(self):
        m = ManagerInfo(name="张三", start_date="2020-01-01")
        p = FundProfile(code="006105", name="宏利印度", fund_type="QDII",
                        establish_date="2019-01-01", manager=m)
        assert p.code == "006105"
        d = p.to_dict()
        assert d["fund_type"] == "QDII"

    def test_fund_profile_no_manager(self):
        p = FundProfile(code="006105", name="某基金", fund_type="股票型",
                        establish_date="2019-01-01")
        assert p.manager is None

    def test_models_all_have_to_dict(self):
        """所有模型必须可序列化"""
        models = [
            NavPoint(date="2026-01-15", nav=1.0, accumulated_nav=1.0, daily_return=0.0),
            Holdings(quarter="2025Q4", publish_date="2026-01-21"),
            FeeStructure(manage_fee=1.0, custody_fee=0.25),
            ManagerInfo(name="张三", start_date="2020-01-01"),
            FundProfile(code="000001", name="某基金", fund_type="混合型", establish_date="2020-01-01"),
        ]
        for m in models:
            d = m.to_dict()
            assert isinstance(d, dict), f"{type(m).__name__}.to_dict() failed"


class TestFactory:
    """Test FundDataSourceFactory"""

    def test_auto_register(self):
        """首次 get() 自动注册默认数据源"""
        _ = FundDataSourceFactory.get()  # 触发自动注册
        sources = FundDataSourceFactory.get_available_sources()
        assert len(sources) > 0
        assert "jd" in sources

    def test_get_default_provider(self):
        provider = FundDataSourceFactory.get()
        assert provider is not None
        assert isinstance(provider, IFundDataProvider)

    def test_get_provider_by_name(self):
        provider = FundDataSourceFactory.get("jd")
        assert provider is not None
        assert provider.name == "jd"

    def test_get_fallback(self):
        provider = FundDataSourceFactory.get(fallback=True)
        assert provider is not None

    def test_get_unknown_provider(self):
        provider = FundDataSourceFactory.get("nonexistent")
        assert provider is None

    def test_register_new_provider(self):
        """测试动态注册新provider"""
        count_before = len(FundDataSourceFactory.get_available_sources())

        class MockProvider(IFundDataProvider):
            @property
            def name(self): return "mock"
            def get_nav(self, *a, **kw): return []
            def get_holdings(self, *a, **kw): return Holdings(quarter="", publish_date="")
            def get_fee(self, *a, **kw): return FeeStructure(manage_fee=0, custody_fee=0)
            def get_manager(self, *a, **kw): return ManagerInfo(name="", start_date="")
            def get_profile(self, *a, **kw): return FundProfile(code="", name="", fund_type="", establish_date="")
            def get_nav_history(self, *a, **kw): return []

        FundDataSourceFactory.register("mock", MockProvider)
        count_after = len(FundDataSourceFactory.get_available_sources())
        assert count_after == count_before + 1

        provider = FundDataSourceFactory.get("mock")
        assert provider is not None
        assert provider.name == "mock"

    def test_unique_instances(self):
        """同一数据源返回单例"""
        p1 = FundDataSourceFactory.get("jd")
        p2 = FundDataSourceFactory.get("jd")
        assert p1 is p2