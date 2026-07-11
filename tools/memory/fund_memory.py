"""基金长期记忆 — 参考 tradingagents TradingMemoryLog 两阶段持久化

每个基金的分析历史、信号历史、经理变更记录以 JSON 文件持久化。

结构:
  data/memory/
  ├── analysis_{fund_code}.json     # 分析历史
  ├── signals_{fund_code}.json      # 信号历史
  ├── manager_changes_{fund_code}.json  # 经理变更
  └── insights.json                 # 跨基金 insights
"""
from __future__ import annotations
import json
import os
from pathlib import Path
from datetime import datetime
from typing import List, Optional, Dict, Any

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "memory"


class FundMemoryLog:
    """基金记忆系统 — 两阶段持久化（追加写 + 原子更新）"""

    def __init__(self):
        DATA_DIR.mkdir(parents=True, exist_ok=True)

    # ── 分析历史 ──

    def store_analysis(self, fund_code: str, score: dict,
                       decision: dict, explanation: str = "") -> None:
        """保存分析记录（原子写入）"""
        records = self._load(f"analysis_{fund_code}.json")
        records.append({
            "timestamp": datetime.now().isoformat(),
            "score": score,
            "decision": decision,
            "explanation": explanation,
        })
        # 保留最近 50 条
        self._save(f"analysis_{fund_code}.json", records[-50:])

    def get_history(self, fund_code: str, n: int = 5) -> List[dict]:
        """获取最近 N 条分析记录"""
        records = self._load(f"analysis_{fund_code}.json")
        return records[-n:]

    # ── 信号历史 ──

    def store_signal(self, fund_code: str, signal: dict) -> None:
        """保存决策信号"""
        signals = self._load(f"signals_{fund_code}.json")
        signals.append({**signal, "timestamp": datetime.now().isoformat()})
        self._save(f"signals_{fund_code}.json", signals[-100:])

    def get_signal_history(self, fund_code: str) -> List[dict]:
        """获取历史买卖信号"""
        return self._load(f"signals_{fund_code}.json")

    # ── 经理变更 ──

    def record_manager_change(self, fund_code: str,
                               old_manager: str, new_manager: str) -> None:
        """记录基金经理变更"""
        changes = self._load(f"manager_changes_{fund_code}.json")
        changes.append({
            "timestamp": datetime.now().isoformat(),
            "old_manager": old_manager,
            "new_manager": new_manager,
        })
        self._save(f"manager_changes_{fund_code}.json", changes)

    def get_manager_changes(self, fund_code: str) -> List[dict]:
        return self._load(f"manager_changes_{fund_code}.json")

    # ── Insights ──

    def store_insight(self, source: str, content: str) -> None:
        """存储进化循环中 AI 提炼的投资 insight"""
        insights = self._load("insights.json")
        insights.append({
            "timestamp": datetime.now().isoformat(),
            "source": source,
            "content": content,
        })
        self._save("insights.json", insights[-200:])  # 保留最近 200 条

    def get_insights(self, limit: int = 10) -> List[dict]:
        insights = self._load("insights.json")
        return insights[-limit:]

    # ── 内部 ──

    @staticmethod
    def _load(name: str) -> list:
        path = DATA_DIR / name
        if not path.exists():
            return []
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, Exception):
            return []

    @staticmethod
    def _save(name: str, data: list) -> None:
        path = DATA_DIR / name
        # 原子写入：tmp + os.replace
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(str(tmp), str(path))