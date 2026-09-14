"""M8 batch B worker CLI: argument handling and one-shot drain reporting."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest
from paper_worker.__main__ import main

if TYPE_CHECKING:
    from pathlib import Path


def test_worker_once_reports_executed_jobs(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["--once", "--jobs-root", str(tmp_path)]) == 0
    printed = json.loads(capsys.readouterr().out.strip())
    assert printed == {"executed": 0, "jobsRoot": str(tmp_path)}


def test_worker_rejects_non_positive_concurrency(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(["--once", "--jobs-root", str(tmp_path), "--concurrency", "0"])
    assert excinfo.value.code == 2
