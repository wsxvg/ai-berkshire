#!/usr/bin/env python3
"""Generate OpenCode skills from AI Berkshire Claude command files.

Output: opencode-skills/<name>/SKILL.md for each skill.
Install: scripts/install-opencode-skills.ps1 (Windows) or manual copy.
"""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLAUDE_SKILLS = ROOT / "skills"
OPENCODE_SKILLS = ROOT / "opencode-skills"


def split_frontmatter(text: str) -> tuple[str | None, str]:
    if not text.startswith("---\n"):
        return None, text
    end = text.find("\n---\n", 4)
    if end == -1:
        return None, text
    return text[4:end], text[end + 5 :].lstrip("\n")


def first_heading(text: str, fallback: str) -> str:
    for line in text.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return fallback


def yaml_quote(value: str) -> str:
    value = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{value}"'


def short_description(body: str) -> str:
    """First non-empty, non-heading line as description."""
    for line in body.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and not stripped.startswith(">"):
            return stripped[:120]
    return body[:120]


def build_frontmatter(name: str, source_name: str, source_text: str) -> str:
    existing, body = split_frontmatter(source_text)
    title = first_heading(body, name)
    desc = short_description(body)
    lines = [
        "---",
        f"name: {name}",
        f"description: {yaml_quote(desc)}",
        "user-invocable: true",
    ]
    if existing:
        lines.append(f"# Original frontmatter from skills/{source_name}:")
        for el in existing.split("\n"):
            if el.strip():
                lines.append(f"#   {el.strip()}")
    lines.append("---\n")
    return "\n".join(lines)


def opencode_body(name: str, source_name: str, source_text: str) -> str:
    _, body = split_frontmatter(source_text)
    note = (
        "## OpenCode adapter note\n\n"
        f"This skill is generated from `skills/{source_name}` — the canonical source.\n\n"
        "- Treat `$ARGUMENTS` as the user's request in the current session.\n"
        "- When the source references Claude-only tool names (Task, Agent, etc.), "
        "use the closest capability available in your environment.\n"
        "- Commands reference `python3 tools/...` — use the correct Python path "
        "for your shell.\n"
        "- Preserve the research quality rules from `AGENTS.md`: cross-check "
        "financial data, use exact arithmetic, label uncertainty.\n\n"
    )
    return note + body.rstrip() + "\n"


def main() -> None:
    OPENCODE_SKILLS.mkdir(exist_ok=True)
    count = 0
    for source in sorted(CLAUDE_SKILLS.glob("*.md")):
        name = source.stem
        source_text = source.read_text(encoding="utf-8")
        target_dir = OPENCODE_SKILLS / name
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / "SKILL.md"
        target.write_text(
            build_frontmatter(name, source.name, source_text)
            + opencode_body(name, source.name, source_text),
            encoding="utf-8",
        )
        count += 1
    print(f"Generated {count} OpenCode skills in {OPENCODE_SKILLS.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
