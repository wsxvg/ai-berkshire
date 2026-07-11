#!/usr/bin/env bash
# AI Berkshire – 一键同步 SKILL (Codex + OpenCode + Codex Prompts)
# 任何 skills/*.md 修改后必跑
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "=========================================="
echo "AI Berkshire – Skill Sync"
echo "=========================================="
echo ""

# 检查 Python
if ! command -v python3 &> /dev/null && ! command -v python &> /dev/null; then
    echo "ERROR: python not found"
    exit 1
fi
PY=$(command -v python3 || command -v python)

# 跑三个 sync
echo "[1/3] Codex skills..."
$PY scripts/sync-codex-skills.py
echo ""

echo "[2/3] OpenCode skills..."
$PY scripts/sync-opencode-skills.py
echo ""

echo "[3/3] Codex prompts..."
$PY scripts/sync-codex-prompts.py
echo ""

# 一致性检查
echo "=========================================="
echo "Consistency check"
echo "=========================================="
$PY scripts/check-skills-sync.py
echo ""
echo "Done."
