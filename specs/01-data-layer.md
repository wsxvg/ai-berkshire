# Spec 01: 数据层重构

## 目标
把 jd_finance_api.py 的 75K 零散函数包装成标准化接口，新增备用数据源。

## 接口定义

```python
# tools/data_provider/models.py
@dataclass
class NavPoint:
    date: str          # "2026-01-15"
    nav: float         # 单位净值
    accumulated_nav: float  # 累计净值
    daily_return: float     # 日收益率 %

@dataclass
class StockHolding:
    code: str; name: str; ratio: float; pe: float; pb: float

@dataclass
class Holdings:
    quarter: str       # "2025Q4"
    publish_date: str  # 季报公布日期
    top_stocks: List[StockHolding]

@dataclass
class FeeStructure:
    manage_fee: float; custody_fee: float
    purchase_fee_rates: List[dict]  # [{min_amount, rate}]
    redeem_fee_rates: List[dict]    # [{min_days, max_days, rate}]
    service_fee: float

@dataclass
class ManagerInfo:
    name: str; start_date: str; tenure_return: float
    tenure_years: float; managed_scale: float; funds_count: int

@dataclass
class FundProfile:
    code: str; name: str; fund_type: str
    establish_date: str; scale: float; manager: ManagerInfo
```

```python
# tools/data_provider/base.py
class IFundDataProvider(ABC):
    @abstractmethod
    def get_nav(self, code: str, start: str = None, end: str = None) -> List[NavPoint]
    @abstractmethod
    def get_holdings(self, code: str, quarter: str = None) -> Holdings
    @abstractmethod
    def get_fee(self, code: str) -> FeeStructure
    @abstractmethod
    def get_manager(self, code: str) -> ManagerInfo
    @abstractmethod
    def get_profile(self, code: str) -> FundProfile
    @abstractmethod
    def get_nav_history(self, code: str) -> List[NavPoint]
```

```python
# tools/data_provider/factory.py
class FundDataSourceFactory:
    @classmethod
    def register(cls, name: str, provider_cls: type[IFundDataProvider])
    @classmethod
    def get(cls, name: str = "jd") -> IFundDataProvider
    # 故障切换: get("jd") 失败 → get("akshare") 自动降级
```

## 实现列表

| 文件 | 说明 |
|------|------|
| models.py | 6个dataclass |
| base.py | IFundDataProvider抽象接口 |
| jd_finance_provider.py | 调用jd_finance_api，输出标准化model |
| akshare_provider.py | 天天基金/AkShare来源（备用） |
| factory.py | 注册+懒加载+故障切换 |

## 测试
- mock jd_finance_api 后验证 get_nav 返回 NavPoint 类型
- 切换 jd→akshare 验证同一基金code返回相同字段结构

## 参考项目可复用模式
| 来源 | 模式 | 复用方式 |
|------|------|---------|
| daily-stock-analysis | BaseFetcher 数据抽象 | _fetch_raw_data→_normalize_data→_calculate_indicators 模板方法 |
| quantdinger | DataSourceFactory | 类方法工厂+别名归一化+日志降噪+惰性加载 |
| quantdinger | Circuit Breaker | CLOSED→OPEN→HALF_OPEN 熔断器状态机 |
| quantdinger | Rate Limiter | 指数退避重试+User-Agent轮换 |
| AI-Trader-main | Cache 降级 | Redis 不可用时静默跳过，不阻塞 |
| AI-Trader-main | Config 管理 | 环境变量+dotenv+类型安全转换+缓存 |