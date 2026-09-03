from __future__ import annotations

import pytest
from paper_api import health


@pytest.mark.unit
def test_health_status() -> None:
    assert health()["status"] == "ok"
