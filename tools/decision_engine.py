"""决策引擎 — 5步决策管线

流程: Rules → Scoring → Risk Check → Backtest → 最终决策

核心原则:
- AI 建议仅供参考，不主导决策
- 硬性规则（加权清仓等）优先于评分
- 风险检查不可跳过
- 回测验证 (Phase 7 完成后生效)
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from pathlib import Path
import sys
import json
from datetime import datetime, timedelta

# ── 项目路径 ──
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

DATA_DIR = _PROJECT_ROOT / "data"
CACHE_DIR = DATA_DIR / "fund_cache"

# ── 风险参数 ──
RISK_FREE_RATE = 0.025
MAX_SINGLE_PCT = 0.15     # 单只基金最大仓位 15%
MAX_QDII_PCT = 0.30       # QDII 总仓位上限 30%
CASH_RESERVE_PCT = 0.20   # 现金储备 20%
COOLING_DAYS = 7           # 冷却期 7 天（T+7 惩罚约束）
BUY_THRESHOLD = 4.0        # 买入阈值
WATCH_THRESHOLD = 3.3      # 观察阈值
SELL_THRESHOLD = 3.0       # 卖出阈值


@dataclass
class DecisionResult:
    """决策结果"""
    fund_code: str
    action: str = "hold"           # buy/hold/reduce/sell/switch
    amount: float = 0.0       # 0 表示不操作
    priority: str = "参考"      # 强制/建议/参考
    reason: str = ""
    steps: List[dict] = field(default_factory=list)  # 五步日志
    backtest: Optional[dict] = None
    ai_suggestion: Optional[str] = None


class DecisionEngine:
    """决策引擎"""

    def evaluate(
        self,
        fund_code: str,
        cash: float,
        ai_suggestion: Optional[str] = None,
    ) -> DecisionResult:
        """5步决策管线

        Args:
            fund_code: 基金代码
            cash: 可用资金
            ai_suggestion: AI 建议文本（可选，仅参考）
        Returns:
            DecisionResult 最终决策
        """
        result = DecisionResult(fund_code=fund_code, ai_suggestion=ai_suggestion)
        steps = []

        # ── Step 1: Rules Engine ──
        rules_result = self._step_rules(fund_code)
        steps.append({"step": 1, "name": "rules", "result": rules_result})

        # 硬性清仓优先
        if rules_result.get("forced_sell"):
            result.action = "sell"
            result.amount = rules_result.get("sell_pct", 100)
            result.priority = "强制"
            result.reason = rules_result.get("reason", "硬性清仓")
            result.steps = steps
            return result

        # ── Step 2: Scoring Engine ──
        score = self._step_scoring(fund_code)
        steps.append({
            "step": 2, "name": "scoring",
            "result": {
                "total": score.total if score else 0,
                "quality": score.quality.score if score else 0,
                "cost": score.cost.score if score else 0,
                "manager": score.manager.score if score else 0,
                "momentum": score.momentum.score if score else 0,
                "smart_money": score.smart_money.score if score else 0,
            } if score else {},
        })

        if score is None:
            result.action = "hold"
            result.reason = "评分数据不可用"
            result.steps = steps
            return result

        # ── Step 3: Validate AI suggestion vs score ──
        if ai_suggestion:
            self._validate_suggestion(ai_suggestion, score, steps)

        # ── Step 4: Risk Check ──
        risk_result = self._step_risk(fund_code, cash)
        steps.append({"step": 4, "name": "risk", "result": risk_result})

        if risk_result.get("blocked"):
            result.action = "hold"
            result.priority = "强制"
            result.reason = risk_result.get("reason", "风险检查未通过")
            result.steps = steps
            return result

        # ── Step 5: Final Decision ──
        decision = self._make_decision(score, cash, risk_result)
        result.action = decision["action"]
        result.amount = decision["amount"]
        result.priority = decision["priority"]
        result.reason = decision["reason"]
        result.steps = steps
        return result

    def evaluate_portfolio(
        self,
        holdings: List[dict],
        cash: float,
    ) -> List[DecisionResult]:
        """全组合评估，按优先级排序返回"""
        results = []
        for h in holdings:
            code = h.get("code", "")
            if not code:
                continue
            result = self.evaluate(code, cash)
            results.append(result)

        # 按优先级排序：强制 > 建议 > 参考
        priority_map = {"强制": 0, "建议": 1, "参考": 2}
        results.sort(key=lambda r: priority_map.get(r.priority, 99))
        return results

    # ── Step implementations ──

    def _step_rules(self, fund_code: str) -> dict:
        """Step 1: 规则引擎"""
        try:
            from tools.fund_rules import analyze_all, swap_cost, take_profit_level
            rules = analyze_all(fund_code)

            # 硬性清仓
            if rules.get("weighted_clear", {}).get("verdict") == "red_clear":
                shield = rules.get("buy_shield", {})
                if not shield.get("shield_active"):
                    sell_pct = 100
                    return {
                        "forced_sell": True,
                        "sell_pct": sell_pct,
                        "reason": f"加权清仓信号（权重{rules['weighted_clear']['weighted_clear']}）",
                    }
                else:
                    return {"forced_sell": False, "warning": "清仓信号但买入护盾激活, 分歧观察"}

            return {"forced_sell": False, "rules": rules}
        except Exception as e:
            return {"forced_sell": False, "error": str(e)}

    def _step_scoring(self, fund_code: str):
        """Step 2: 评分引擎"""
        try:
            from tools.fund_scorer import score_fund
            return score_fund(fund_code)
        except Exception:
            return None

    def _step_risk(self, fund_code: str, cash: float) -> dict:
        """Step 4: 风险检查"""
        blocked = False
        reasons = []

        # 1. 冷却期检查
        if self._check_cooling(fund_code):
            blocked = True
            reasons.append(f"冷却期内（{COOLING_DAYS}天）")

        # 2. 单只仓位上限
        current_position = self._get_position(fund_code)
        max_position = cash * MAX_SINGLE_PCT
        if current_position >= max_position:
            blocked = True
            reasons.append(f"仓位超限（{current_position:.0f} > {max_position:.0f}）")

        # 3. QDII 总仓位
        total_qdii = self._get_total_qdii()
        max_qdii = cash * MAX_QDII_PCT
        if total_qdii >= max_qdii:
            blocked = True
            reasons.append(f"QDII 总仓位超限")

        return {
            "blocked": blocked,
            "reason": "; ".join(reasons) if reasons else "通过",
            "current_position": current_position,
            "max_position": max_position,
        }

    def _make_decision(
        self, score, cash: float, risk: dict
    ) -> dict:
        """Step 5: 最终决策"""
        total = score.total

        if total >= BUY_THRESHOLD:
            # 计算建议金额
            try:
                from tools.fund_planner import kelly_allocation
                plan = kelly_allocation(cash)
                amount = 0
                for p in plan:
                    if p.get("code") == score.fund_code:
                        amount = p.get("suggested_amount", 0)
                        break
                if amount == 0 and plan:
                    amount = plan[0].get("suggested_amount", 0)
            except Exception:
                amount = min(
                    round(cash * (1 - CASH_RESERVE_PCT) * (total / 5.0) / 100) * 100,
                    cash * MAX_SINGLE_PCT,
                )

            return {
                "action": "buy",
                "amount": max(100, int(amount)),
                "priority": "强制" if total >= 4.5 else "建议",
                "reason": f"评分 {total:.2f}，达到买入阈值",
            }

        elif total >= WATCH_THRESHOLD:
            return {
                "action": "hold",
                "amount": 0,
                "priority": "参考",
                "reason": f"评分 {total:.2f}，处于观察区间，等待信号确认",
            }

        else:
            # 评分低于卖出阈值
            if total <= SELL_THRESHOLD:
                return {
                    "action": "sell" if score.stale else "reduce",
                    "amount": 50 if score.stale else 0,
                    "priority": "建议",
                    "reason": f"评分 {total:.2f}，低于卖出阈值{SELL_THRESHOLD}" if not score.stale
                             else f"评分 {total:.2f} 且数据陈旧({score.stale})，建议减仓",
                }
            return {
                "action": "hold",
                "amount": 0,
                "priority": "参考",
                "reason": f"评分 {total:.2f}，低于买入阈值",
            }

    def _validate_suggestion(
        self,
        suggestion: str,
        score,
        steps: List[dict],
    ) -> None:
        """记录 AI 建议与程序评分的分歧"""
        # 提取 AI 建议中的情绪倾向
        positive = any(w in suggestion for w in ["买入", "买", "加仓", "增持", "看好"])
        negative = any(w in suggestion for w in ["卖出", "卖", "减仓", "减持", "回避"])

        programmatic_buy = score.total >= BUY_THRESHOLD
        programmatic_sell = score.total <= SELL_THRESHOLD

        if positive and not programmatic_buy:
            steps.append({
                "step": 3, "name": "分歧",
                "detail": f"AI建议买入但评分{score.total:.2f}<{BUY_THRESHOLD}，分歧已记录",
            })
        if negative and not programmatic_sell:
            steps.append({
                "step": 3, "name": "分歧",
                "detail": f"AI建议卖出但评分{score.total:.2f}>{SELL_THRESHOLD}，分歧已记录",
            })

    # ── Helpers ──

    @staticmethod
    def _check_cooling(fund_code: str) -> bool:
        """检查冷却期（最近操作是否在 COOLING_DAYS 天内）"""
        status_path = DATA_DIR / "auto" / "status.json"
        if not status_path.exists():
            return False
        try:
            status = json.loads(status_path.read_text("utf-8"))
            operations = status.get("operations", [])
            now = datetime.now()
            for op in operations:
                if op.get("code") == fund_code:
                    op_date = datetime.fromisoformat(op.get("date", ""))
                    if (now - op_date).days < COOLING_DAYS:
                        return True
        except Exception:
            pass
        return False

    @staticmethod
    def _get_position(fund_code: str) -> float:
        """获取当前仓位金额"""
        status_path = DATA_DIR / "auto" / "status.json"
        if not status_path.exists():
            return 0
        try:
            status = json.loads(status_path.read_text("utf-8"))
            for h in status.get("my_holdings", []):
                if h.get("code") == fund_code:
                    return float(h.get("amount", 0))
        except Exception:
            pass
        return 0

    @staticmethod
    def _get_total_qdii() -> float:
        """获取 QDII 总仓位"""
        status_path = DATA_DIR / "auto" / "status.json"
        if not status_path.exists():
            return 0
        try:
            status = json.loads(status_path.read_text("utf-8"))
            total = 0
            for h in status.get("my_holdings", []):
                if h.get("is_qdii"):
                    total += float(h.get("amount", 0))
            return total
        except Exception:
            return 0


# ── CLI ──
def main():
    import argparse
    parser = argparse.ArgumentParser(description="Decision Engine CLI")
    parser.add_argument("--evaluate", type=str, help="评估指定基金")
    parser.add_argument("--cash", type=float, default=100000, help="可用资金")
    parser.add_argument("--ai-suggestion", type=str, help="AI建议文本")
    args = parser.parse_args()

    if args.evaluate:
        engine = DecisionEngine()
        result = engine.evaluate(args.evaluate, args.cash, args.ai_suggestion)
        text = json.dumps({
            "action": result.action,
            "fund_code": result.fund_code,
            "amount": result.amount,
            "priority": result.priority,
            "reason": result.reason,
            "steps": result.steps,
        }, ensure_ascii=False, indent=2)
        print(text)


if __name__ == "__main__":
    main()