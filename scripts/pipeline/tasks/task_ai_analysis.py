"""AI 分析数据输出 task"""
from __future__ import annotations
import json
from pathlib import Path
from scripts.pipeline.engine import PipelineEngine, PipelineTask

try:
    from tools.logutil import get_logger
except Exception:
    from logutil import get_logger

_logger = get_logger("pipeline.ai_analysis")

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"


@PipelineEngine.register
class TaskAIAnalysis(PipelineTask):
    name = "ai_analysis"
    description = "输出评分数据和规则结论供 Skill 读取解释"
    depends_on = ["scoring"]

    def execute(self, context: dict, offline: bool = False) -> dict:
        scores = context.get("scoring", {}).get("scores", {})
        rules = context.get("rules", {}).get("rules_result", {})
        trading = context.get("trading", {}).get("signals", {})

        # 输出结构化 JSON 供 Claude Code Skill 读取
        output = {
            "scores": scores,
            "rules": rules,
            "trading_signals": trading,
            "timestamp": __import__("datetime").datetime.now().isoformat(),
        }

        (DATA_DIR / "auto").mkdir(parents=True, exist_ok=True)
        output_path = DATA_DIR / "auto" / "ai_input.json"
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)

        _logger.info(f"AI data written to {output_path}")
        _logger.info(f"Run: /fund-analyze {', '.join(list(scores.keys())[:3])}")

        return {"ai_output": str(output_path), "data": output}