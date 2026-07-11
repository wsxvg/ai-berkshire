"""京东金融基金数据提供者

包装 jd_finance_api.py 的零散函数，实现 IFundDataProvider 接口，
输出标准化 models。
"""
from __future__ import annotations
from typing import List, Optional
from datetime import datetime
import sys
import os
from pathlib import Path

# 添加项目根到 path，使能 import tools.jd_finance_api
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from tools.data_provider.base import IFundDataProvider
from tools.data_provider.models import (
    NavPoint, StockHolding, Holdings,
    FeeStructure, ManagerInfo, FundProfile,
)
from tools import jd_finance_api as jd


class JDFinanceProvider(IFundDataProvider):
    """京东金融数据源"""

    @property
    def name(self) -> str:
        return "jd"

    def get_nav(self, code: str, start: Optional[str] = None,
                end: Optional[str] = None) -> List[NavPoint]:
        chart = jd.get_fund_chart_data(code)
        points = []
        for cp in chart.get("chart_points", []):
            nav_date = cp.get("xAxis", "")
            nav_val = _float(cp.get("yAxis", 0))
            if not nav_date:
                continue
            if start and nav_date < start:
                continue
            if end and nav_date > end:
                continue
            points.append(NavPoint(
                date=nav_date,
                nav=nav_val,
                accumulated_nav=nav_val,  # chart_data 是累计收益率
                daily_return=0.0,
            ))
        return points

    def get_holdings(self, code: str, quarter: Optional[str] = None) -> Holdings:
        hd = jd.get_fund_holdings_distribution(code)
        if not hd:
            return Holdings(quarter=quarter or "", publish_date="")

        top_stocks = []
        for s in hd.get("top_stocks", []):
            top_stocks.append(StockHolding(
                code=s.get("code", ""),
                name=s.get("name", ""),
                ratio=float(s.get("ratio", 0)),
                pe=float(s.get("pe", 0)) if s.get("pe") else None,
                pb=float(s.get("pb", 0)) if s.get("pb") else None,
            ))

        return Holdings(
            quarter=hd.get("report_date", quarter or ""),
            publish_date=hd.get("publish_date", ""),
            top_stocks=top_stocks,
            asset_allocation={
                "stock": _float(hd.get("stock_ratio")),
                "bond": _float(hd.get("bond_ratio")),
                "cash": _float(hd.get("cash_ratio")),
                "other": _float(hd.get("other_ratio")),
            },
        )

    def get_fee(self, code: str) -> FeeStructure:
        rules = jd.get_fund_trade_rules(code)
        if not rules:
            return FeeStructure(manage_fee=0, custody_fee=0)

        return FeeStructure(
            manage_fee=float(rules.get("manage_fee", 0)),
            custody_fee=float(rules.get("custody_fee", 0)),
            purchase_fee_rates=[{"min_amount": 0, "rate": float(rules.get("purchase_fee", 0))}],
            redeem_fee_rates=rules.get("redeem_fees", []),
            service_fee=float(rules.get("sale_fee", 0)) if rules.get("sale_fee") else None,
        )

    def get_manager(self, code: str) -> ManagerInfo:
        mgr = jd.get_fund_manager(code)
        if not mgr or not mgr.get("managers"):
            return ManagerInfo(name="", start_date="")

        m = mgr["managers"][0]
        name = m.get("name", "")
        tenure = m.get("tenure", "")

        employ_perf = _float(m.get("employ_performance", 0))
        radar_score = float(m.get("total_score", 0)) if m.get("total_score") else None

        return ManagerInfo(
            name=name,
            start_date=tenure,
            tenure_return=employ_perf if employ_perf else None,
            tenure_years=None,
            managed_scale=_float(m.get("manage_scale")) if m.get("manage_scale") else None,
            funds_count=None,
            avg_return=radar_score,
        )

    def get_profile(self, code: str) -> FundProfile:
        pf = jd.get_fund_profile(code)
        if not pf:
            return FundProfile(code=code, name="", fund_type="", establish_date="")

        full_name = pf.get("full_name", "")
        scale_str = pf.get("scale", "")

        # 判断基金类型
        fund_type = self._infer_fund_type(full_name)

        manager = self.get_manager(code)

        return FundProfile(
            code=code,
            name=full_name,
            fund_type=fund_type,
            establish_date=pf.get("established", ""),
            scale=_parse_scale(scale_str),
            manager=manager if manager.name else None,
            company=pf.get("manager_company", ""),
        )

    def get_nav_history(self, code: str) -> List[NavPoint]:
        return self.get_nav(code)

    @staticmethod
    def _infer_fund_type(name: str) -> str:
        name_lower = name.lower()
        if "qdii" in name_lower:
            return "QDII"
        if "指数" in name or "etf" in name_lower or "联接" in name:
            return "指数型"
        if "债券" in name or "债" in name:
            return "债券型"
        if "货币" in name:
            return "货币型"
        if "混合" in name:
            return "混合型"
        return "股票型"


def _float(v) -> float:
    if v is None:
        return 0.0
    try:
        return float(str(v).replace("%", "").strip() or 0)
    except (ValueError, TypeError):
        return 0.0


def _parse_scale(scale_text: str) -> Optional[float]:
    """解析规模文本 "12.34亿元" → 12.34"""
    if not scale_text:
        return None
    s = str(scale_text).replace(",", "").replace(" ", "")
    import re
    nums = re.findall(r"[\d.]+", s)
    if not nums:
        return None
    val = float(nums[0])
    if "万" in s and "亿" not in s:
        val /= 10000
    return round(val, 2)