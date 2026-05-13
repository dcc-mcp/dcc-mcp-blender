"""Blender standalone dispatcher (background mode).

Provides ``BlenderStandaloneDispatcher`` — a dispatcher that runs callbacks
directly (no main-thread marshalling needed because there's no UI).

In background mode (``blender --background``), all code runs in the
main thread anyway, so no special dispatch is needed.
"""

# Import future modules
from __future__ import annotations

# Import built-in modules
import logging
import threading
import time
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)


class BlenderStandaloneDispatcher:
    """Dispatcher for Blender standalone (background) mode.

    Runs callbacks directly — no main-thread marshalling needed.
    """

    def __init__(self, timeout_ms: int = 30000) -> None:
        self.timeout_ms = timeout_ms
        self._pending: Dict[str, Callable] = {}
        self._results: Dict[str, Any] = {}
        self._errors: Dict[str, Exception] = {}
        self._lock = threading.Lock()

    def dispatch(self, func: Callable, *args: Any, **kwargs: Any) -> Any:
        """Dispatch a call (runs directly in standalone mode).

        Args:
            func: The function to call.
            *args: Positional arguments.
            **kwargs: Keyword arguments.

        Returns:
            The function's return value.
        """
        return func(*args, **kwargs)

    def dispatch_async(self, func: Callable, *args: Any, **kwargs: Any) -> str:
        """Dispatch a call asynchronously.

        Returns a job ID that can be polled for completion.

        Args:
            func: The function to call.
            *args: Positional arguments.
            **kwargs: Keyword arguments.

        Returns:
            Job ID string.
        """
        job_id = f"job_{time.time()}_{id(func)}"
        try:
            result = func(*args, **kwargs)
            with self._lock:
                self._results[job_id] = result
        except Exception as e:
            with self._lock:
                self._errors[job_id] = e
        return job_id

    def get_result(self, job_id: str) -> Optional[Any]:
        """Get the result of an async job.

        Args:
            job_id: The job ID returned by ``dispatch_async``.

        Returns:
            The job result, or ``None`` if not ready.
        """
        with self._lock:
            if job_id in self._results:
                return self._results[job_id]
            if job_id in self._errors:
                raise self._errors[job_id]
        return None

    def is_done(self, job_id: str) -> bool:
        """Check if an async job is done.

        Args:
            job_id: The job ID returned by ``dispatch_async``.

        Returns:
            ``True`` if the job is done (success or error).
        """
        with self._lock:
            return job_id in self._results or job_id in self._errors
