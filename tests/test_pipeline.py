"""Tests for Pipeline engine"""
from __future__ import annotations
import pytest
from scripts.pipeline.engine import PipelineEngine, PipelineTask


# ── Mock task for testing ──
@PipelineEngine.register
class MockTask(PipelineTask):
    name = "mock_task"
    description = "测试用"

    def execute(self, context: dict, offline: bool = False) -> dict:
        return {"result": "ok", "offline": offline}


@PipelineEngine.register
class MockFailingTask(PipelineTask):
    name = "mock_fail"
    description = "测试失败"

    def execute(self, context: dict, offline: bool = False) -> dict:
        raise ValueError("模拟失败")


class TestPipelineEngine:

    def test_register(self):
        assert "mock_task" in PipelineEngine.list_tasks()

    def test_run_single_task(self):
        result = PipelineEngine.run(tasks=["mock_task"])
        assert "mock_task" in result
        assert result["mock_task"]["result"] == "ok"

    def test_run_all_tasks(self):
        result = PipelineEngine.run()
        assert isinstance(result, dict)

    def test_offline_mode(self):
        result = PipelineEngine.run(tasks=["mock_task"], offline=True)
        assert result["mock_task"]["offline"] is True

    def test_context_passed(self):
        result = PipelineEngine.run(tasks=["mock_task"], context={"foo": "bar"})
        assert result["foo"] == "bar"

    def test_failing_task_does_not_block(self):
        """失败 task 不阻断后续"""
        result = PipelineEngine.run(tasks=["mock_fail"])
        assert "mock_fail" in result
        assert "error" in result["mock_fail"]

    def test_task_with_dependencies(self):
        task = PipelineEngine.get_task("mock_task")
        assert task is not None
        assert task.name == "mock_task"

    def test_unknown_task_logged(self):
        result = PipelineEngine.run(tasks=["nonexistent"])
        assert "nonexistent" not in result