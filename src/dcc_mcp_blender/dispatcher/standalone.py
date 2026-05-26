"""Core-backed Blender standalone dispatcher compatibility wrapper."""

# Import future modules
from __future__ import annotations

import uuid
from typing import Any, Callable, Dict, Optional

from dcc_mcp_core import InProcessCallableDispatcher, JobOutcome


class BlenderStandaloneDispatcher:
    """Dispatcher for Blender standalone (background) mode.

    Uses core's reference in-process dispatcher and keeps the adapter's small
    historical ``dispatch`` / ``dispatch_async`` convenience API.
    """

    def __init__(self, timeout_ms: int = 30000) -> None:
        self.timeout_ms = timeout_ms
        self._dispatcher = InProcessCallableDispatcher()
        self._results: Dict[str, Any] = {}
        self._errors: Dict[str, str] = {}

    def dispatch(self, func: Callable, *args: Any, **kwargs: Any) -> Any:
        """Dispatch a call inline through core's in-process dispatcher."""
        outcome = self._dispatcher.submit_callable(
            self._request_id(func),
            lambda: func(*args, **kwargs),
            affinity="main",
            timeout_ms=self.timeout_ms,
        )
        return self._value_or_raise(outcome)

    def dispatch_async(self, func: Callable, *args: Any, **kwargs: Any) -> str:
        """Dispatch a call asynchronously and return a pollable request id."""
        job_id = self._request_id(func)

        def _complete(outcome: JobOutcome) -> None:
            if outcome.ok:
                self._results[job_id] = outcome.value
            else:
                self._errors[job_id] = outcome.error or "Blender standalone dispatch failed"

        self._dispatcher.submit_async_callable(
            job_id,
            lambda: func(*args, **kwargs),
            affinity="main",
            timeout_ms=self.timeout_ms,
            on_complete=_complete,
        )
        return job_id

    def get_result(self, job_id: str) -> Optional[Any]:
        """Get an async job result, or ``None`` when still pending."""
        if job_id in self._results:
            return self._results[job_id]
        if job_id in self._errors:
            raise RuntimeError(self._errors[job_id])
        return None

    def is_done(self, job_id: str) -> bool:
        """Check whether an async job has finished."""
        return job_id in self._results or job_id in self._errors

    @staticmethod
    def _request_id(func: Callable) -> str:
        label = getattr(func, "__name__", "callable")
        return f"{label}:{uuid.uuid4().hex}"

    @staticmethod
    def _value_or_raise(outcome: JobOutcome) -> Any:
        if outcome.ok:
            return outcome.value
        raise RuntimeError(outcome.error or "Blender standalone dispatch failed")


__all__ = ["BlenderStandaloneDispatcher"]
