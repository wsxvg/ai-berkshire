# Spec 02: Pipeline 插件化

## 目标
把 auto-pipeline.py(107K) 的线性流程拆成插件式，新增模块只需新建 task 文件。

## PipelineEngine

```python
# scripts/pipeline/engine.py

class PipelineTask(ABC):
    name: str          # 唯一标识
    depends_on: List[str]  # 依赖的task名
    @abstractmethod
    def execute(self, context: dict, offline: bool) -> dict

class PipelineEngine:
    _tasks: Dict[str, PipelineTask] = {}

    @classmethod
    def register(cls, task_cls):
        """@register 装饰器"""
        instance = task_cls()
        cls._tasks[instance.name] = instance

    @classmethod
    def run(cls, tasks: List[str] = None, offline: bool = False, context: dict = None):
        """按依赖顺序执行。tasks=None 执行全部"""
```

## Task 列表

| Task | 来源 | 说明 |
|------|------|------|
| task_auth | auto-pipeline Step0 | Cookie认证 |
| task_holdings | Step1 | 大佬持仓采集 |
| task_trading | Step2 | 交易记录 |
| task_news | Step2b | 每日新闻 |
| task_ranking | Step2c | 排行榜+交叉验证 |
| task_scoring | 调用fund_scorer | 基金评分 |
| task_rules | 调用fund_rules | 规则引擎 |
| task_ai_analysis | 新增 | LLM分析评分结果 |
| task_report | 调用generate_report | 报告生成 |
| task_feishu | 调用feishu_push | 飞书推送 |

## 从 auto-pipeline 提取 task 的规则
1. 每个 task 独立文件，只提取该步骤的逻辑
2. 不修改 auto-pipeline.py 原有代码（保留原始入口）
3. 每个 task 支持 offline 模式（跳过 API 调用，用缓存数据）

## 参考项目可复用模式
| 来源 | 模式 | 复用方式 |
|------|------|---------|
| daily-stock-analysis | Pipeline 双架构 | 传统流水线→基金净值处理；多Agent→基金分析 |
| AI-Trader-main | Worker 注册表 | BACKGROUND_TASK_REGISTRY 按 env 控制哪些任务启动 |
| AI-Trader-main | Worker 单例锁 | Redis锁+文件锁双重防止重复启动 |
| AI-Trader-main | 优雅关闭 | stop_event.wait() + task.cancel() |