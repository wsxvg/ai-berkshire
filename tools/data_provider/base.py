"""基金数据提供者接口

所有数据源（京东金融/天天基金/AkShare等）必须实现此接口。
业务层只依赖此接口，不直接调用具体数据源。
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import List, Optional
from .models import NavPoint, Holdings, FeeStructure, ManagerInfo, FundProfile


class IFundDataProvider(ABC):
    """基金数据提供者统一接口"""

    @abstractmethod
    def get_nav(self, code: str, start: Optional[str] = None,
                end: Optional[str] = None) -> List[NavPoint]:
        """获取基金净值历史
        Args:
            code: 基金代码
            start: 开始日期 "2026-01-01"，None=全部
            end: 截止日期 "2026-06-30"，None=至今
        Returns:
            List[NavPoint] 按日期升序排列
        """

    @abstractmethod
    def get_holdings(self, code: str, quarter: Optional[str] = None) -> Holdings:
        """获取基金季报持仓
        Args:
            code: 基金代码
            quarter: 季度 "2025Q4"，None=最新
        Returns:
            Holdings 包含持仓股票和资产配置
        """

    @abstractmethod
    def get_fee(self, code: str) -> FeeStructure:
        """获取基金费率结构
        Args:
            code: 基金代码
        Returns:
            FeeStructure 管理费/托管费/申购赎回费
        """

    @abstractmethod
    def get_manager(self, code: str) -> ManagerInfo:
        """获取基金经理信息
        Args:
            code: 基金代码
        Returns:
            ManagerInfo 经理名称/任期/回报
        """

    @abstractmethod
    def get_profile(self, code: str) -> FundProfile:
        """获取基金基本信息
        Args:
            code: 基金代码
        Returns:
            FundProfile 基金名称/类型/规模/成立日
        """

    @abstractmethod
    def get_nav_history(self, code: str) -> List[NavPoint]:
        """获取完整净值历史（纯用于回测，含全量数据）
        Args:
            code: 基金代码
        Returns:
            List[NavPoint] 全量历史净值
        """

    @property
    @abstractmethod
    def name(self) -> str:
        """数据源名称: "jd"/"akshare"/"morningstar" """
