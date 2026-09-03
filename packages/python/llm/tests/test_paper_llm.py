from __future__ import annotations

import pytest
from paper_llm import provider_status


@pytest.mark.unit
def test_provider_status() -> None:
    assert provider_status() == "ok"
