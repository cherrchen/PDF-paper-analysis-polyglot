#!/usr/bin/env python3
"""Format-check first-party LaTeX with ChkTeX and latexindent when available."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from repo import ROOT

FIRST_PARTY = (
    ROOT / "templates" / "latex",
    ROOT / "tests" / "fixtures" / "source" / "latex",
)


def _sources() -> list[Path]:
    files: list[Path] = []
    for directory in FIRST_PARTY:
        files.extend(sorted(directory.glob("*.tex")))
    return files


def _need(name: str) -> str:
    path = shutil.which(name)
    if path is None:
        raise SystemExit(f"missing {name}. Install TeX Live 2026 / MacTeX and re-run just doctor.")
    return path


def chktex(sources: list[Path]) -> None:
    chktex_bin = _need("chktex")
    rc = ROOT / ".chktexrc"
    for source in sources:
        completed = subprocess.run(
            [chktex_bin, "-q", "-l", str(rc), str(source)],
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            sys.stderr.write(completed.stdout)
            sys.stderr.write(completed.stderr)
            raise SystemExit(f"ChkTeX failed for {source.relative_to(ROOT)}")
        print(f"ok  chktex {source.relative_to(ROOT)}")


def latexindent_check(sources: list[Path]) -> None:
    indent = _need("latexindent")
    for source in sources:
        with tempfile.TemporaryDirectory() as tmp:
            formatted = Path(tmp) / source.name
            completed = subprocess.run(
                [
                    indent,
                    "-l",
                    str(ROOT / ".latexindent.yaml"),
                    "-o",
                    str(formatted),
                    str(source),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            if completed.returncode != 0:
                sys.stderr.write(completed.stderr)
                raise SystemExit(f"latexindent failed for {source.relative_to(ROOT)}")
            if formatted.read_text(encoding="utf-8") != source.read_text(encoding="utf-8"):
                raise SystemExit(
                    f"LaTeX formatting drift in {source.relative_to(ROOT)}; run just fmt"
                )
        print(f"ok  latexindent {source.relative_to(ROOT)}")


def latexindent_write(sources: list[Path]) -> None:
    indent = _need("latexindent")
    for source in sources:
        completed = subprocess.run(
            [
                indent,
                "-l",
                str(ROOT / ".latexindent.yaml"),
                "-w",
                "-s",
                str(source),
            ],
            check=False,
        )
        if completed.returncode != 0:
            raise SystemExit(f"latexindent failed for {source.relative_to(ROOT)}")
        backup = source.with_name(source.name + ".bak0")
        if backup.is_file():
            backup.unlink()
        print(f"ok  formatted {source.relative_to(ROOT)}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("check", "fmt"))
    args = parser.parse_args()
    sources = _sources()
    if not sources:
        print("no first-party LaTeX sources currently defined")
        return 0
    if args.action == "check":
        chktex(sources)
        latexindent_check(sources)
    else:
        latexindent_write(sources)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
