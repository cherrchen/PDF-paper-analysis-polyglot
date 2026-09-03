#!/usr/bin/env python3
"""Run registered code generators. None are registered during bootstrap."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from repo import ROOT


def main() -> int:
    registry: list[str] = []
    if not registry:
        print("no generators currently registered")
        print("canonical schemas live in schemas/; bindings will be generated later")
        return 0
    print(f"repository: {ROOT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
