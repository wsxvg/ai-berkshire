"""交易记录采集 task"""
from __future__ import annotations
from scripts.pipeline.engine import PipelineEngine, PipelineTask
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    from tools.logutil import get_logger
except Exception:
    from logutil import get_logger

_logger = get_logger("pipeline.trading")


@PipelineEngine.register
class TaskTrading(PipelineTask):
    name = "trading"
    description = "采集大佬交易记录"
    depends_on = ["auth"]

    def execute(self, context: dict, offline: bool = False) -> dict:
        cookies = context.get("auth", {}).get("cookies")
        cookie_ok = context.get("auth", {}).get("cookie_ok", False)

        if not cookie_ok or not cookies:
            _logger.info("Trading: skipped (no cookie)")
            return {"records": [], "signals": {}}

        from tools.jd_finance_api import FOLLOWED_USERS, get_trading_records

        all_records = []
        with ThreadPoolExecutor(max_workers=10) as pool:
            futures = {pool.submit(get_trading_records, target_uid=uid, cookies=cookies, today_only=True): name
                       for uid, name in FOLLOWED_USERS.items()}
            for fut in as_completed(futures):
                name = futures[fut]
                try:
                    result = fut.result()
                    records = result.get("records", [])
                    if records:
                        all_records.extend(records)
                        _logger.debug(f"[{name}] {len(records)} records")
                except Exception as e:
                    pass

        # 汇总信号
        signals = {}
        for r in all_records:
            fund_name = r.get("fundName", "")
            action = r.get("actionName", "")
            if fund_name not in signals:
                signals[fund_name] = {"buy_count": 0, "sell_count": 0}
            if "买入" in action:
                signals[fund_name]["buy_count"] += 1
            elif "卖出" in action:
                signals[fund_name]["sell_count"] += 1

        _logger.info(f"Trading: {len(all_records)} records, {len(signals)} funds with signals")
        return {"records": all_records, "signals": signals}