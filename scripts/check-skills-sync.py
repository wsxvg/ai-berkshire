#!/usr/bin/env python3
"""检查 skills 三方同步状态。

失败状态 = 1 (有源未同步)
成功状态 = 0 (三方一致)
"""
from __future__ import annotations
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLAUDE_SKILLS = ROOT / "skills"
CODEX_SKILLS = ROOT / "codex-skills"
OPENCODE_SKILLS = ROOT / "opencode-skills"
CODEX_PROMPTS = ROOT / "codex-prompts"


def normalize(text: str) -> str:
    """去掉 frontmatter / adapter note / frontmatter 注释, 只比较 body。"""
    # 去 frontmatter
    if text.startswith("---"):
        end = text.find("\n---\n", 4)
        if end != -1:
            text = text[end + 5:]
    # 按行扫: 跳过特定段
    skip_block = False
    out_lines = []
    for line in text.splitlines():
        stripped = line.strip()
        # 开始跳过: adapter note / Original frontmatter 注释
        if re.match(r"^## (Codex|OpenCode) adapter note\s*$", stripped):
            skip_block = True
            continue
        if re.match(r"^# Original frontmatter.*$", stripped):
            skip_block = True
            continue
        # 结束跳过: 遇到下一个 # / ## 标题
        if skip_block and (stripped.startswith("# ") or stripped.startswith("## ")):
            skip_block = False
        if skip_block:
            continue
        out_lines.append(line)
    text = "\n".join(out_lines)
    # 去空白差异
    text = re.sub(r"\s+", " ", text).strip()
    return text


def main() -> int:
    source_files = sorted(CLAUDE_SKILLS.glob("*.md"))
    if not source_files:
        print("ERROR: no source skills found in skills/")
        return 1

    issues: list[str] = []
    print(f"Source: {len(source_files)} skills in skills/")
    print()

    codex_count = 0
    opencode_count = 0
    prompts_count = 0

    for src in source_files:
        name = src.stem
        src_text = src.read_text(encoding="utf-8")
        src_norm = normalize(src_text)

        # Codex skill
        codex_file = CODEX_SKILLS / name / "SKILL.md"
        if codex_file.exists():
            codex_count += 1
            codex_text = codex_file.read_text(encoding="utf-8")
            if normalize(codex_text) != src_norm:
                issues.append(f"  STALE: codex-skills/{name}/SKILL.md")
        else:
            issues.append(f"  MISSING: codex-skills/{name}/SKILL.md")

        # OpenCode skill
        opencode_file = OPENCODE_SKILLS / name / "SKILL.md"
        if opencode_file.exists():
            opencode_count += 1
            opencode_text = opencode_file.read_text(encoding="utf-8")
            if normalize(opencode_text) != src_norm:
                issues.append(f"  STALE: opencode-skills/{name}/SKILL.md")
        else:
            issues.append(f"  MISSING: opencode-skills/{name}/SKILL.md")

        # Codex prompt (格式不同, 只检查存在)
        prompt_file = CODEX_PROMPTS / f"{name}.md"
        if prompt_file.exists():
            prompts_count += 1
        else:
            issues.append(f"  MISSING: codex-prompts/{name}.md")

    # 孤儿
    src_names = {p.stem for p in source_files}
    for tgt in CODEX_SKILLS.iterdir():
        if tgt.is_dir() and tgt.name not in src_names:
            issues.append(f"  ORPHAN: codex-skills/{tgt.name}/")
    for tgt in OPENCODE_SKILLS.iterdir():
        if tgt.is_dir() and tgt.name not in src_names:
            issues.append(f"  ORPHAN: opencode-skills/{tgt.name}/")
    for tgt in CODEX_PROMPTS.iterdir():
        if tgt.is_file() and tgt.suffix == ".md" and tgt.stem not in src_names:
            issues.append(f"  ORPHAN: codex-prompts/{tgt.name}")

    print(f"Generated: codex-skills={codex_count}  opencode-skills={opencode_count}  codex-prompts={prompts_count}")
    print(f"Source:    {len(source_files)}")
    print()

    if issues:
        print(f"FAILED ({len(issues)} issues):")
        for i in issues[:30]:
            print(i)
        if len(issues) > 30:
            print(f"  ... and {len(issues) - 30} more")
        print()
        print("Fix: run scripts/sync-all-skills.sh")
        return 1

    print("OK: all skills in sync.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
