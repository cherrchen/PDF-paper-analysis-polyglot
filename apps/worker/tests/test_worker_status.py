from __future__ import annotations

import pytest
from paper_worker import status


@pytest.mark.unit
def test_worker_status() -> None:
    assert status()["status"] == "ok"
