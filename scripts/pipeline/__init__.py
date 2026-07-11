"""scripts/pipeline — 插件式 Pipeline 系统

用法:
    from scripts.pipeline import PipelineEngine, run_pipeline

    # 注册 task (通过 @PipelineEngine.register 装饰器自动完成)
    # 导入 tasks 目录触发自动注册

    # 运行全部 task
    result = run_pipeline()

    # 运行指定 task
    result = run_pipeline(tasks=["auth", "scoring"])
"""
from .engine import PipelineEngine, PipelineTask
from . import tasks  # noqa: F401 — 触发 task 自动注册


def run_pipeline(tasks=None, offline=False, context=None):
    """快捷运行 Pipeline

    Args:
        tasks: task 名称列表，None=全部
        offline: 跳过API调用
        context: 初始上下文
    Returns:
        合并后的 context
    """
    return PipelineEngine.run(tasks=tasks, offline=offline, context=context)