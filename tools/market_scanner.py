"""全市场扫描引擎 — 从 10000+ 基金中自动筛选候选池"""
from __future__ import annotations
import json
from typing import List, Optional, Set
from pathlib import Path
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "scan"
DATA_DIR.mkdir(parents=True, exist_ok=True)


class FundScanner:
    """全市场基金扫描器"""

    def fetch_all_funds(self) -> list:
        """获取全市场基金列表（来源: AkShare 天天基金）"""
        try:
            import akshare as ak
            df = ak.fund_name_em()
            results = []
            for _, row in df.iterrows():
                code = str(row.get("基金代码", ""))
                name = str(row.get("基金名称", ""))
                fund_type = str(row.get("基金类型", ""))
                # 过滤: 排除货币基金/ETF联接/C类
                if "货币" in fund_type or "ETF联接" in name:
                    continue
                if name.endswith("C") or "C类" in fund_type:
                    continue
                results.append({
                    "code": code,
                    "name": name,
                    "type": fund_type,
                    "scale": float(row.get("单位净值", 0)),
                })
            logger.info("Fetched %d funds via akshare", len(results))
            return results
        except ImportError:
            logger.warning("akshare not installed, trying fallback...")
            return self._fetch_from_cache()
        except Exception as e:
            logger.warning("Failed to fetch funds: %s", e)
            return self._fetch_from_cache()

    def _fetch_from_cache(self) -> list:
        """从本地缓存获取基金列表（离线模式）"""
        from pathlib import Path
        import json
        cache_path = Path(__file__).resolve().parent.parent / "data" / "fund_list.json"
        if cache_path.exists():
            return json.loads(cache_path.read_text("utf-8"))
        return []

    def quick_score(self, fund_type: str, scale: float, cost: float) -> float:
        """用轻量维度粗筛（不调完整评分，只调API）"""
        score = 3.0
        # 规模稳定性: 规模越大越稳定
        if scale > 50:
            score += 1.0
        elif scale > 10:
            score += 0.5
        # 成本: 费率越低越好
        if cost < 0.6:
            score += 1.0
        elif cost < 1.0:
            score += 0.5
        else:
            score -= 0.5
        return min(5.0, max(1.0, score))

    def filter_pool(self, funds: List[dict], top_pct: float = 0.3) -> List[str]:
        """粗筛后取 top30%"""
        if not funds:
            return []
        # 按 quick_score 降序
        scored = [(f["code"], self.quick_score(
            f.get("type", ""), float(f.get("scale", 0)), float(f.get("cost", 1.5))
        )) for f in funds]
        scored.sort(key=lambda x: x[1], reverse=True)
        cutoff = max(1, int(len(scored) * top_pct))
        return [code for code, _ in scored[:cutoff]]


class CandidatePool:
    """候选池管理"""

    def __init__(self):
        self._path = DATA_DIR / "candidate_pool.json"

    @property
    def watch_list(self) -> List[str]:
        return self._load().get("watch_list", [])

    @property
    def candidates(self) -> List[str]:
        return self._load().get("candidates", [])

    def refresh(self, scanner: FundScanner) -> dict:
        """更新候选池"""
        all_funds = scanner.fetch_all_funds()
        codes = scanner.filter_pool(all_funds, top_pct=0.3)
        changes = {"new_watch": [], "dropped": []}

        old = set(self.candidates)
        new = set(codes[:200])

        # 新进
        for code in new - old:
            changes["new_watch"].append(code)

        # 掉出
        for code in old - new:
            changes["dropped"].append(code)

        # 更新观察池
        pool = {
            "candidates": list(new),
            "watch_list": codes[:20],
            "updated_at": datetime.now().isoformat(),
            "changes": changes,
        }
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(pool, f, ensure_ascii=False, indent=2)

        return changes

    def _load(self) -> dict:
        if self._path.exists():
            return json.loads(self._path.read_text("utf-8"))
        return {"candidates": [], "watch_list": [], "changes": {}}