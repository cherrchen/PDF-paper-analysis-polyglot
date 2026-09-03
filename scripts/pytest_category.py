#!/usr/bin/env python3
"""Treat pytest collection of zero selected tests as an explicit empty category."""

from __future__ import annotations

import subprocess
import sys


def main() -> int:
    if len(sys.argv) < 3:
        print("usage: pytest_category.py <label> <pytest-args...>", file=sys.stderr)
        return 2
    label = sys.argv[1]
    argv = sys.argv[2:]
    completed = subprocess.run(argv, check=False)
    if completed.returncode == 5:
        print(f"no {label} tests currently defined")
        return 0
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
