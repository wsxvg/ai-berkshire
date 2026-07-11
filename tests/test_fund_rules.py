"""Tests for fund_rules.py — 规则引擎"""
from __future__ import annotations
import pytest
from pathlib import Path
import sys

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from tools.fund_rules import weighted_clear, buy_shield, take_profit_level, swap_cost, analyze_all


class TestWeightedClear:
    """测试加权清仓计算"""

    def test_weighted_clear_no_data(self):
        """无数据时返回 pass"""
        result = weighted_clear("000000", holdings_diff={})
        assert result["verdict"] == "pass"
        assert result["weighted_clear"] == 0

    def test_weighted_clear_high_signal(self):
        """加权清仓 >= 3 时返回 red_clear"""
        holdings_diff = {
            "funds": {
                "006105": {
                    "clear_total": 3.5,
                    "reduce_30pct_total": 0,
                    "weighted_clear": 3.5,
                    "clear_details": [],
                    "conflict": {},
                }
            }
        }
        result = weighted_clear("006105", holdings_diff=holdings_diff)
        assert result["verdict"] == "red_clear"
        assert result["weighted_clear"] == 3.5

    def test_weighted_clear_medium_signal(self):
        """加权清仓 2-3 时返回 yellow_watch"""
        holdings_diff = {
            "funds": {
                "006105": {
                    "clear_total": 2.5,
                    "reduce_30pct_total": 0,
                    "weighted_clear": 2.5,
                    "clear_details": [],
                    "conflict": {},
                }
            }
        }
        result = weighted_clear("006105", holdings_diff=holdings_diff)
        assert result["verdict"] == "yellow_watch"

    def test_weighted_clear_low_signal(self):
        """加权清仓 < 2 时返回 pass"""
        holdings_diff = {
            "funds": {
                "006105": {
                    "clear_total": 1.0,
                    "reduce_30pct_total": 0,
                    "weighted_clear": 1.0,
                    "clear_details": [],
                    "conflict": {},
                }
            }
        }
        result = weighted_clear("006105", holdings_diff=holdings_diff)
        assert result["verdict"] == "pass"


class TestBuyShield:
    """测试买入护盾检测"""

    def test_buy_shield_not_holding(self):
        """未持仓时返回 shield_active=False"""
        result = buy_shield("006105", my_holdings=[], trading_cache={})
        assert result["shield_active"] is False
        assert result["reason"] == "未持仓"

    def test_buy_shield_no_trading_record(self):
        """有持仓但无交易记录"""
        my_holdings = [{"code": "006105"}]
        result = buy_shield("006105", my_holdings=my_holdings, trading_cache={"funds": {}})
        assert result["shield_active"] is False
        assert result["reason"] == "无交易记录"

    def test_buy_shield_strong(self):
        """2人以上买入 → 强护盾"""
        my_holdings = [{"code": "006105"}]
        trading_cache = {
            "funds": {
                "宏利印度": {"fund_code": "006105", "buy_count": 3, "sell_count": 0}
            }
        }
        result = buy_shield("006105", my_holdings=my_holdings, trading_cache=trading_cache)
        assert result["shield_active"] is True
        assert result["strength"] == "strong"
        assert result["buy_count"] == 3

    def test_buy_shield_weak(self):
        """1人买入 → 弱护盾"""
        my_holdings = [{"code": "006105"}]
        trading_cache = {
            "funds": {
                "宏利印度": {"fund_code": "006105", "buy_count": 1, "sell_count": 0}
            }
        }
        result = buy_shield("006105", my_holdings=my_holdings, trading_cache=trading_cache)
        assert result["shield_active"] is True
        assert result["strength"] == "weak"

    def test_buy_shield_no_buy(self):
        """无人买入 → 无护盾"""
        my_holdings = [{"code": "006105"}]
        trading_cache = {
            "funds": {
                "宏利印度": {"fund_code": "006105", "buy_count": 0, "sell_count": 1}
            }
        }
        result = buy_shield("006105", my_holdings=my_holdings, trading_cache=trading_cache)
        assert result["shield_active"] is False
        assert result["strength"] == "none"


class TestTakeProfitLevel:
    """测试止盈阈值表"""

    def test_active_fund(self):
        """主动型基金止盈50%，止损-20%"""
        result = take_profit_level("active")
        assert result["target_profit_pct"] == 50
        assert result["stop_loss_pct"] == -20

    def test_passive_index(self):
        """被动指数基金止盈20%，无止损"""
        result = take_profit_level("passive_index")
        assert result["target_profit_pct"] == 20
        assert result["stop_loss_pct"] is None

    def test_qdii_active(self):
        """QDII主动型止盈50%，止损-25%"""
        result = take_profit_level("qdii_active")
        assert result["target_profit_pct"] == 50
        assert result["stop_loss_pct"] == -25

    def test_unknown_type_defaults_to_active(self):
        """未知类型默认按 active 处理"""
        result = take_profit_level("unknown_type")
        assert result["target_profit_pct"] == 50
        assert result["stop_loss_pct"] == -20


class TestSwapCost:
    """测试调仓成本计算"""

    def test_swap_cost_no_data(self):
        """无费率数据时返回 should_swap=False"""
        result = swap_cost("000000")
        assert result["should_swap"] is False
        assert result["reason"] == "无费率数据"


class TestAnalyzeAll:
    """测试统一分析入口"""

    def test_analyze_all_no_code(self):
        """无基金代码时返回基本结构"""
        result = analyze_all()
        assert "weighted_clear" in result
        assert "buy_shield" in result
        assert "take_profit" in result
        assert "suggestions" in result

    def test_analyze_all_with_code(self):
        """有基金代码时返回完整分析"""
        result = analyze_all("006105")
        assert "weighted_clear" in result
        assert "buy_shield" in result
        assert "take_profit" in result
