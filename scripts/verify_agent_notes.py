#!/usr/bin/env python3
"""Validate Agent Note tree, filenames, status, headings, and relative links."""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bilingual import is_english_filename
from repo import ROOT

LIFECYCLES = ("proposed", "implemented", "rejected", "archived")
CLASSES = ("feature", "bug-fix", "simplification", "architecture", "process", "testing")
FILENAME_ZH_RE = re.compile(r"^\d{4}-\d{2}-\d{2}-[a-z0-9]+(?:-[a-z0-9]+)*\.md$")
FILENAME_EN_RE = re.compile(r"^\d{4}-\d{2}-\d{2}-[a-z0-9]+(?:-[a-z0-9]+)*\.en.md$")
STATUS_RE = re.compile(r"^Status:\s+(proposed|implemented|rejected(?:\s+—\s+.+)?|archived)\s*$")
HEADING_RE = re.compile(r"^##\s+(.+?)\s*$")
LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
META_NAMES = {"README.md", "README.en.md", "AGENTS.md", "AGENTS.en.md"}

REQUIRED_EN = {
    "proposed": ("Problem", "Proposal", "Alternatives considered", "Acceptance criteria", "Risks"),
    "implemented": ("Problem", "Decision", "Alternatives considered", "Consequences"),
    "rejected": ("Problem", "Proposal", "Alternatives considered"),
    "archived": ("Problem", "Decision", "Alternatives considered", "Consequences"),
}
FORBIDDEN_EN = {
    "implemented": ("Proposal", "Implementation Plan", "Migration Plan", "Acceptance criteria"),
    "archived": ("Proposal", "Implementation Plan", "Migration Plan", "Acceptance criteria"),
}
REQUIRED_ZH = {
    "proposed": ("问题", "提案", "考虑过的替代方案", "验收标准", "风险"),
    "implemented": ("问题", "决策", "考虑过的替代方案", "后果"),
    "rejected": ("问题", "提案", "考虑过的替代方案"),
    "archived": ("问题", "决策", "考虑过的替代方案", "后果"),
}
FORBIDDEN_ZH = {
    "implemented": ("提案", "实施计划", "迁移计划", "验收标准"),
    "archived": ("提案", "实施计划", "迁移计划", "验收标准"),
}


def _notes_root() -> Path:
    return ROOT / ".agents" / "notes"


def _lifecycle_of(path: Path) -> str | None:
    parts = path.relative_to(_notes_root()).parts
    if not parts:
        return None
    return parts[0] if parts[0] in LIFECYCLES else None


def _class_of(path: Path) -> str | None:
    parts = path.relative_to(_notes_root()).parts
    if len(parts) < 2:
        return None
    return parts[1] if parts[1] in CLASSES else None


def _status_lifecycle(status: str) -> str:
    if status.startswith("rejected"):
        return "rejected"
    return status


def _check_links(path: Path, text: str) -> list[str]:
    errors: list[str] = []
    for target in LINK_RE.findall(text):
        if target.startswith(("http://", "https://", "mailto:")):
            continue
        if target.startswith("#"):
            continue
        dest = (path.parent / target.split("#", 1)[0]).resolve()
        if not dest.exists():
            errors.append(f"{path.relative_to(ROOT)}: broken relative link {target}")
    return errors


def main() -> int:
    errors: list[str] = []
    notes_root = _notes_root()
    for lifecycle in LIFECYCLES:
        for class_name in CLASSES:
            directory = notes_root / lifecycle / class_name
            if not directory.is_dir():
                errors.append(f"missing required directory: {directory.relative_to(ROOT)}")

    notes = [path for path in notes_root.rglob("*.md") if path.name not in META_NAMES]
    for path in notes:
        rel = path.relative_to(ROOT)
        english = is_english_filename(path.name)
        pattern = FILENAME_EN_RE if english else FILENAME_ZH_RE
        if pattern.match(path.name) is None:
            expected = "yyyy-mm-dd-topic-title.en.md" if english else "yyyy-mm-dd-topic-title.md"
            errors.append(f"{rel}: filename must match {expected}")
        lifecycle = _lifecycle_of(path)
        class_name = _class_of(path)
        if lifecycle is None:
            errors.append(f"{rel}: not under a known lifecycle")
            continue
        if class_name is None:
            errors.append(f"{rel}: not under a known class")
            continue
        text = path.read_text(encoding="utf-8")
        lines = text.splitlines()
        if not lines or not lines[0].startswith("# Agent Note:"):
            errors.append(f"{rel}: first line must be '# Agent Note: <Title>'")
        status_line = next((line for line in lines if line.startswith("Status:")), None)
        if status_line is None or STATUS_RE.match(status_line) is None:
            errors.append(f"{rel}: missing or invalid Status line")
        else:
            status_value = status_line.split(":", 1)[1].strip()
            if _status_lifecycle(status_value) != lifecycle:
                errors.append(f"{rel}: Status {status_value!r} does not match folder {lifecycle}")
        headings = [match.group(1) for line in lines if (match := HEADING_RE.match(line))]
        required = REQUIRED_EN[lifecycle] if english else REQUIRED_ZH[lifecycle]
        forbidden = (FORBIDDEN_EN if english else FORBIDDEN_ZH).get(lifecycle, ())
        for heading in required:
            if heading not in headings:
                errors.append(f"{rel}: missing required heading '## {heading}'")
        for heading in forbidden:
            if heading in headings:
                errors.append(f"{rel}: forbidden heading '## {heading}' for {lifecycle}")
        errors.extend(_check_links(path, text))

    if errors:
        print("agent note validation failed:", file=sys.stderr)
        for item in errors:
            print(f"  - {item}", file=sys.stderr)
        return 1
    print(f"ok  agent notes ({len(notes)} notes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
