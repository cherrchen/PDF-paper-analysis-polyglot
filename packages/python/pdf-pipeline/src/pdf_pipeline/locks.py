"""POSIX locks for queue records and shared local pipeline resources.

Resource identity is the canonical path, independent of jobs root. Acquire
workspace before viewer; never acquire a workspace while holding a viewer lock.
Resource locks are reentrant only within the owning thread.
"""

from __future__ import annotations

import errno
import fcntl
import hashlib
import inspect
import os
import threading
from contextlib import contextmanager
from functools import wraps
from pathlib import Path
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from collections.abc import Callable, Generator


class FileLock:
    """Exclusive flock descriptor; every owner must release it, even on contention."""

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._fd: int | None = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)

    def acquire(self, *, blocking: bool) -> bool:
        if self._fd is None:
            raise RuntimeError("lock already released")
        try:
            fcntl.flock(self._fd, fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))
        except OSError as error:
            if error.errno in (errno.EAGAIN, errno.EACCES):
                return False
            raise
        return True

    def release(self) -> None:
        fd, self._fd = self._fd, None
        if fd is not None:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            finally:
                os.close(fd)


_held = threading.local()


def resource_lock_path(path: Path, kind: str) -> Path:
    """Stable resource lock inode outside artifacts; lock files are never pruned."""
    digest = hashlib.sha256(str(path.resolve()).encode()).hexdigest()
    return path.resolve().parent / ".paper-pipeline-locks" / f"{kind}-{digest}.lock"


@contextmanager
def resource_lock(path: Path, kind: str) -> Generator[None]:
    lock_path = resource_lock_path(path, kind)
    held = cast("set[Path]", getattr(_held, "paths", set[Path]()))
    _held.paths = held
    if lock_path in held:
        yield
        return
    lock = FileLock(lock_path)
    try:
        if not lock.acquire(blocking=True):
            raise RuntimeError(f"cannot acquire {kind} lock")
        held.add(lock_path)
        try:
            yield
        finally:
            held.remove(lock_path)
    finally:
        lock.release()


def resource_locked[**P, R](
    parameter: str, kind: str
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Protect a whole operation, including its reads, using a named Path argument."""

    def decorate(function: Callable[P, R]) -> Callable[P, R]:
        signature = inspect.signature(function)

        @wraps(function)
        def locked(*args: P.args, **kwargs: P.kwargs) -> R:
            bound = signature.bind(*args, **kwargs)
            path = bound.arguments[parameter]
            if not isinstance(path, Path):
                raise TypeError(f"{parameter} must be a Path")
            with resource_lock(path, kind):
                return function(*args, **kwargs)

        return locked

    return decorate
