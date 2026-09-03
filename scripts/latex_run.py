#!/usr/bin/env python3
"""Compile first-party LaTeX with latexmk using the repository latexmkrc."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from repo import ROOT

LATEXMKRC = ROOT / "tex" / "latexmkrc"


def _need(name: str) -> None:
    if shutil.which(name) is None:
        raise SystemExit(f"missing {name}. Install TeX Live 2026 / MacTeX and re-run just doctor.")


def compile_tex(source: Path) -> None:
    _need("latexmk")
    _need("lualatex")
    build_dir = source.parent / "build"
    build_dir.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(
        [
            "latexmk",
            "-r",
            str(LATEXMKRC),
            "-cd",
            str(source),
        ],
        check=False,
        cwd=ROOT,
    )
    if completed.returncode != 0:
        raise SystemExit(f"latexmk failed for {source.relative_to(ROOT)}")
    pdf_name = source.with_suffix(".pdf").name
    produced = build_dir / pdf_name
    if not produced.is_file():
        raise SystemExit(f"expected PDF was not produced: {produced.relative_to(ROOT)}")
    print(f"ok  {source.relative_to(ROOT)} -> {produced.relative_to(ROOT)}")


def clean_tex(source: Path) -> None:
    _need("latexmk")
    subprocess.run(
        ["latexmk", "-r", str(LATEXMKRC), "-C", "-cd", str(source)],
        check=False,
        cwd=ROOT,
    )
    build_dir = source.parent / "build"
    if build_dir.is_dir() and not any(build_dir.iterdir()):
        build_dir.rmdir()


def iter_sources(kind: str) -> list[Path]:
    if kind == "templates":
        return sorted((ROOT / "templates" / "latex").glob("*.tex"))
    if kind == "smoke":
        return sorted((ROOT / "tests" / "fixtures" / "source" / "latex").glob("*.tex"))
    raise SystemExit(f"unknown kind {kind}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("compile", "clean"))
    parser.add_argument("kind", choices=("templates", "smoke"))
    args = parser.parse_args()
    sources = iter_sources(args.kind)
    if not sources:
        print(f"no {args.kind} LaTeX sources currently defined")
        return 0
    for source in sources:
        if args.action == "compile":
            compile_tex(source)
        else:
            clean_tex(source)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
