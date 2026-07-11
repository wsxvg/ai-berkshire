"""基金数据源工厂

注册+懒加载+故障切换模式。
参考 quantdinger DataSourceFactory 设计。
"""
from __future__ import annotations
from typing import Dict, Type, Optional
import logging

from .base import IFundDataProvider

logger = logging.getLogger(__name__)


class FundDataSourceFactory:
    """基金数据源工厂

    用法:
        FundDataSourceFactory.register("jd", JDFinanceProvider)
        provider = FundDataSourceFactory.get("jd")          # 主数据源
        provider = FundDataSourceFactory.get(fallback=True) # 自动故障切换
    """

    _providers: Dict[str, IFundDataProvider] = {}
    _provider_classes: Dict[str, Type[IFundDataProvider]] = {}
    _fallback_chain: list = ["jd", "akshare"]  # 故障切换链

    @classmethod
    def register(cls, name: str, provider_cls: Type[IFundDataProvider]) -> None:
        """注册数据源实现类（懒加载，首次 get 时才实例化）"""
        cls._provider_classes[name] = provider_cls
        if name not in cls._fallback_chain:
            cls._fallback_chain.append(name)
        logger.info("DataProvider registered: %s -> %s", name, provider_cls.__name__)

    @classmethod
    def get(cls, name: str = "jd", fallback: bool = False) -> Optional[IFundDataProvider]:
        """获取数据源实例

        Args:
            name: 数据源名称，默认 "jd"
            fallback: True 时自动故障切换
        Returns:
            IFundDataProvider 实例，或 None
        """
        if not cls._provider_classes:
            cls._auto_register()
            return cls.get(name, fallback=fallback)

        # 尝试指定数据源
        if not fallback:
            return cls._get_or_create(name)

        # 故障切换模式：按 fallback 链尝试
        for fallback_name in cls._fallback_chain:
            try:
                provider = cls._get_or_create(fallback_name)
                if provider is not None:
                    return provider
            except Exception as e:
                logger.warning("DataProvider fallback %s failed: %s", fallback_name, e)
                continue

        logger.error("All data providers failed")
        return None

    @classmethod
    def _get_or_create(cls, name: str) -> Optional[IFundDataProvider]:
        """获取或创建数据源（懒加载）"""
        if name in cls._providers:
            return cls._providers[name]

        provider_cls = cls._provider_classes.get(name)
        if provider_cls is None:
            logger.warning("DataProvider not registered: %s", name)
            return None

        try:
            provider = provider_cls()
            cls._providers[name] = provider
            logger.info("DataProvider created: %s", name)
            return provider
        except Exception as e:
            logger.error("Failed to create DataProvider %s: %s", name, e)
            return None

    @classmethod
    def _auto_register(cls) -> None:
        """首次调用时自动注册默认数据源"""
        try:
            from .jd_finance_provider import JDFinanceProvider
            cls.register("jd", JDFinanceProvider)
        except ImportError as e:
            logger.warning("JDFinanceProvider not available: %s", e)

    @classmethod
    def get_available_sources(cls) -> list:
        """获取已注册的所有数据源名称"""
        return list(cls._provider_classes.keys())

    @classmethod
    def clear_cache(cls) -> None:
        """清除已实例化的 provider（测试用）"""
        cls._providers.clear()
