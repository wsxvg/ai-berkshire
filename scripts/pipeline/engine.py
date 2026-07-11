"""Pipeline 引擎 — 插件式任务注册与执行

用法:
    from scripts.pipeline.engine import PipelineEngine

    @PipelineEngine.register
    class MyTask(PipelineTask):
        name = "my_task"

    PipelineEngine.run(tasks=["auth", "scoring"])
    PipelineEngine.run()  # 执行全部
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Type
import logging

logger = logging.getLogger(__name__)


class PipelineTask(ABC):
    """Pipeline 任务基类"""
    name: str = ""
    description: str = ""

    @abstractmethod
    def execute(self, context: dict, offline: bool = False) -> dict:
        """执行任务
        Args:
            context: 共享上下文（前序任务输出可写入）
            offline: True=跳过API调用，使用缓存
        Returns:
            dict 任务输出，会合并到 context
        """


class PipelineEngine:
    """Pipeline 引擎"""

    _tasks: Dict[str, PipelineTask] = {}

    @classmethod
    def register(cls, task_cls: Type[PipelineTask]) -> Type[PipelineTask]:
        """注册 task（装饰器用法）

        @PipelineEngine.register
        class MyTask(PipelineTask):
            name = "my_task"
        """
        instance = task_cls()
        cls._tasks[instance.name] = instance
        logger.info("Pipeline task registered: %s", instance.name)
        return task_cls

    @classmethod
    def run(cls, tasks: Optional[List[str]] = None,
            offline: bool = False, context: Optional[dict] = None) -> dict:
        """按顺序执行 tasks

        Args:
            tasks: task 名称列表，None=执行所有已注册 task
            offline: 离线模式（跳过API调用）
            context: 初始上下文
        Returns:
            dict 合并后的上下文
        """
        if context is None:
            context = {}

        selected = tasks if tasks is not None else list(cls._tasks.keys())

        for name in selected:
            task = cls._tasks.get(name)
            if task is None:
                logger.warning("Pipeline task not found: %s", name)
                continue

            logger.info("Pipeline running: %s (offline=%s)", name, offline)
            try:
                result = task.execute(context, offline=offline)
                if isinstance(result, dict):
                    context[name] = result
                logger.info("Pipeline completed: %s", name)
            except Exception as e:
                logger.error("Pipeline task failed: %s - %s", name, e)
                context[name] = {"error": str(e)}
                # 不中断后续 task，记录错误继续执行

        return context

    @classmethod
    def get_task(cls, name: str) -> Optional[PipelineTask]:
        return cls._tasks.get(name)

    @classmethod
    def list_tasks(cls) -> List[str]:
        return list(cls._tasks.keys())