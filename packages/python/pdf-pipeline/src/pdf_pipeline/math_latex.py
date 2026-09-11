"""Deterministic unicode/rawText to LaTeX math conversion (M5 Phase 5.7)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pdf_pipeline.tex_escape import escape_latex

if TYPE_CHECKING:
    from document_model.generated import schema_models as generated

_STANDALONE_SYMBOLS = {
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
    "→": r"\rightarrow",
    "←": r"\leftarrow",
    "∈": r"\in",
}

# ASCII math punctuation plus letters/digits. Scripts and roots are parsed
# separately so a stray `_` or `√` cannot emit illegal or meaning-changing TeX.
_SAFE_MATH_CHARS = set(" \t0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ")
_SAFE_MATH_CHARS.update("=+-*/()[].,:;<>|")
_MATH_STRUCTURE_CHARS = set("=+-*/^_<>|\\")


def equation_to_latex(content: generated.EquationContent) -> str:
    """Return the best LaTeX math body for an equation block."""
    if content.latex and content.latex.strip():
        return content.latex.strip()
    source = content.unicodeText or content.rawText or ""
    if not source.strip():
        return r"\text{}"
    stripped = source.strip()
    converted = _unicode_to_latex(stripped)
    if converted is not None and _keep_as_math(converted, stripped):
        return converted
    return rf"\text{{{escape_latex(stripped)}}}"


def _keep_as_math(converted: str, source: str) -> bool:
    if converted != source:
        return True
    return any(char in _MATH_STRUCTURE_CHARS for char in converted)


def _unicode_to_latex(text: str) -> str | None:
    """Parse a conservative subset of unicode math; return None when unsure."""
    parts: list[str] = []
    index = 0
    while index < len(text):
        char = text[index]
        if char == "√":
            operand = _parse_sqrt_operand(text, index + 1)
            if operand is None:
                return None
            body, consumed = operand
            parts.append(rf"\sqrt{{{body}}}")
            index += 1 + consumed
            continue
        replacement = _STANDALONE_SYMBOLS.get(char)
        if replacement is not None:
            parts.append(replacement + "{}")
            index += 1
            continue
        if char in "^_":
            script = _parse_script(text, index)
            if script is None:
                return None
            piece, consumed = script
            parts.append(piece)
            index += consumed
            continue
        if char in _SAFE_MATH_CHARS:
            parts.append(char)
            index += 1
            continue
        return None
    return _normalize_equals("".join(parts))


def _parse_script(text: str, index: int) -> tuple[str, int] | None:
    op = text[index]
    cursor = index + 1
    if cursor >= len(text):
        return None
    nxt = text[cursor]
    grouped = _convert_grouped(text, cursor)
    if grouped is not None:
        inner, consumed = grouped
        return f"{op}{{{inner}}}", 1 + consumed
    if nxt.isalnum():
        return op + nxt, 2
    symbol = _STANDALONE_SYMBOLS.get(nxt)
    if symbol is None:
        return None
    return f"{op}{{{symbol}{{}}}}", 2


def _parse_sqrt_operand(text: str, index: int) -> tuple[str, int] | None:
    if index >= len(text):
        return None
    grouped = _convert_grouped(text, index)
    if grouped is not None:
        return grouped
    char = text[index]
    if char.isdigit():
        cursor = index
        while cursor < len(text) and text[cursor].isdigit():
            cursor += 1
        return text[index:cursor], cursor - index
    if char.isalpha() and (index + 1 >= len(text) or not text[index + 1].isalpha()):
        return char, 1
    symbol = _STANDALONE_SYMBOLS.get(char)
    if symbol is None:
        return None
    return symbol + "{}", 1


def _convert_grouped(text: str, index: int) -> tuple[str, int] | None:
    if index >= len(text) or text[index] not in "({":
        return None
    close = ")" if text[index] == "(" else "}"
    group = _balanced(text, index, text[index], close)
    if group is None:
        return None
    inner, consumed = group
    converted = _unicode_to_latex(inner[1:-1])
    if converted is None:
        return None
    return converted, consumed


def _balanced(text: str, start: int, open_ch: str, close_ch: str) -> tuple[str, int] | None:
    if start >= len(text) or text[start] != open_ch:
        return None
    depth = 0
    for cursor in range(start, len(text)):
        current = text[cursor]
        if current == open_ch:
            depth += 1
        elif current == close_ch:
            depth -= 1
            if depth == 0:
                return text[start : cursor + 1], cursor + 1 - start
    return None


def _normalize_equals(text: str) -> str:
    if "=" not in text:
        return text
    left, sep, right = text.partition("=")
    if not sep:
        return text
    return f"{left.rstrip()} = {right.lstrip()}"
