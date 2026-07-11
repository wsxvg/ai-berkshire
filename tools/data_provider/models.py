"""场外基金数据标准化模型

统一数据模型，所有数据源 Provider 统一输出格式。
"""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import List, Optional


@dataclass
class NavPoint:
    """基金净值数据点（日频）"""
    date: str             # "2026-01-15"
    nav: float            # 单位净值
    accumulated_nav: float  # 累计净值
    daily_return: float   # 日收益率 %

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class StockHolding:
    """基金持仓股票"""
    code: str             # 股票代码
    name: str             # 股票名称
    ratio: float          # 占净值比例 %
    pe: Optional[float] = None   # 市盈率
    pb: Optional[float] = None   # 市净率

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Holdings:
    """基金持仓（季报）"""
    quarter: str          # "2025Q4"
    publish_date: str     # 季报公布日期 "2026-01-21"
    top_stocks: List[StockHolding] = field(default_factory=list)
    asset_allocation: dict = field(default_factory=dict)  # 资产配置比例

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class FeeStructure:
    """基金费率结构"""
    manage_fee: float                # 管理费 %/年
    custody_fee: float               # 托管费 %/年
    purchase_fee_rates: List[dict] = field(default_factory=list)  # [{min_amount, rate}]
    redeem_fee_rates: List[dict] = field(default_factory=list)    # [{min_days, max_days, rate}]
    service_fee: Optional[float] = None  # 销售服务费 %/年（C类）

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def total_annual_fee(self) -> float:
        """年化总费率（管理+托管+销售服务）"""
        return self.manage_fee + self.custody_fee + (self.service_fee or 0)


@dataclass
class ManagerInfo:
    """基金经理信息"""
    name: str             # 姓名
    start_date: str       # 任职起始日
    tenure_return: Optional[float] = None  # 任职回报 %
    tenure_years: Optional[float] = None   # 任职年限
    managed_scale: Optional[float] = None  # 管理规模 亿
    funds_count: Optional[int] = None      # 管理基金数
    avg_return: Optional[float] = None     # 年均回报 %

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class FundProfile:
    """基金基本信息"""
    code: str                # 基金代码
    name: str                # 基金名称
    fund_type: str           # 基金类型（股票型/混合型/债券型/指数型/QDII）
    establish_date: str      # 成立日期
    scale: Optional[float] = None   # 规模 亿
    manager: Optional[ManagerInfo] = None  # 基金经理
    company: Optional[str] = None     # 基金公司

    def to_dict(self) -> dict:
        return asdict(self)
