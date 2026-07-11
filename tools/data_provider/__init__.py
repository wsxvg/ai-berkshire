"""tools/data_provider — 基金数据提供者层

提供标准化基金数据接口和多数据源切换能力。

用法:
    from tools.data_provider import get_data
    nav = get_data("get_nav", "006105")

    from tools.data_provider.factory import FundDataSourceFactory
    provider = FundDataSourceFactory.get("jd")
    nav = provider.get_nav("006105")
"""
from .models import NavPoint, Holdings, FeeStructure, ManagerInfo, FundProfile, StockHolding
from .base import IFundDataProvider
from .factory import FundDataSourceFactory


def get_data(method: str, fund_code: str, *args, **kwargs):
    """快捷获取基金数据（故障切换自动）

    Args:
        method: 方法名 "get_nav"/"get_holdings"/"get_fee"/"get_manager"/"get_profile"
        fund_code: 基金代码
    Returns:
        对应模型的实例，所有provider失效时返回None
    """
    provider = FundDataSourceFactory.get(fallback=True)
    if provider is None:
        return None
    func = getattr(provider, method, None)
    if func is None:
        return None
    return func(fund_code, *args, **kwargs)