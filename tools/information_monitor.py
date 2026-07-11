"""基金信息感知引擎 — 自动监测基金动态和宏观因子"""
from __future__ import annotations
from typing import Optional, Dict
from pathlib import Path
import json
import logging

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "monitor"
DATA_DIR.mkdir(parents=True, exist_ok=True)


class FundEventMonitor:
    """基金事件监测"""

    def __init__(self):
        self._cache_path = DATA_DIR / "manager_cache.json"
        self._manager_cache = self._load_cache()

    def check_manager_change(self, fund_code: str) -> Optional[dict]:
        """检测基金经理是否变更"""
        from tools.data_provider import get_data
        manager = get_data("get_manager", fund_code)
        if manager is None:
            return None

        current_name = manager.name
        cached = self._manager_cache.get(fund_code)

        if cached and cached != current_name:
            # 变更!
            self._manager_cache[fund_code] = current_name
            self._save_cache()
            return {
                "event": "manager_change",
                "fund_code": fund_code,
                "old": cached,
                "new": current_name,
            }

        if not cached:
            self._manager_cache[fund_code] = current_name
            self._save_cache()

        return None

    def check_dividend(self, fund_code: str) -> Optional[dict]:
        """检查分红（待接入数据源）"""
        return None

    def check_redemption_limit(self, fund_code: str) -> Optional[dict]:
        """检查是否暂停申购（待接入数据源）"""
        from tools.data_provider import get_data
        fee = get_data("get_fee", fund_code)
        if fee is None:
            return None
        return None  # 待完善

    def check_liquidation(self, fund_code: str, scale: float) -> Optional[dict]:
        """检查清盘预警（规模<5000万）"""
        if scale is not None and scale < 0.5:
            return {
                "event": "liquidation_warning",
                "fund_code": fund_code,
                "scale": scale,
                "warning": "规模低于5000万，存在清盘风险",
            }
        return None

    def _load_cache(self) -> dict:
        if self._cache_path.exists():
            return json.loads(self._cache_path.read_text("utf-8"))
        return {}

    def _save_cache(self) -> None:
        with open(self._cache_path, "w", encoding="utf-8") as f:
            json.dump(self._manager_cache, f, ensure_ascii=False, indent=2)


class MacroFactorMonitor:
    """宏观因子监测"""

    def __init__(self):
        self._cache_path = DATA_DIR / "macro_cache.json"
        self._cache = self._load_cache()

    def get_interest_rate(self) -> Optional[float]:
        """获取 LPR/国债收益率（尝试从央行数据接口获取）"""
        cached = self._cache.get("interest_rate")
        if cached is not None:
            return cached
        # 尝试从公开数据获取
        try:
            import akshare as ak
            bond = ak.bond_china_yield(start_date="20250101")
            if not bond.empty:
                rate = bond.iloc[-1].get("10年", None)
                if rate:
                    self.update(interest_rate=float(rate))
                    return float(rate)
        except Exception:
            pass
        return cached  # 返回缓存值或None

    def get_pmi(self) -> Optional[float]:
        """获取制造业 PMI（尝试从国家统计局接口获取）"""
        cached = self._cache.get("pmi")
        if cached is not None:
            return cached
        try:
            import akshare as ak
            pmi = ak.macro_china_pmi()
            if not pmi.empty:
                val = pmi.iloc[-1].get("pmi", None)
                if val:
                    self.update(pmi=float(val))
                    return float(val)
        except Exception:
            pass
        return cached

    def get_social_financing(self) -> Optional[float]:
        """获取社融数据（待接入数据源）"""
        return self._cache.get("social_financing")

    def update(self, interest_rate=None, pmi=None, social_financing=None) -> None:
        """手动更新宏观数据"""
        if interest_rate is not None:
            self._cache["interest_rate"] = interest_rate
        if pmi is not None:
            self._cache["pmi"] = pmi
        if social_financing is not None:
            self._cache["social_financing"] = social_financing
        with open(self._cache_path, "w", encoding="utf-8") as f:
            json.dump(self._cache, f, ensure_ascii=False)

    def adjust_score(self, fund_type: str, score_total: float) -> float:
        """根据宏观因子调整评分"""
        pmi = self.get_pmi()
        rate = self.get_interest_rate()

        adjustment = 0.0
        if pmi is not None:
            if pmi < 50 and "股票" in fund_type:
                adjustment -= 0.3  # PMI低于50，看空股票型
        if rate is not None:
            if rate > 3.0 and "债券" in fund_type:
                adjustment -= 0.2  # 利率上升，看空债券型

        return max(1.0, min(5.0, score_total + adjustment))

    def _load_cache(self) -> dict:
        if self._cache_path.exists():
            return json.loads(self._cache_path.read_text("utf-8"))
        return {}