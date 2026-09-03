from __future__ import annotations

import pytest
from pdf_pipeline import pipeline_status


@pytest.mark.unit
def test_pipeline_status() -> None:
    assert pipeline_status() == "ok"
