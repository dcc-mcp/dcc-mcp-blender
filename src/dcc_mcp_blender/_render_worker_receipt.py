"""Dependency-free status receipts for owned Blender workers."""

from __future__ import annotations

import errno
import hashlib
import json
import sys
import time
import uuid
from pathlib import Path

# Fast conflicts are bounded by attempt count. A separate one-second deadline
# leaves room for slow filesystem calls but prevents starting another retry
# after the budget expires; it cannot interrupt an operation already in flight.
_IO_RETRY_DEADLINE = 1.0
_IO_RETRY_ATTEMPTS = 10
_IO_RETRY_INTERVAL = 0.01


def _retry_receipt_io(operation, *, reading=False):
    """Bound retries for transient Windows sharing/access conflicts only."""
    deadline = time.monotonic() + _IO_RETRY_DEADLINE
    for attempt in range(_IO_RETRY_ATTEMPTS):
        try:
            return operation()
        except OSError as exc:
            winerror = getattr(exc, "winerror", None)
            retryable = winerror in {5, 32, 33} or (
                reading and winerror is None and isinstance(exc, PermissionError) and exc.errno == errno.EACCES
            )
            remaining = deadline - time.monotonic()
            if sys.platform != "win32" or not retryable or attempt + 1 == _IO_RETRY_ATTEMPTS or remaining <= 0:
                raise
            time.sleep(min(_IO_RETRY_INTERVAL, remaining))
            if time.monotonic() >= deadline:
                raise


STATES = {"running", "completed", "failed", "cancelled", "timed_out", "host_shutdown", "stop_failed"}


def file_hash(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_worker_status(directory, result):
    """Atomically replace only this worker's status receipt."""
    path = Path(directory) / "worker-status.json"
    temporary = path.with_name(".worker-status-" + uuid.uuid4().hex + ".tmp")
    try:
        with temporary.open("x", encoding="utf-8") as stream:
            json.dump(result, stream)
        _retry_receipt_io(lambda: temporary.replace(path))
    finally:
        try:
            temporary.unlink()
        except OSError:
            pass


def read_worker_status(directory, job_id, kind):
    directory = Path(directory)
    if not directory.is_absolute():
        raise ValueError("job_directory must be absolute")
    path = directory / "worker-status.json"

    def read_text():
        if path.stat().st_size > 1_000_000:
            raise ValueError("Worker receipt exceeds the size limit")
        return path.read_text(encoding="utf-8")

    result = json.loads(_retry_receipt_io(read_text, reading=True))
    if (
        not isinstance(result, dict)
        or result.get("job_id") != job_id
        or result.get("kind") != kind
        or result.get("status") not in STATES
    ):
        raise ValueError("Worker receipt does not match this job")
    if file_hash(directory / "request.json") != result.get("request_sha256"):
        raise ValueError("Worker request changed after submission")
    return result
