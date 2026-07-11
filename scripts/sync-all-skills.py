#!/usr/bin/env python3
"""AI Berkshire – 一键同步 SKILL (跨平台 Python 版)

Windows / Linux / Mac 通吃, 替代 sync-all-skills.sh
"""
from __future__ import annotations
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable


def run(label: str, script: str) -> int:
    print(f"\n=== [{label}] {script} ===")
    r = subprocess.run([PY, str(ROOT / "scripts" / script)], cwd=ROOT)
    return r.returncode


def main() -> int:
    rc = 0
    for label, script in [
        ("1/3 Codex skills", "sync-codex-skills.py"),
        ("2/3 OpenCode skills", "sync-opencode-skills.py"),
        ("3/3 Codex prompts", "sync-codex-prompts.py"),
    ]:
        if run(label, script) != 0:
            rc = 1
    print("\n=== [check] check-skills-sync.py ===")
    r = subprocess.run([PY, str(ROOT / "scripts" / "check-skills-sync.py")], cwd=ROOT)
    if r.returncode != 0:
        rc = 1
    print()
    print("DONE." if rc == 0 else "FAILED (see above).")
    return rc


if __name__ == "__main__":
    sys.exit(main())
