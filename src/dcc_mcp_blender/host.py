"""Blender host adapter for dcc-mcp-core main-thread dispatch."""

from __future__ import annotations

import threading
from typing import Callable, Optional

from dcc_mcp_core.host import HostAdapter

TickFn = Callable[[], Optional[float]]


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
