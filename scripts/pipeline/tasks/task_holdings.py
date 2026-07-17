"""大佬持仓采集 task"""
from __future__ import annotations
from scripts.pipeline.engine import PipelineEngine, PipelineTask

try:
    from tools.logutil import get_logger
except Exception:
    from logutil import get_logger

_logger = get_logger("pipeline.holdings")


@PipelineEngine.register
class TaskHoldings(PipelineTask):
    name = "holdings"
    description = "采集大佬持仓数据"
    depends_on = ["auth"]

    def execute(self, context: dict, offline: bool = False) -> dict:
        cookies = context.get("auth", {}).get("cookies")
        cookie_ok = context.get("auth", {}).get("cookie_ok", False)

        if not cookie_ok or not cookies:
            _logger.info("Holdings: skipped (no cookie)")
            return {"holdings": {}, "holdings_ok": False, "holdings_diff": {}}

        from tools.jd_finance_api import FOLLOWED_USERS, get_user_holdings
        from concurrent.futures import ThreadPoolExecutor, as_completed

        # 提取所有 tracked users
        all_tracked = dict(FOLLOWED_USERS)

        # 获取持仓
        current_holdings = {}
        with ThreadPoolExecutor(max_workers=10) as pool:
            futures = {pool.submit(get_user_holdings, target_uid=uid, cookies=cookies): name
                       for uid, name in all_tracked.items()}
            for fut in as_completed(futures):
                name = futures[fut]
                try:
                    result = fut.result()
                    items = result.get("holdings", [])
                    if items:
                        current_holdings[name] = items
                except Exception as e:
                    _logger.warning(f"[{name}] failed: {e}")

        # 计算 diff（与前次对比）
        from pathlib import Path
        import json
        PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
        SNAPSHOT_PATH = PROJECT_ROOT / "data" / "holdings_snapshot.json"

        def _load_json(path, default=None):
            p = Path(path)
            return json.loads(p.read_text(encoding="utf-8")) if p.exists() else (default or {})

        previous = _load_json(SNAPSHOT_PATH, {})
        prev_holdings = previous.get("holdings", previous) if isinstance(previous, dict) else {}

        # 计算 diff
        prev_codes = {code for user in prev_holdings.values() for code in [h.get("code", "") for h in user] if code}
        curr_codes = {code for user in current_holdings.values() for code in [h.get("code", "") for h in user] if code}
        holdings_diff = {
            "new_funds": list(curr_codes - prev_codes),
            "removed_funds": list(prev_codes - curr_codes),
        }

        _logger.info(f"Holdings: {len(current_holdings)} users, "
                     f"{len(holdings_diff.get('new_funds', []))} new, "
                     f"{len(holdings_diff.get('removed_funds', []))} removed")

        return {
            "holdings": current_holdings,
            "holdings_ok": True,
            "holdings_diff": holdings_diff,
        }