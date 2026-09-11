"""Escape extracted text for TeX."""

from __future__ import annotations

import unicodedata

_TEX_SPECIALS = {
    "\\": r"\textbackslash{}",
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
}


def escape_latex(text: str) -> str:
    """Normalize extracted controls and escape TeX special characters."""
    escaped: list[str] = []
    for char in text:
        if char in "\r\n\t":
            escaped.append(" ")
        elif unicodedata.category(char) == "Cc":
            continue
        else:
            escaped.append(_TEX_SPECIALS.get(char, char))
    return "".join(escaped)
