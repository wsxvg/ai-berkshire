"""Tests for Decision Engine"""
from __future__ import annotations
import json
from pathlib import Path
import pytest
from tools.decision_engine import DecisionEngine, DecisionResult

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


class TestDecisionEngine:
    """Test 5-step decision pipeline"""

    def test_engine_creation(self):
        engine = DecisionEngine()
        assert engine is not None

    def test_evaluate_returns_decision(self):
        engine = DecisionEngine()
        result = engine.evaluate("000000", cash=100000)
        assert isinstance(result, DecisionResult)
        assert result.action in ("buy", "hold", "reduce", "sell", "switch")
        assert result.fund_code == "000000"

    def test_evaluate_has_steps(self):
        engine = DecisionEngine()
        result = engine.evaluate("000000", cash=100000)
        assert len(result.steps) >= 2  # at least rules + scoring

    def test_evaluate_with_ai_suggestion(self):
        engine = DecisionEngine()
        result = engine.evaluate("000000", cash=100000, ai_suggestion="强烈建议买入")
        assert result.ai_suggestion == "强烈建议买入"

    def test_evaluate_portfolio_returns_list(self):
        engine = DecisionEngine()
        holdings = [
            {"code": "000001", "name": "基金A", "amount": 10000},
            {"code": "000002", "name": "基金B", "amount": 20000},
        ]
        results = engine.evaluate_portfolio(holdings, cash=100000)
        assert isinstance(results, list)
        assert len(results) == 2

    def test_decision_result_has_required_fields(self):
        r = DecisionResult(
            action="buy",
            fund_code="006105",
            amount=5000,
            priority="建议",
            reason="评分4.2",
        )
        assert r.action == "buy"
        assert r.fund_code == "006105"
        assert r.amount == 5000
        assert r.priority == "建议"

    def test_forced_sell_priority(self):
        """强制清仓的优先级为强制"""
        r = DecisionResult(action="sell", fund_code="000000",
                           priority="强制", reason="加权清仓信号")
        assert r.priority == "强制"

    def test_validate_suggestion_records_diverge(self):
        engine = DecisionEngine()
        from tools.fund_scorer import FundScore, DimensionScore

        mock_score = FundScore(
            fund_code="000000", fund_type="active",
            quality=DimensionScore(3.0, 0.25, 0),
            cost=DimensionScore(3.0, 0.20, 0),
            manager=DimensionScore(3.0, 0.20, 0),
            momentum=DimensionScore(3.0, 0.15, 0),
            smart_money=DimensionScore(3.0, 0.20, 0),
            total=3.0,
        )
        steps = []
        engine._validate_suggestion("强烈建议买入", mock_score, steps)
        assert any("分歧" in str(s) for s in steps)

    def test_step_rules_returns_dict(self):
        engine = DecisionEngine()
        result = engine._step_rules("000000")
        assert isinstance(result, dict)
        assert "forced_sell" in result

    def test_step_scoring_returns_none_or_score(self):
        engine = DecisionEngine()
        score = engine._step_scoring("000000")
        # None 或 FundScore 都是可接受的
        assert score is None or hasattr(score, "total")

    def test_step_risk_returns_blocked_status(self):
        engine = DecisionEngine()
        risk = engine._step_risk("000000", cash=100000)
        assert isinstance(risk, dict)
        assert "blocked" in risk
        assert "reason" in risk