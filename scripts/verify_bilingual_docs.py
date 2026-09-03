#!/usr/bin/env python3
"""Validate Chinese-primary / English-companion markdown pairs and jump links."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bilingual import (
    counterpart_path,
    english_path,
    is_english_filename,
    iter_scoped_markdown,
    markdown_link_names,
    primary_path,
)
from repo import ROOT


def _relative(path: Path) -> str:
    return str(path.relative_to(ROOT))


def main() -> int:
    errors: list[str] = []
    files = list(iter_scoped_markdown())
    if not files:
        errors.append("no scoped bilingual markdown files found")

    primaries = {primary_path(path).resolve() for path in files}
    for primary in sorted(primaries):
        english = english_path(primary)
        if not primary.is_file():
            errors.append(f"missing Chinese primary: {_relative(primary)}")
        if not english.is_file():
            errors.append(f"missing English companion: {_relative(english)}")

    for path in files:
        text = path.read_text(encoding="utf-8")
        rel = _relative(path)
        counterpart = counterpart_path(path)
        names = markdown_link_names(text)
        if counterpart.name not in names:
            errors.append(f"{rel}: missing jump link to {counterpart.name}")
        if "中文" not in text or "English" not in text:
            errors.append(f"{rel}: language switcher must include 中文 and English")
        if is_english_filename(path.name) and primary_path(path).name not in names:
            errors.append(f"{rel}: English file must link back to {primary_path(path).name}")

    if errors:
        print("bilingual documentation validation failed:", file=sys.stderr)
        for item in errors:
            print(f"  - {item}", file=sys.stderr)
        return 1
    print(f"ok  bilingual docs ({len(primaries)} Chinese/English pairs)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
