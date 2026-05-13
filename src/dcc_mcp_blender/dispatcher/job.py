"""Job entry and timeout tracking for Blender.

Provides ``_JobEntry`` (job metadata) and ``_current_job`` (ContextVar)
for tracking the currently executing skill/action.
"""

# Import future modules
from __future__ import annotations

# Import built-in modules
import contextvars
import logging
import time
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

DEFAULT_JOB_TIMEOUT_MS = 30000  # 30 seconds

# ContextVar holding the currently executing job
_current_job: contextvars.ContextVar[Optional["_JobEntry"]] = contextvars.ContextVar("_current_job", default=None)


class _JobEntry:
    """Metadata for a single job (skill action execution)."""

    def __init__(
        self,
        job_id: str,
        action_name: str,
        timeout_ms: int = DEFAULT_JOB_TIMEOUT_MS,
    ) -> None:
        self.job_id = job_id
        self.action_name = action_name
        self.timeout_ms = timeout_ms
        self.start_time = time.time()
        self.end_time: Optional[float] = None
        self.result: Dict[str, Any] = {}
        self.error: Optional[str] = None

    def elapsed_ms(self) -> float:
        """Return elapsed time in milliseconds."""
        if self.end_time is not None:
            return (self.end_time - self.start_time) * 1000
        return (time.time() - self.start_time) * 1000

    def is_timed_out(self) -> bool:
        """Return ``True`` if the job has exceeded its timeout."""
        return self.elapsed_ms() > self.timeout_ms

    def finish(self, result: Dict[str, Any]) -> None:
        """Mark the job as finished successfully."""
        self.end_time = time.time()
        self.result = result
        logger.debug(
            "Job %s (%s) finished in %.1fms",
            self.job_id,
            self.action_name,
            self.elapsed_ms(),
        )

    def fail(self, error: str) -> None:
        """Mark the job as failed."""
        self.end_time = time.time()
        self.error = error
        logger.warning(
            "Job %s (%s) failed after %.1fms: %s",
            self.job_id,
            self.action_name,
            self.elapsed_ms(),
            error,
        )

    def to_dict(self) -> Dict[str, Any]:
        """Return a dict representation of this job."""
        return {
            "job_id": self.job_id,
            "action_name": self.action_name,
            "timeout_ms": self.timeout_ms,
            "elapsed_ms": self.elapsed_ms(),
            "is_timed_out": self.is_timed_out(),
            "finished": self.end_time is not None,
            "error": self.error,
        }
