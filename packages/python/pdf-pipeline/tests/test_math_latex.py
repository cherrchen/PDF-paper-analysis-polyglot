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


@pytest.mark.unit
def test_malformed_subscripts_fall_back_to_escaped_text() -> None:
    content = generated.EquationContent(unicodeText="x__1")
    assert equation_to_latex(content) == r"\text{x\_\_1}"


@pytest.mark.unit
def test_dollar_signs_are_escaped_in_text_fallback() -> None:
    content = generated.EquationContent(unicodeText="cost $5")
    assert equation_to_latex(content) == r"\text{cost \$5}"


@pytest.mark.unit
def test_sqrt_wraps_a_single_operand() -> None:
    content = generated.EquationContent(unicodeText="√x")
    assert equation_to_latex(content) == r"\sqrt{x}"


@pytest.mark.unit
def test_ambiguous_sqrt_keeps_source_text() -> None:
    content = generated.EquationContent(unicodeText="√xy")
    latex = equation_to_latex(content)
    assert latex.startswith(r"\text{")
    assert r"\sqrt{}" not in latex
    assert r"\sqrt{x}y" not in latex
