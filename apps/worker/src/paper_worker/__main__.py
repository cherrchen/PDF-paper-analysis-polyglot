"""Idle worker loop used to prove the application entry point."""

from __future__ import annotations

import signal
import time

from paper_worker import status


def main() -> None:
    running = True

    def _stop(_signum: int, _frame: object) -> None:
        nonlocal running
        running = False

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)
    print(f"worker {status()['status']}", flush=True)
    while running:
        time.sleep(1)


if __name__ == "__main__":
    main()
