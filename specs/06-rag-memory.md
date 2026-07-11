# Spec 06: RAG + Memory

## RAG（向量库）

用 chromadb + sentence-transformers，不需要 GPU。

```bash
pip install chromadb sentence-transformers
```

### 索引内容
1. 基金季报（持仓数据 + 经理投资策略和运作分析章节）
2. 基金合同/招募说明书（费率条款、投资范围）
3. 基金经理访谈/观点
4. 晨星/招商等第三方评级报告
5. 系统自己的历史分析报告

### 接口

```python
class FundVectorStore:
    def index_quarterly(self, fund_code: str, report_text: str) -> None
    def index_announcement(self, fund_code: str, title: str, content: str) -> None
    def query(self, fund_code: str, question: str, top_k: int = 3) -> List[str]
    # query 供 FundAnalyzer 用：分析时从RAG拉取相关上下文
```

## Memory（长期记忆）

参考 tradingagents 的 TradingMemoryLog，两阶段持久化。

```python
class FundMemoryLog:
    def store_analysis(self, fund_code: str, score: FundScore,
                       decision: DecisionResult, explanation: str) -> None

    def get_history(self, fund_code: str, n: int = 5) -> List[dict]:
        """获取历史分析记录"""

    def get_manager_changes(self, fund_code: str) -> List[dict]:
        """基金经理变更记录"""

    def get_signal_history(self, fund_code: str) -> List[dict]:
        """历史买卖信号"""

    def store_insight(self, source: str, content: str) -> None:
        """存储进化循环中AI提炼的投资insight"""

## 参考项目可复用模式
| 来源 | 模式 | 复用方式 |
|------|------|---------|
| tradingagents | TradingMemoryLog | 追加写+原子更新(tmp+os.replace)+容量控制+延迟闭环 |
| tradingagents | 延迟闭环 | Phase A写入pending → Phase B实际收益产生后原子更新+LLM反思 |
| tradingagents | get_past_context | n_same=5/n_cross=3 提取同标的+跨标的的历史经验 |
| tradingagents | 报告树生成 | 结构化Markdown文件树，存入RAG供参考 |
```