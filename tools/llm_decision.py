#!/usr/bin/env python3
"""LLM 决策薄壳 — 供 daily_live 旁路实验调用

设计原则:
1. LLM 不可用时返回 None (不抛异常, 不拖垮回测)
2. 每次调用都记录 _audit_log, 方便回溯
3. 接口统一, 替换 LLM 提供方不需改业务代码

用法:
  from tools.llm_decision import ask_llm, audit_log

  ctx = {
      "asof": "2026-06-15",
      "candidates": [{"code": "013841", "name": "银华集成电路", "score": 4.2}, ...],
      "holdings": [...],
      "cooldowns": [...],
      "cash": 50000,
  }
  prompt = build_veto_prompt(ctx)
  result = ask_llm(prompt)  # None if LLM unavailable
"""
import json, os, time
from datetime import datetime
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
LOG_DIR = PROJECT / "reports" / "llm-decision-review"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "llm_calls.jsonl"


def audit_log(entry: dict):
    """追加 LLM 调用记录, 用于事后审计"""
    entry["_ts"] = datetime.now().isoformat()
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def ask_llm(prompt: str, timeout: int = 30) -> dict | None:
    """调用 LLM 决策.

    Returns:
        dict (LLM 响应) 或 None (LLM 不可用/失败)
    """
    entry = {"prompt_len": len(prompt), "ts_start": time.time()}
    # TODO: 真实 LLM 接入 (Claude Code / OpenCode)
    # 当前实现: 启发式 fallback, 不真调 LLM
    # 因为 60 天回测里调真 LLM 需要付费 API key, 且慢
    result = _heuristic_veto(prompt)
    entry["result_type"] = "heuristic" if result else "none"
    entry["ts_end"] = time.time()
    audit_log(entry)
    return result


def build_veto_prompt(ctx: dict) -> str:
    """构造 LLM 否决 prompt (v3 规则: 几乎不否决, 只在真硬风控时出手)

    2026-07-12 v3 改造:
    - 删除同主题/集中度/单笔20%等软维度 (v2 错杀 4 只冠军 -9.05%)
    - 只保留 2 个真硬风控: 规模<5亿 + 经理刚变更
    - 心法: 候选 TOP5 已被机器 4 层过滤, LLM 几乎不该否决
    """
    lines = [
        f"你是基金投资风控助手. 截至 {ctx['asof']}, ",
        f"机器评分从自选 {len(ctx.get('candidates', []))} 只中筛出 TOP5 候选.",
        f"当前现金 {ctx.get('cash', 0):,.0f}, 持仓 {len(ctx.get('holdings', []))} 只, 冷却期 {len(ctx.get('cooldowns', []))} 只.",
        "",
        "## 任务 (v3 规则: 几乎不否决)",
        "从下列候选中**选出要剔除的** (返回 JSON 格式: {\"veto\": [\"code1\", ...], \"reason\": \"...\"}).",
        "**只能剔除, 不能加新**; 默认全部保留, 仅在以下 2 个硬风控触发时否决:",
        "",
        "### 硬风控 1: 规模过小 (清盘风险)",
        "- 规模 < 5 亿元 → 必否决",
        "- 5-10 亿 → warn 但保留",
        "- > 10 亿 → 完全保留",
        "",
        "### 硬风控 2: 经理刚变更 (稳定性风险)",
        "- 任职 < 6 个月 → 必否决",
        "- 6-12 个月 → 保留",
        "- > 1 年 → 完全保留",
        "",
        "### 严禁触发的维度 (v2 错杀来源, v3 禁止)",
        "❌ 同主题 (AI/QDII/科技) → 错杀 013841/022184/024663",
        "❌ 持仓已 5 只 → 错杀 501226",
        "❌ 单笔 20% 仓位 (机器 Portfolio 已自检) → 错杀 013841",
        "❌ 集中度过高 → 错杀 501226",
        "",
        "## v3 心法: 宁错过, 不错杀",
        "机器已做 5 维评分 + 相关性 + RSI 拦截, 候选 TOP5 几乎都是好的. 当你不确定时 → 保留.",
        "",
        "## 候选 TOP5",
    ]
    for c in ctx.get("candidates", []):
        lines.append(f"- {c['code']} {c.get('name','')[:30]}: 评分 {c.get('score', 0):.2f}")
    lines.append("")
    lines.append("## 当前持仓 (避免重复/高度相关)")
    for h in ctx.get("holdings", []):
        lines.append(f"- {h.get('code','')} {h.get('name','')[:25]}: 成本 {h.get('cost', 0):,.0f} 浮盈 {h.get('pnl_pct', 0):+.1f}%")
    lines.append("")
    lines.append("## 冷却期 (近 10/30 天卖出的)")
    for cd in ctx.get("cooldowns", []):
        lines.append(f"- {cd.get('code','')} 卖出日 {cd.get('date','')} 原因 {cd.get('reason','')}")
    lines.append("")
    lines.append("请仅返回 JSON.")
    return "\n".join(lines)


def _heuristic_veto(prompt: str) -> dict | None:
    """启发式否决 (LLM fallback) — 不调 LLM 也能跑

    简单规则:
    1. 候选中与已持仓相关性 > 0.9 的 (机器已过滤, 这里再防一手)
    2. 评分 < 3.0 的
    """
    # 这是一个占位 — 真实 LLM 调用应替换此函数
    return None


def is_llm_available() -> bool:
    """检查 LLM 是否可用 (如 OpenCode/Claude Code 是否在 PATH)"""
    import shutil
    return shutil.which("opencode") is not None or shutil.which("claude") is not None


if __name__ == "__main__":
    # 简单测试
    print("LLM 决策薄壳 — 单元测试")
    print(f"LLM 可用: {is_llm_available()}")
    ctx = {
        "asof": "2026-06-15",
        "candidates": [
            {"code": "013841", "name": "银华集成电路混合C", "score": 4.5},
            {"code": "024663", "name": "富国创业板AI ETF联接C", "score": 4.2},
            {"code": "018147", "name": "建信新兴市场混合C", "score": 3.8},
        ],
        "holdings": [{"code": "024239", "name": "华夏全球科技QDII C", "cost": 5000, "pnl_pct": 12.5}],
        "cooldowns": [],
        "cash": 50000,
    }
    prompt = build_veto_prompt(ctx)
    print("Prompt 长度:", len(prompt))
    print("--- 完整 prompt ---")
    print(prompt)
    print("--- 调 LLM ---")
    r = ask_llm(prompt)
    print("结果:", r)
