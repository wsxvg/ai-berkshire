"""事件总线 — 基于 blinker 的模块间解耦

用法:
    from tools.event_bus import events

    @events.nav_updated.connect
    def on_nav_updated(sender, **kwargs):
        print(f"NAV更新: {kwargs.get('fund_code')} = {kwargs.get('nav')}")

    # 在生产代码中触发:
    from tools.event_bus import events
    events.nav_updated.send("task_holdings", fund_code="006105", nav=1.234)
"""
from blinker import signal

# ── 事件定义 ──
nav_updated = signal('nav_updated')
"""基金净值更新 → Risk检查 / Memory存储"""
holdings_updated = signal('holdings_updated')
"""大佬持仓更新 → Scoring重算 / Rules重算"""
signal_created = signal('signal_created')
"""新决策信号 → Feishu推送 / 后续task触发"""
risk_alert = signal('risk_alert')
"""风控预警 → DecisionEngine重评 / Feishu紧急通知"""
quarterly_report = signal('quarterly_report')
"""季报发布 → RAG索引 / Analyzer解读"""


class Events:
    """命名空间，方便 IDE 自动补全"""
    nav_updated = nav_updated
    holdings_updated = holdings_updated
    signal_created = signal_created
    risk_alert = risk_alert
    quarterly_report = quarterly_report


events = Events()