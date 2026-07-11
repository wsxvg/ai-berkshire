"""基金向量知识库（RAG）

基于 chromadb 存储和检索基金公告/季报/经理访谈等文本信息。

用法:
    store = FundVectorStore()
    store.index_quarterly("006105", "2025Q4", "季报文本...")
    results = store.query("006105", "最近持仓变化")
"""
from __future__ import annotations
from pathlib import Path
from typing import List, Optional
import logging

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "rag"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# ── 尝试导入 chromadb ──
try:
    import chromadb
    from chromadb.config import Settings
    _HAS_CHROMADB = True
except ImportError:
    _HAS_CHROMADB = False
    logger.warning("chromadb not installed. RAG will use file-based fallback.")


class FundVectorStore:
    """基金向量知识库"""

    def __init__(self, collection_name: str = "fund_knowledge"):
        self.collection_name = collection_name
        self._collection = None

        if _HAS_CHROMADB:
            try:
                client = chromadb.PersistentClient(
                    path=str(DATA_DIR),
                    settings=Settings(anonymized_telemetry=False),
                )
                self._collection = client.get_or_create_collection(
                    name=collection_name,
                    metadata={"hnsw:space": "cosine"},
                )
                logger.info("RAG: chromadb initialized at %s", DATA_DIR)
            except Exception as e:
                logger.warning("RAG: chromadb init failed: %s. Using fallback.", e)

    def index_quarterly(self, fund_code: str, quarter: str, report_text: str) -> None:
        """索引基金季报"""
        doc_id = f"{fund_code}_Q_{quarter}"
        metadata = {"fund_code": fund_code, "type": "quarterly", "quarter": quarter}

        if self._collection is not None:
            self._collection.add(
                documents=[report_text],
                metadatas=[metadata],
                ids=[doc_id],
            )
        else:
            self._fallback_write(doc_id, metadata, report_text)

    def index_announcement(self, fund_code: str, title: str, content: str) -> None:
        """索引基金公告"""
        doc_id = f"{fund_code}_A_{hash(content) % 100000:05d}"
        metadata = {"fund_code": fund_code, "type": "announcement", "title": title}

        if self._collection is not None:
            self._collection.add(
                documents=[content],
                metadatas=[metadata],
                ids=[doc_id],
            )
        else:
            self._fallback_write(doc_id, metadata, content)

    def query(self, fund_code: str, question: str, top_k: int = 3) -> List[dict]:
        """查询基金相关知识"""
        if self._collection is not None:
            try:
                results = self._collection.query(
                    query_texts=[question],
                    n_results=min(top_k, 10),
                    where={"fund_code": fund_code},
                )
                docs = []
                for i, doc in enumerate(results.get("documents", [[]])[0]):
                    docs.append({
                        "content": doc,
                        "metadata": results.get("metadatas", [[]])[0][i] if results.get("metadatas") else {},
                    })
                return docs
            except Exception as e:
                logger.warning("RAG query failed: %s", e)

        return self._fallback_query(fund_code, top_k)

    # ── File-based fallback ──

    def _fallback_write(self, doc_id: str, metadata: dict, content: str) -> None:
        """没有 chromadb 时用 JSON 文件存储"""
        path = DATA_DIR / "docs" / f"{doc_id}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        import json
        path.write_text(json.dumps({
            "id": doc_id,
            "metadata": metadata,
            "content": content[:2000],  # 限制长度
        }, ensure_ascii=False), encoding="utf-8")

    def _fallback_query(self, fund_code: str, top_k: int) -> list:
        """简单关键词匹配（免 chromadb 时的替代）"""
        import json
        docs_dir = DATA_DIR / "docs"
        if not docs_dir.exists():
            return []

        results = []
        for f in sorted(docs_dir.glob(f"{fund_code}_*.json")):
            try:
                doc = json.loads(f.read_text("utf-8"))
                if doc.get("metadata", {}).get("fund_code") == fund_code:
                    results.append(doc)
            except Exception:
                continue

        return results[-top_k:]