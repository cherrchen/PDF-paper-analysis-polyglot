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
