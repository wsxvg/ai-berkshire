"""绩效归因与复盘 — Brinson 归因 + 风格归因 + 进化反馈

分析"为什么赚/亏了"，归因结果反哺策略进化。
"""
from __future__ import annotations
from typing import List, Dict, Optional
from pathlib import Path
import json
from datetime import datetime

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
MEMORY_DIR = DATA_DIR / "memory"


class PerformanceAttribution:
    """绩效归因分析"""

    @staticmethod
    def brinson_attribution(portfolio: Dict[str, float],
                            benchmark: str = "沪深300") -> dict:
        """Brinson 归因分析

        Args:
            portfolio: {fund_code: weight_pct} 组合配置
            benchmark: 基准指数
        Returns:
            {allocation_effect, selection_effect, interaction_effect}
        """
        if not portfolio:
            return {
                "allocation_effect": 0.0,
                "selection_effect": 0.0,
                "interaction_effect": 0.0,
                "explanation": "无持仓数据",
            }

        # 从 jd_finance_api 获取各基金和基准的收益数据
        try:
            from tools.jd_finance_api import get_fund_chart_data
            import datetime

            total_weight = sum(portfolio.values())
            if total_weight <= 0:
                return {"error": "无效的权重"}

            # 归一化权重
            weights = {k: v / total_weight for k, v in portfolio.items()}

            # 计算各基金近 1 月收益
            fund_returns = {}
            for code in portfolio:
                try:
                    chart = get_fund_chart_data(code)
                    points = chart.get("chart_points", [])
                    if len(points) >= 2:
                        last = float(points[-1].get("yAxis", 0))
                        prev = float(points[-len(points)//6].get("yAxis", 0))  # 约1月前
                        fund_returns[code] = (last - prev) / (abs(prev) + 0.01) * 100
                    else:
                        fund_returns[code] = 0
                except Exception:
                    fund_returns[code] = 0

            # 配置效应: sum(wi - bi) * Ri
            allocation = sum(
                (w - 1.0 / max(1, len(portfolio))) * fund_returns.get(code, 0)
                for code, w in weights.items()
            )

            # 选择效应: sum(bi * (Ri - Rb))
            avg_return = sum(fund_returns.values()) / max(1, len(fund_returns))
            selection = sum(
                (1.0 / max(1, len(portfolio))) * (fund_returns.get(code, 0) - avg_return)
                for code in portfolio
            )

            return {
                "allocation_effect": round(allocation, 2),
                "selection_effect": round(selection, 2),
                "interaction_effect": round(0.0, 2),
                "explanation": f"配置效应{allocation:+.2f}% 来自仓位分配，选择效应{selection:+.2f}% 来自基金选择",
                "fund_returns": fund_returns,
            }
        except Exception as e:
            return {
                "allocation_effect": 0.0,
                "selection_effect": 0.0,
                "interaction_effect": 0.0,
                "error": str(e),
            }

    @staticmethod
    def style_attribution(portfolio: Dict[str, float]) -> dict:
        """风格暴露分析

        Returns:
            {large_cap, small_cap, value, growth} 各风格占比
        """
        # 穿透基金持仓到股票，按风格归类
        return {
            "large_cap": 0.0,
            "small_cap": 0.0,
            "value": 0.0,
            "growth": 0.0,
            "note": "需要持仓穿透数据才能计算",
        }

    @staticmethod
    def sector_attribution(portfolio: Dict[str, float]) -> dict:
        """行业暴露分析"""
        return {"note": "需要持仓穿透数据才能计算"}


class ReviewReport:
    """自动复盘报告生成"""

    def __init__(self):
        self._memory = None
        try:
            from tools.memory.fund_memory import FundMemoryLog
            self._memory = FundMemoryLog()
        except ImportError:
            pass

    def monthly(self, portfolio: list, cash: float) -> str:
        """每月自动归因报告"""
        if not portfolio:
            return "无持仓数据"

        lines = []
        lines.append(f"## {datetime.now().strftime('%Y-%m')} 月度归因报告")
        lines.append("")

        total_return = 0
        for h in portfolio:
            code = h.get("code", "")
            amount = float(h.get("amount", 0))
            profit = float(h.get("profit_rate", 0))
            total_return += amount * profit / 100

        lines.append(f"组合总收益: {total_return:.2f}")
        lines.append(f"持仓数量: {len(portfolio)} 只")

        # 归因（待完善）
        lines.append("")
        lines.append("### 归因分析")
        attr = PerformanceAttribution.brinson_attribution({})
        for key, val in attr.items():
            lines.append(f"- {key}: {val}")

        report = "\n".join(lines)

        # 存入记忆
        if self._memory:
            self._memory.store_insight("review", report)

        return report

    def trigger_evolution(self, attribution: dict) -> Optional[str]:
        """连续负贡献维度→自动降低权重（待完善）"""
        return None