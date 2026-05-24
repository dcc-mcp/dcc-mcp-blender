"""Blender host adapter for dcc-mcp-core main-thread dispatch."""

from __future__ import annotations

import threading
from typing import Any, Callable, Optional

from dcc_mcp_core.host import BlockingDispatcher, HostAdapter

TickFn = Callable[[], Optional[float]]


class BlenderCallableDispatcher:
    """Callable dispatcher driven by Blender's host tick loop."""

    def __init__(self, dispatcher: Optional[BlockingDispatcher] = None) -> None:
        self._dispatcher = dispatcher or BlockingDispatcher()

    @property
    def host_dispatcher(self) -> BlockingDispatcher:
        """Return the core dispatcher that backs HTTP main-thread routing."""
        return self._dispatcher

    def dispatch_callable(
        self,
        func: Callable[..., Any],
        *args: Any,
        affinity: str = "main",
        context: Any = None,
        action_name: str = "",
        skill_name: Optional[str] = None,
        execution: str = "sync",
        timeout_hint_secs: Optional[int] = None,
        **kwargs: Any,
    ) -> Any:
        """Post ``func`` to Blender's main-thread queue and wait for its result."""
        _ = (affinity, context, action_name, skill_name, execution)

        def _invoke() -> Any:
            return func(*args, **kwargs)

        handle = self._dispatcher.post(_invoke)
        return handle.wait(timeout_hint_secs)

    def tick(self, max_jobs: int):
        """Drain queued callables from Blender's main thread."""
        return self._dispatcher.tick(max_jobs)

    def tick_blocking(self, max_jobs: int, timeout_ms: int):
        """Drain queued callables, blocking briefly while headless."""
        return self._dispatcher.tick_blocking(max_jobs, timeout_ms)

    def shutdown(self) -> None:
        """Stop accepting queued work."""
        self._dispatcher.shutdown()

    def is_shutdown(self) -> bool:
        """Return whether the underlying dispatcher is shut down."""
        return bool(self._dispatcher.is_shutdown())


class BlenderInlineCallableDispatcher:
    """Callable bridge used after the core dispatcher owns the main-thread hop."""

    def __init__(self, host_dispatcher: Any) -> None:
        self._host_dispatcher = host_dispatcher

    def dispatch_callable(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Execute ``func`` inline once HTTP has dispatched onto Blender's thread."""
        return func(*args, **kwargs)

    def shutdown(self, reason: str = "Interrupted") -> Any:
        """Forward shutdown to the underlying host dispatcher when supported."""
        shutdown = getattr(self._host_dispatcher, "shutdown", None)
        if not callable(shutdown):
            return None
        try:
            return shutdown(reason)
        except TypeError:
            return shutdown()


class BlenderHost(HostAdapter):
    """Drive a dcc-mcp-core dispatcher from Blender's main thread.

    Blender exposes ``bpy.app.timers`` as its native idle primitive. In
    interactive mode this adapter registers the core dispatcher tick with that
    timer API; in background mode it uses :class:`HostAdapter`'s blocking loop.
    """

    def __init__(self, dispatcher, **kwargs) -> None:
        super().__init__(dispatcher, name=kwargs.pop("name", "blender-host"), **kwargs)
        self._tick_fn: Optional[TickFn] = None
        self._tick_thread_ident: Optional[int] = None

    @property
    def tick_thread_ident(self) -> Optional[int]:
        """Thread id of the most recent Blender timer tick."""
        return self._tick_thread_ident

    def is_background(self) -> bool:
        """Return whether Blender is running in background mode."""
        import bpy

        return bool(bpy.app.background)

    def attach_tick(self, tick_fn: TickFn) -> None:
        """Register ``tick_fn`` with ``bpy.app.timers``."""
        import bpy

        def _tick_wrapper() -> Optional[float]:
            self._tick_thread_ident = threading.get_ident()
            return tick_fn()

        self._tick_fn = _tick_wrapper
        bpy.app.timers.register(_tick_wrapper, first_interval=0.0, persistent=True)

    def detach_tick(self) -> None:
        """Unregister the Blender timer tick, if it is still registered."""
        import bpy

        tick_fn = self._tick_fn
        if tick_fn is not None and bpy.app.timers.is_registered(tick_fn):
            bpy.app.timers.unregister(tick_fn)
        self._tick_fn = None
