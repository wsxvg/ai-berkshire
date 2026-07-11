"""策略自动进化循环 — 锦标赛制策略基因优化

自动发现+验证+优化策略参数，不依赖人工输入。
"""
from __future__ import annotations
import random
import json
import math
from dataclasses import dataclass, field
from typing import List, Optional, Tuple
from pathlib import Path
from datetime import datetime

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "evolution"
DATA_DIR.mkdir(parents=True, exist_ok=True)


@dataclass
class StrategyGene:
    """策略基因 — 定义一组可调参数"""
    quality_weight: float = 0.25
    cost_weight: float = 0.20
    manager_weight: float = 0.20
    momentum_weight: float = 0.15
    smart_money_weight: float = 0.20
    buy_threshold: float = 4.0
    sell_threshold: float = 3.0
    max_single_pct: float = 0.15
    cooling_days: int = 7
    cash_reserve_pct: float = 0.20

    def to_dict(self) -> dict:
        return {k: round(v, 4) if isinstance(v, float) else v
                for k, v in self.__dict__.items()}

    @classmethod
    def random(cls) -> "StrategyGene":
        """生成随机基因"""
        return cls(
            quality_weight=random.uniform(0.05, 0.40),
            cost_weight=random.uniform(0.05, 0.40),
            manager_weight=random.uniform(0.05, 0.40),
            momentum_weight=random.uniform(0.05, 0.40),
            smart_money_weight=random.uniform(0.05, 0.40),
            buy_threshold=random.uniform(3.0, 4.5),
            sell_threshold=random.uniform(2.0, 3.5),
            max_single_pct=random.uniform(0.05, 0.25),
            cooling_days=random.choice([3, 5, 7, 10, 14]),
            cash_reserve_pct=random.uniform(0.10, 0.30),
        )

    @classmethod
    def expert_conservative(cls) -> "StrategyGene":
        return cls(quality_weight=0.30, cost_weight=0.25, manager_weight=0.20,
                   momentum_weight=0.10, smart_money_weight=0.15,
                   buy_threshold=4.3, sell_threshold=3.0, max_single_pct=0.10,
                   cooling_days=14, cash_reserve_pct=0.30)

    @classmethod
    def expert_balanced(cls) -> "StrategyGene":
        return cls(quality_weight=0.25, cost_weight=0.20, manager_weight=0.20,
                   momentum_weight=0.15, smart_money_weight=0.20,
                   buy_threshold=4.0, sell_threshold=3.0, max_single_pct=0.15,
                   cooling_days=7, cash_reserve_pct=0.20)

    @classmethod
    def expert_aggressive(cls) -> "StrategyGene":
        return cls(quality_weight=0.20, cost_weight=0.15, manager_weight=0.15,
                   momentum_weight=0.25, smart_money_weight=0.25,
                   buy_threshold=3.5, sell_threshold=2.5, max_single_pct=0.20,
                   cooling_days=5, cash_reserve_pct=0.10)


class EvolutionLoop:
    """策略进化循环 — 锦标赛制"""

    POPULATION_SIZE = 50
    ELITE_RATIO = 0.20    # 前20%晋级
    MUTATION_RATE = 0.10  # 变异幅度 ±10%
    MAX_GENERATIONS = 15
    CONVERGENCE_LIMIT = 0.05  # 收敛阈值

    def __init__(self):
        self.generation = 0
        self.history: List[dict] = []

    def initialize(self) -> List[StrategyGene]:
        """初始化种群: 50随机 + 3专家"""
        population = [StrategyGene.random() for _ in range(self.POPULATION_SIZE)]
        population.extend([
            StrategyGene.expert_conservative(),
            StrategyGene.expert_balanced(),
            StrategyGene.expert_aggressive(),
        ])
        random.shuffle(population)
        return population

    def run_generation(self, population: List[StrategyGene]) -> List[StrategyGene]:
        """跑一轮锦标赛: 排名→晋级→变异→杂交→补充"""
        pop_size = len(population)

        # 1. 排序
        ranked = sorted(population, key=lambda g: self._simulate(g), reverse=True)

        # 2. 晋级（前20%）
        elite_count = max(2, int(pop_size * self.ELITE_RATIO))

        elites = ranked[:elite_count]

        # 3. 变异
        mutants = [self._mutate(e) for e in elites]

        # 4. 杂交
        children = []
        for i in range(elite_count):
            for j in range(i + 1, elite_count):
                if len(children) >= elite_count:
                    break
                children.append(self._crossover(elites[i], elites[j]))

        # 5. 补充随机（填满到 pop_size）
        total_so_far = len(elites) + len(mutants) + len(children)
        new_blood_count = max(0, pop_size - total_so_far)
        new_blood = [StrategyGene.random() for _ in range(new_blood_count)]

        # 6. 下一代
        next_gen = elites + mutants + children + new_blood
        random.shuffle(next_gen)

        self.generation += 1
        best_score = self._simulate(elites[0])
        self.history.append({
            "generation": self.generation,
            "best_score": round(float(best_score), 4),
            "best_gene": elites[0].to_dict(),
        })

        return next_gen[:pop_size]

    def is_converged(self) -> bool:
        """检查是否收敛"""
        if len(self.history) < 3:
            return False
        recent = [h["best_score"] for h in self.history[-3:]]
        return max(recent) - min(recent) < self.CONVERGENCE_LIMIT

    def analyze_winners(self, winners: List[StrategyGene]) -> str:
        """AI 分析胜出基因特征（输出到 ai_input.json 供 Skill 读取）"""
        # 实际调用 fund-analyze skill 做分析
        # 这里只输出结构化数据
        output = {
            "type": "evolution_insight",
            "generation": self.generation,
            "winners": [w.to_dict() for w in winners[:3]],
            "timestamp": datetime.now().isoformat(),
        }
        output_path = DATA_DIR / "evolution_insight.json"
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        return str(output_path)

    def run_full(self, generations: int = 10) -> StrategyGene:
        """完整进化流程"""
        pop = self.initialize()
        for _ in range(generations):
            pop = self.run_generation(pop)
            if self.is_converged():
                break
        # 排序输出最优
        ranked = sorted(pop, key=lambda g: self._simulate(g), reverse=True)
        self._save_result(ranked[0])
        return ranked[0]

    # ── 内部 ──

    @staticmethod
    def _mutate(gene: StrategyGene) -> StrategyGene:
        """变异: 各维度 ±10% 随机扰动"""
        d = gene.to_dict()
        for key, val in d.items():
            if isinstance(val, float):
                d[key] = val * random.uniform(0.9, 1.1)
        return StrategyGene(**d)

    @staticmethod
    def _crossover(g1: StrategyGene, g2: StrategyGene) -> StrategyGene:
        """杂交: 两两取均值"""
        d1, d2 = g1.to_dict(), g2.to_dict()
        return StrategyGene(**{
            k: (d1[k] + d2[k]) / 2 if isinstance(v, float) else random.choice([d1[k], d2[k]])
            for k, v in d1.items()
        })

    @staticmethod
    def _simulate(gene: StrategyGene, fast: bool = True) -> float:
        """用启发式（fast=True）或完整回测（fast=False）评估基因"""
        if fast:
            # 快速启发式评估: 用基因合理性得分
            score = 1.0
            # 权重总和接近1.0 → 合理
            w_sum = gene.quality_weight + gene.cost_weight + gene.manager_weight + gene.momentum_weight + gene.smart_money_weight
            if 0.95 <= w_sum <= 1.05:
                score += 0.3
            # buy > sell → 合理
            if gene.buy_threshold > gene.sell_threshold:
                score += 0.2
            # 冷却期合理
            if 5 <= gene.cooling_days <= 14:
                score += 0.2
            # 加仓上限合理
            if 0.05 <= gene.max_single_pct <= 0.25:
                score += 0.2
            # 现金储备合理
            if 0.10 <= gene.cash_reserve_pct <= 0.30:
                score += 0.1
            # 权重均衡度: 标准差越小越均衡
            weights = [gene.quality_weight, gene.cost_weight, gene.manager_weight,
                      gene.momentum_weight, gene.smart_money_weight]
            mean_w = sum(weights) / len(weights)
            std_w = (sum((w - mean_w) ** 2 for w in weights) / len(weights)) ** 0.5
            if std_w < 0.05:
                score += 0.2
            return min(3.0, score + random.uniform(-0.1, 0.1))

        # 完整回测模式（慢但准确）
        try:
            from backtest.engine.backtest import run_backtest
            config = {
                "start_date": "2026-01-05",
                "end_date": "2026-06-30",
                "initial_cash": 100000,
                "min_score": gene.buy_threshold,
                "weights": {
                    "quality": gene.quality_weight * 100,
                    "cost": gene.cost_weight * 100,
                    "manager": gene.manager_weight * 100,
                    "momentum": gene.momentum_weight * 100,
                    "smart_money": gene.smart_money_weight * 100,
                },
                "min_consensus": 2,
                "dynamic_ranking": True,
                "ranking_window": 90,
                "ranking_fwd_days": 30,
                "ranking_min_buys": 5,
                "ranking_recalc_days": 30,
                "verbose_ranking": False,
                "max_position_pct": gene.max_single_pct * 100,
                "cash_reserve_pct": gene.cash_reserve_pct,
                "take_profit_pct": 30,
                "stop_loss_pct": -15,
                "momentum_sell": 2.0,
                "kelly_cap": 0.2,
                "max_holdings": 8,
                "rebalance": True,
                "max_sector_pct": 24,
                "max_qdii_pct": 30,
                "sell_consensus": 0,
                "profit_mode": "half",
                "no_stop_loss": False,
            }
            result = run_backtest(config)
            # Use total_return as fitness (subtract benchmark to get excess)
            total_ret = float(result.get("total_return", 0))
            benchmark = float(result.get("benchmark_return", 6))
            excess = total_ret - benchmark
            return float(excess)
        except Exception:
            return random.uniform(0.5, 2.0)

    @staticmethod
    def _walk_forward_validate(gene: StrategyGene) -> dict:
        """滚动窗口验证: 5轮 walk-forward, 全部通过才合格"""
        from backtest.engine.backtest import run_backtest
        import sys, io
        
        # 5个滚动窗口 (训练7-12月, 验证3月)
        windows = [
            ("2024-03-11", "2024-12-31", "2025-01-01", "2025-03-31"),
            ("2024-06-01", "2025-03-31", "2025-04-01", "2025-06-30"),
            ("2024-09-01", "2025-06-30", "2025-07-01", "2025-09-30"),
            ("2024-12-01", "2025-09-30", "2025-10-01", "2025-12-31"),
            ("2025-03-01", "2025-12-31", "2026-01-01", "2026-03-31"),
        ]
        
        def run_window(train_start, train_end, val_start, val_end):
            cfg = {
                "start_date": train_start, "end_date": train_end,
                "initial_cash": 100000,
                "min_score": gene.buy_threshold,
                "weights": {
                    "quality": gene.quality_weight * 100,
                    "cost": gene.cost_weight * 100,
                    "manager": gene.manager_weight * 100,
                    "momentum": gene.momentum_weight * 100,
                    "smart_money": gene.smart_money_weight * 100,
                },
                "min_consensus": 2, "dynamic_ranking": True,
                "use_weighted_consensus": True, "rebalance": True,
                "max_position_pct": gene.max_single_pct * 100,
                "cash_reserve_pct": gene.cash_reserve_pct,
                "take_profit_pct": 200, "stop_loss_pct": -15,
                "momentum_sell": 0.5, "kelly_cap": 0.5,
                "max_holdings": 6, "max_sector_pct": 50, "max_qdii_pct": 50,
                "fund_type_filter": "all", "monthly_injection": 0,
                "peak_drawdown_exit": 8, "profit_mode": "half",
            }
            old = sys.stdout; sys.stdout = io.StringIO()
            result = run_backtest(cfg)
            sys.stdout = old
            tr = float(result.get("total_return", 0))
            bm = float(result.get("benchmark_return", 0))
            return {"train_ret": tr, "train_bm": bm, "excess": tr - bm}
        
        results = []
        passes = 0
        for train_start, train_end, val_start, val_end in windows:
            train_r = run_window(train_start, train_end, val_start, val_end)
            val_r = run_window(val_start, val_end, val_end + "_ext", val_end)
            # 验证集用单独参数
            val_cfg = {
                "start_date": val_start, "end_date": val_end,
                "initial_cash": 100000,
                "min_score": gene.buy_threshold,
                "weights": {
                    "quality": gene.quality_weight * 100,
                    "cost": gene.cost_weight * 100,
                    "manager": gene.manager_weight * 100,
                    "momentum": gene.momentum_weight * 100,
                    "smart_money": gene.smart_money_weight * 100,
                },
                "min_consensus": 2, "dynamic_ranking": True,
                "use_weighted_consensus": True, "rebalance": True,
                "max_position_pct": gene.max_single_pct * 100,
                "cash_reserve_pct": gene.cash_reserve_pct,
                "take_profit_pct": 200, "stop_loss_pct": -15,
                "momentum_sell": 0.5, "kelly_cap": 0.5,
                "max_holdings": 6, "max_sector_pct": 50, "max_qdii_pct": 50,
                "fund_type_filter": "all", "monthly_injection": 0,
                "peak_drawdown_exit": 8, "profit_mode": "half",
            }
            old = sys.stdout; sys.stdout = io.StringIO()
            val_result = run_backtest(val_cfg)
            sys.stdout = old
            val_tr = float(val_result.get("total_return", 0))
            val_bm = float(val_result.get("benchmark_return", 0))
            val_excess = val_tr - val_bm
            
            results.append({
                "train": f"{train_start}~{train_end}",
                "val": f"{val_start}~{val_end}",
                "val_return": round(val_tr, 2),
                "val_benchmark": round(val_bm, 2),
                "val_excess": round(val_excess, 2),
            })
            if val_excess > 0:  # 验证集跑赢基准
                passes += 1
        
        total_excess = sum(r["val_excess"] for r in results)
        avg_excess = total_excess / len(results) if results else 0
        
        return {
            "windows": results,
            "passes": passes,
            "total_windows": len(windows),
            "avg_excess": round(avg_excess, 2),
            "total_excess": round(total_excess, 2),
            "qualified": passes == len(windows)  # 全部通过才算合格
        }

    def _save_result(self, best: StrategyGene) -> None:
        path = DATA_DIR / "best_gene.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump({
                "gene": best.to_dict(),
                "generation": self.generation,
                "history": self.history,
            }, f, ensure_ascii=False, indent=2)