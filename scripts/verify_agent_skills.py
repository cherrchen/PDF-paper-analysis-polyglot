#!/usr/bin/env python3
"""Validate Agent Skill frontmatter, names, and required sections."""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from repo import ROOT

FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)
NAME_RE = re.compile(r"^name:\s*(.+)$", re.MULTILINE)
DESC_RE = re.compile(r"^description:\s*(.+)$", re.MULTILINE)
REQUIRED_SECTIONS = (
    "When to use",
    "Preconditions",
    "Workflow",
    "Validation",
    "Failure handling",
    "Documentation impact",
)
EXPECTED_SKILLS = (
    "repo-bootstrap",
    "pre-push-checks",
    "code-review",
    "docs-review",
    "agent-note",
    "archive-agent-notes",
    "schema-change",
    "latex-rendering",
    "pdf-regression",
    "release",
    "bilingual-docs",
)


def main() -> int:
    errors: list[str] = []
    skills_root = ROOT / ".agents" / "skills"
    found: set[str] = set()
    for skill_dir in sorted(path for path in skills_root.iterdir() if path.is_dir()):
        skill_file = skill_dir / "SKILL.md"
        rel = skill_file.relative_to(ROOT)
        if not skill_file.is_file():
            errors.append(f"{skill_dir.relative_to(ROOT)}: missing SKILL.md")
            continue
        text = skill_file.read_text(encoding="utf-8")
        match = FRONTMATTER_RE.match(text)
        if match is None:
            errors.append(f"{rel}: missing YAML frontmatter")
            continue
        front = match.group(1)
        name_match = NAME_RE.search(front)
        desc_match = DESC_RE.search(front)
        if name_match is None or desc_match is None:
            errors.append(f"{rel}: frontmatter requires name and description")
            continue
        name = name_match.group(1).strip()
        if name != skill_dir.name:
            errors.append(f"{rel}: name {name!r} must match directory {skill_dir.name!r}")
        found.add(name)
        for section in REQUIRED_SECTIONS:
            if f"## {section}" not in text:
                errors.append(f"{rel}: missing section '## {section}'")
    missing = [name for name in EXPECTED_SKILLS if name not in found]
    for name in missing:
        errors.append(f"missing required skill: {name}")
    if errors:
        print("agent skill validation failed:", file=sys.stderr)
        for item in errors:
            print(f"  - {item}", file=sys.stderr)
        return 1
    print(f"ok  agent skills ({len(found)} skills)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
