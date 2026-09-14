"""Pipeline worker entry point: claim queued jobs and run them (M8 batch B).

The worker owns no business logic: queue, locks, retry, and failure
attribution live in ``pdf_pipeline.jobs``, and the pipeline itself is
unchanged. This module is only argparse wiring plus signal handling.
"""

from __future__ import annotations

import argparse
import json
import signal
import threading
from pathlib import Path

from pdf_pipeline.jobs import POLL_INTERVAL_S, JobWorker


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="PDF pipeline job worker")
    parser.add_argument(
        "--jobs-root",
        type=Path,
        default=Path(".jobs"),
        help="directory holding the queued/running/finished job records",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=1,
        help="jobs to run in parallel (same-workspace jobs stay serialized)",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=POLL_INTERVAL_S,
        help="seconds to idle between empty polls",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="drain the currently queued jobs once and exit",
    )
    args = parser.parse_args(argv)
    if args.concurrency < 1:
        parser.error("--concurrency must be >= 1")
    return args


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    worker = JobWorker(
        args.jobs_root,
        concurrency=args.concurrency,
        poll_interval=args.poll_interval,
    )
    if args.once:
        executed = worker.run_once()
        print(json.dumps({"executed": executed, "jobsRoot": str(args.jobs_root)}), flush=True)
        return 0

    stop = threading.Event()

    def _stop(_signum: int, _frame: object) -> None:
        stop.set()

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)
    print(f"worker watching {args.jobs_root}", flush=True)
    worker.run_forever(stop)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
