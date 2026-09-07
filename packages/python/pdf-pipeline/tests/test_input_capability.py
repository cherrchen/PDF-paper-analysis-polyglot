# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false
"""FR-PDF-002 input capability tests (M5 Phase 5.0).

Scanned PDFs or documents without an effective text layer must be rejected
with a clear message instead of silently producing low-quality results.
"""

from __future__ import annotations

import io
from pathlib import Path

import pypdfium2 as pdfium
import pytest
from pdf_pipeline.physical import probe_input_capability

FIXTURE_DIR = Path(__file__).resolve().parents[4] / "tests/fixtures/source/latex/build"


def _scanned_like_pdf() -> bytes:
    """A blank page: exactly what a scanned PDF looks like to PDFium."""
    doc = pdfium.PdfDocument.new()
    doc.new_page(595.0, 842.0)
    buffer = io.BytesIO()
    doc.save(buffer)
    doc.close()
    return buffer.getvalue()


def test_blank_pdf_is_rejected_with_reason() -> None:
    capability = probe_input_capability(_scanned_like_pdf())
    assert capability.usable is False
    assert capability.reason
    assert "text layer" in capability.reason


def test_born_digital_pdf_is_usable() -> None:
    pdf_path = FIXTURE_DIR / "smoke.pdf"
    if not pdf_path.exists():
        pytest.skip("smoke fixture not built; run `just latex-smoke`")
    capability = probe_input_capability(pdf_path.read_bytes())
    assert capability.usable is True
    assert capability.reason is None


def test_mixed_document_with_any_text_page_is_usable() -> None:
    """One text-carrying page is enough; per-page verdicts stay internal."""
    pdf_path = FIXTURE_DIR / "spanning-figure.pdf"
    if not pdf_path.exists():
        pytest.skip("spanning-figure fixture not built; run `just latex-smoke`")
    capability = probe_input_capability(pdf_path.read_bytes())
    assert capability.usable is True


def test_zero_page_pdf_fails_at_load() -> None:
    """PDFium rejects zero-page documents before the probe can run."""
    doc = pdfium.PdfDocument.new()
    buffer = io.BytesIO()
    doc.save(buffer)
    doc.close()
    with pytest.raises(pdfium.PdfiumError):
        probe_input_capability(buffer.getvalue())


def test_pipeline_rejects_scanned_input() -> None:
    pytest.importorskip("pdf_pipeline.pipeline")
    # Write the scanned-like bytes to a temp file so run_pipeline sees a Path.
    import tempfile

    from pdf_pipeline.pipeline import run_pipeline

    with tempfile.TemporaryDirectory() as tmp:
        pdf_path = Path(tmp) / "scanned.pdf"
        pdf_path.write_bytes(_scanned_like_pdf())
        with pytest.raises(ValueError, match="unsupported input PDF"):
            run_pipeline(pdf_path, Path(tmp) / "out")
