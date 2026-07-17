"""基金评分 task"""
from __future__ import annotations
from scripts.pipeline.engine import PipelineEngine, PipelineTask

try:
    from tools.logutil import get_logger
except Exception:
    from logutil import get_logger

_logger = get_logger("pipeline.scoring")


@PipelineEngine.register
class TaskScoring(PipelineTask):
    name = "scoring"
    description = "基金5维评分"
    depends_on = ["holdings"]

    def execute(self, context: dict, offline: bool = False) -> dict:
        from tools.fund_scorer import score_fund

        holdings = context.get("holdings", {}).get("holdings", {})
        fund_codes = set()
        for user_name, funds in holdings.items():
            for f in funds:
                code = f.get("code", "")
                if code:
                    fund_codes.add(code)

        if not fund_codes:
            _logger.info("Scoring: no funds to score")
            return {"scores": {}}

        scores = {}
        for code in sorted(fund_codes):
            try:
                result = score_fund(code)
                if result:
                    scores[code] = {
                        "total": result.total,
                        "quality": result.quality.score,
                        "cost": result.cost.score,
                        "manager": result.manager.score,
                        "momentum": result.momentum.score,
                        "smart_money": result.smart_money.score,
                    }
            except Exception as e:
                _logger.warning(f"[{code}] scoring failed: {e}")

        _logger.info(f"Scoring: {len(scores)} funds rated")
        return {"scores": scores}