"""Pipeline tasks — 自动发现注册"""
from pathlib import Path
import importlib
import logging

logger = logging.getLogger(__name__)

# 自动导入 tasks/ 下所有 task_*.py 文件
_tasks_dir = Path(__file__).parent
for f in sorted(_tasks_dir.glob("task_*.py")):
    module_name = f"scripts.pipeline.tasks.{f.stem}"
    try:
        importlib.import_module(module_name)
        logger.debug("Auto-loaded pipeline task: %s", module_name)
    except Exception as e:
        logger.warning("Failed to load pipeline task %s: %s", module_name, e)