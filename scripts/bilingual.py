"""Bilingual documentation pairing helpers."""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

from repo import ROOT

EN_SUFFIX = ".en.md"
LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
SCOPED_ROOTS = (
    ROOT / "docs",
    ROOT / ".agents" / "notes",
)
SCOPED_FILES = (
    ROOT / "README.md",
    ROOT / "AGENTS.md",
)


def is_english_filename(name: str) -> bool:
    return name.endswith(EN_SUFFIX)


def primary_path(path: Path) -> Path:
    if is_english_filename(path.name):
        return path.with_name(path.name[: -len(EN_SUFFIX)] + ".md")
    return path


def english_path(path: Path) -> Path:
    if is_english_filename(path.name):
        return path
    return path.with_name(f"{path.stem}.en.md")


def counterpart_path(path: Path) -> Path:
    if is_english_filename(path.name):
        return primary_path(path)
    return english_path(path)


def iter_scoped_markdown() -> Iterator[Path]:
    seen: set[Path] = set()
    for path in SCOPED_FILES:
        for candidate in (path, english_path(path)):
            if candidate.is_file():
                resolved = candidate.resolve()
                if resolved not in seen:
                    seen.add(resolved)
                    yield candidate
    for root in SCOPED_ROOTS:
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*.md")):
            resolved = path.resolve()
            if resolved not in seen:
                seen.add(resolved)
                yield path


def markdown_link_names(text: str) -> set[str]:
    names: set[str] = set()
    for target in LINK_RE.findall(text):
        dest = target.split("#", 1)[0].strip()
        if dest.startswith(("http://", "https://", "mailto:")):
            continue
        if not dest:
            continue
        names.add(Path(dest).name)
    return names
