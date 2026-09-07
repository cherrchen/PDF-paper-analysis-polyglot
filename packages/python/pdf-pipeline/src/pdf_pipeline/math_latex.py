"""Deterministic unicode/rawText to LaTeX math conversion (M5 Phase 5.7)."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from document_model.generated import schema_models as generated

_MATH_SYMBOLS = {
    "α": r"\alpha",
    "β": r"\beta",
    "γ": r"\gamma",
    "δ": r"\delta",
    "ε": r"\epsilon",
    "θ": r"\theta",
    "λ": r"\lambda",
    "μ": r"\mu",
    "π": r"\pi",
    "σ": r"\sigma",
    "φ": r"\phi",
    "ω": r"\omega",
    "Δ": r"\Delta",
    "Σ": r"\Sigma",
    "Ω": r"\Omega",
    "∞": r"\infty",
    "≤": r"\leq",
    "≥": r"\geq",
    "≠": r"\neq",
    "≈": r"\approx",
    "±": r"\pm",
    "×": r"\times",
    "÷": r"\div",
    "∑": r"\sum",
    "∫": r"\int",
    "√": r"\sqrt",
    "→": r"\rightarrow",
    "←": r"\leftarrow",
    "∈": r"\in",
}

# ASCII math punctuation plus letters/digits. Curly braces are excluded so a
# stray `{` cannot produce an unmatched group after symbol substitution.
_SAFE_MATH_CHARS = set(" \t0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ")
_SAFE_MATH_CHARS.update("=+-*/()[].,:;^_'<>|")


def equation_to_latex(content: generated.EquationContent) -> str:
    """Return the best LaTeX math body for an equation block."""
    if content.latex and content.latex.strip():
        return content.latex.strip()
    source = content.unicodeText or content.rawText or ""
    if not source.strip():
        return r"\text{}"
    converted = _unicode_to_latex(source.strip())
    if converted is not None and (_looks_like_latex(converted) or converted != source.strip()):
        return converted
    escaped = _escape_text_math(source.strip())
    return rf"\text{{{escaped}}}"


def _looks_like_latex(text: str) -> bool:
    return bool(re.search(r"\\[a-zA-Z]+|[\^_]", text))


def _unicode_to_latex(text: str) -> str | None:
    parts: list[str] = []
    for char in text:
        replacement = _MATH_SYMBOLS.get(char)
        if replacement is not None:
            parts.append(replacement + "{}")
            continue
        if char in _SAFE_MATH_CHARS:
            parts.append(char)
            continue
        return None
    return re.sub(r"([A-Za-z0-9{}\\]+)\s*=\s*([^=]+)", r"\1 = \2", "".join(parts))


def _escape_text_math(text: str) -> str:
    return (
        text.replace("\\", r"\textbackslash{}")
        .replace("{", r"\{")
        .replace("}", r"\}")
        .replace("%", r"\%")
        .replace("#", r"\#")
        .replace("&", r"\&")
        .replace("_", r"\_")
    )
