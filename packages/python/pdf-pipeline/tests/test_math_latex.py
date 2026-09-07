"""Tests for equation LaTeX conversion."""

from __future__ import annotations

import pytest
from document_model.generated import schema_models as generated
from pdf_pipeline.math_latex import equation_to_latex


@pytest.mark.unit
def test_equation_prefers_existing_latex() -> None:
    content = generated.EquationContent(latex="E = mc^2", number="1")
    assert equation_to_latex(content) == "E = mc^2"


@pytest.mark.unit
def test_equation_unicode_fallback_uses_text() -> None:
    content = generated.EquationContent(unicodeText="plain words", number="2")
    assert equation_to_latex(content) == r"\text{plain words}"


@pytest.mark.unit
def test_equation_unicode_symbols_keep_command_boundaries() -> None:
    content = generated.EquationContent(unicodeText="\u03b1x = \u03b2y")
    assert equation_to_latex(content) == r"\alpha{}x = \beta{}y"


@pytest.mark.unit
def test_equation_unsafe_unicode_falls_back_to_text() -> None:
    content = generated.EquationContent(unicodeText="\u03b1 \U0001f600 \u03b2")
    latex = equation_to_latex(content)
    assert latex.startswith(r"\text{")
    assert r"\alphax" not in latex
    assert r"\alpha{}" not in latex
