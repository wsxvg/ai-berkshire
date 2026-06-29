#!/usr/bin/env bash
# Install AI Berkshire OpenCode skills.
# Usage: bash scripts/install-opencode-skills.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="${OPENCODE_SKILLS_DIR:-$HOME/.opencode/skills}"

echo "AI Berkshire – OpenCode Skill Installer"
echo "Source: $ROOT"
echo "Dest:   $DEST"
echo ""

# Step 1: Sync
echo "[1/3] Generating OpenCode skills from skills/*.md ..."
python3 "$ROOT/scripts/sync-opencode-skills.py"

# Step 2: Ensure destination exists
echo "[2/3] Ensuring destination directory ..."
mkdir -p "$DEST"

# Step 3: Copy
echo "[3/3] Installing skills ..."
SRC="$ROOT/opencode-skills"
count=0
for skill_dir in "$SRC"/*/; do
    [ -d "$skill_dir" ] || continue
    name="$(basename "$skill_dir")"
    rm -rf "$DEST/$name"
    cp -R "$skill_dir" "$DEST/$name"
    count=$((count + 1))
    echo "  Installed: $name"
done

echo ""
echo "Installed $count skills to $DEST"
echo "Restart OpenCode to pick up new skills."
