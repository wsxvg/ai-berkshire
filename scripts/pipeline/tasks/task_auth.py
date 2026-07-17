"""Cookie 认证 task"""
from __future__ import annotations
from scripts.pipeline.engine import PipelineEngine, PipelineTask

try:
    from tools.logutil import get_logger
except Exception:
    from logutil import get_logger

_logger = get_logger("pipeline.auth")


@PipelineEngine.register
class TaskAuth(PipelineTask):
    name = "auth"
    description = "京东金融 Cookie 认证"

    def execute(self, context: dict, offline: bool = False) -> dict:
        if offline:
            return {"cookies": None, "cookie_ok": False, "cookie_msg": "offline mode"}

        from tools.jd_finance_api import _ensure_cookies, _verify_cookies
        cookies = _ensure_cookies(offline=offline)
        cookie_ok = _verify_cookies(cookies) if cookies else False
        msg = "[OK]" if cookie_ok else "[--]"
        _logger.info(f"Auth: {msg} (cookies={bool(cookies)})")

        return {"cookies": cookies, "cookie_ok": cookie_ok, "cookie_msg": msg}