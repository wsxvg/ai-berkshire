#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""统一日志工具（仅依赖 Python 标准库）。"""
from __future__ import annotations

# ── PyPy/Windows UTF-8 乱码修复（必须在任何输出之前执行）──
import sys, io, os
if sys.platform == "win32":
    os.system("chcp 65001 >nul")  # 设控制台编码为 UTF-8
    for _name in ("stdout", "stderr"):
        try:
            _stream = getattr(sys, _name)
            _wrapped = io.TextIOWrapper(_stream.buffer, encoding="utf-8",
                                        errors="replace", write_through=True)
            setattr(sys, _name, _wrapped)
        except Exception:
            pass

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

_DEFAULT_FMT = "[%(asctime)s] %(levelname)s %(name)s: %(message)s"
_DATE_FMT = "%Y-%m-%d %H:%M:%S"

_configured: dict[str, logging.Logger] = {}


def get_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    """返回名为 ``fund.<name>`` 的 logger（进程内单例，handler 不重复添加）。"""
    cached = _configured.get(name)
    if cached is not None:
        return cached

    logger = logging.getLogger(f"fund.{name}")
    logger.setLevel(level)
    logger.propagate = False

    if not logger.handlers:
        fmt = logging.Formatter(_DEFAULT_FMT, _DATE_FMT)

        # stderr handler
        sh = logging.StreamHandler()
        sh.setFormatter(fmt)
        logger.addHandler(sh)

        # 文件：logs/<name>.log，失败静默降级
        try:
            log_dir = Path(__file__).resolve().parent.parent / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            fh = RotatingFileHandler(
                log_dir / f"{name}.log",
                maxBytes=5 * 1024 * 1024,
                backupCount=5,
                encoding="utf-8",
            )
            fh.setFormatter(fmt)
            logger.addHandler(fh)
        except Exception:
            pass

    _configured[name] = logger
    return logger
