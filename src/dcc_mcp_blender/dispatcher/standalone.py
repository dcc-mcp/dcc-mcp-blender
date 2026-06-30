"""Core-backed Blender standalone dispatcher compatibility wrapper."""

# Import future modules
from __future__ import annotations

import uuid
from typing import Any, Callable, Dict, Optional

from dcc_mcp_core import JobOutcome
from dcc_mcp_core.host import BlockingDispatcher


class BlenderStandaloneDispatcher:
    """Dispatcher for Blender standalone (background) mode.

    Uses core's reference in-process dispatcher and keeps the adapter's small
    historical ``dispatch`` / ``dispatch_async`` convenience API.
    """

    def __init__(self, timeout_ms: int = 30000) -> None:
        self.timeout_ms = timeout_ms
        self._host_dispatcher = BlockingDispatcher()
        self._results: Dict[str, Any] = {}
        self._errors: Dict[str, str] = {}

    @property
    def host_dispatcher(self) -> BlockingDispatcher:
        """Expose the core dispatcher that backs HTTP main-thread routing."""
        return self._host_dispatcher

    def dispatch(self, func: Callable, *args: Any, **kwargs: Any) -> Any:
        """Dispatch a call inline through core's in-process dispatcher."""
        handle = self._host_dispatcher.post(lambda: func(*args, **kwargs))
        return handle.wait(self.timeout_ms / 1000.0)

    def dispatch_async(self, func: Callable, *args: Any, **kwargs: Any) -> str:
        """Dispatch a call asynchronously and return a pollable request id."""
        job_id = self._request_id(func)

        def _invoke():
            try:
                self._results[job_id] = func(*args, **kwargs)
            except Exception as exc:
                self._errors[job_id] = str(exc)

        self._host_dispatcher.post(_invoke)
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
