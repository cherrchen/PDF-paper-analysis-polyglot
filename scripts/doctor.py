#!/usr/bin/env python3
"""Verify local toolchains. Missing LaTeX is a hard failure with install guidance."""

from __future__ import annotations

import shutil
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from repo import ROOT


class DoctorError(RuntimeError):
    pass


def _run(argv: Sequence[str]) -> str:
    completed = subprocess.run(argv, check=False, capture_output=True, text=True)
    if completed.returncode != 0:
        raise DoctorError(f"{' '.join(argv)} failed:\n{completed.stderr.strip()}")
    return (completed.stdout or completed.stderr).strip()


def _need(name: str) -> str:
    path = shutil.which(name)
    if path is None:
        raise DoctorError(f"missing required command: {name}")
    return path


def _version_ok(command: str, expected_prefix: str, argv: Sequence[str]) -> None:
    output = _run(argv)
    first = output.splitlines()[0] if output else ""
    haystack = f"{first}\n{output}".lower()
    if expected_prefix.lower() not in haystack:
        raise DoctorError(
            f"{command} version mismatch: expected {expected_prefix!r}, got {first!r}"
        )
    print(f"ok  {command}: {first}")


def _latex_guidance() -> str:
    return """
LaTeX is a first-class repository dependency and cannot be skipped.

Install TeX Live 2026 (or MacTeX 2026) including:
  - lualatex
  - latexmk
  - chktex
  - latexindent

macOS:  brew install --cask mactex-no-gui
Linux:  install TeX Live 2026 from https://tug.org/texlive/
Then re-run: just doctor
""".strip()


def main() -> int:
    errors: list[str] = []
    print(f"repository: {ROOT}")

    checks: list[tuple[str, str, Sequence[str]]] = [
        ("python", "3.13", ("python", "--version")),
        ("uv", "uv", ("uv", "--version")),
        ("node", "v24", ("node", "--version")),
        ("pnpm", "10", ("pnpm", "--version")),
        ("rustc", "1.98", ("rustc", "--version")),
        ("cargo", "1.98", ("cargo", "--version")),
        ("just", "just", ("just", "--version")),
    ]

    for name, prefix, argv in checks:
        try:
            _need(name)
            _version_ok(name, prefix, argv)
        except DoctorError as exc:
            errors.append(str(exc))

    for optional in ("lefthook", "ruff", "biome", "typos", "taplo"):
        path = shutil.which(optional)
        if path is None:
            print(f"warn {optional}: not on PATH (install via mise/just setup)")
        else:
            print(f"ok  {optional}: {path}")

    latex_ok = True
    for required in ("lualatex", "latexmk"):
        if shutil.which(required) is None:
            latex_ok = False
            errors.append(f"missing required command: {required}")
        else:
            try:
                _version_ok(
                    required,
                    required if required != "lualatex" else "LuaHBTeX",
                    (required, "--version"),
                )
            except DoctorError as exc:
                errors.append(str(exc))

    for extra in ("chktex", "latexindent"):
        if shutil.which(extra) is None:
            errors.append(f"missing required command: {extra}")
        else:
            print(f"ok  {extra}: {shutil.which(extra)}")

    lockfiles = (
        ROOT / "uv.lock",
        ROOT / "pnpm-lock.yaml",
        ROOT / "Cargo.lock",
    )
    for lockfile in lockfiles:
        if lockfile.is_file():
            print(f"ok  lockfile: {lockfile.name}")
        else:
            errors.append(f"missing lockfile: {lockfile.name}")

    if not latex_ok:
        errors.append(_latex_guidance())

    if errors:
        print("\ndoctor failed:", file=sys.stderr)
        for item in errors:
            print(f"  - {item}", file=sys.stderr)
        return 1
    print("\ndoctor passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
