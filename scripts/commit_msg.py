#!/usr/bin/env python3
"""Conventional Commits checker for commit-msg hooks."""

from __future__ import annotations

import re
import sys
from pathlib import Path

PATTERN = re.compile(
    r"^(feat|fix|refactor|perf|docs|test|build|ci|chore)"
    r"(\([a-z0-9._/-]+\))?!?: .{1,72}(\n|$)"
)


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: commit_msg.py <commit-message-file>", file=sys.stderr)
        return 2
    text = Path(sys.argv[1]).read_text(encoding="utf-8")
    subject = next((line for line in text.splitlines() if line and not line.startswith("#")), "")
    if subject.startswith(("Merge ", "Revert ")):
        return 0
    if PATTERN.match(subject) is None:
        print(
            "commit message must use Conventional Commits:\n"
            "  feat|fix|refactor|perf|docs|test|build|ci|chore(scope)?: summary\n"
            f"got: {subject!r}",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
