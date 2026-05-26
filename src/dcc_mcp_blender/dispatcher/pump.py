"""Blender dispatcher and timer-pump factory helpers."""

from __future__ import annotations

from typing import Any, Callable, Optional

from dcc_mcp_blender.host import BlenderTimerPump, BlenderUiDispatcher

DEFAULT_BUDGET_MS = 200
OVERRUN_MULTIPLIER = 1.0


class _CorePump:
    """Compatibility wrapper for code that only needs pump counters."""

    def __init__(self, budget_ms: int = DEFAULT_BUDGET_MS) -> None:
        self._pump = BlenderTimerPump(budget_ms=budget_ms)

    @property
    def stats(self):
        """Return Blender timer-pump stats."""
        return self._pump.stats

    def pumped_ms(self) -> float:
        """Return the most recent timer tick duration in milliseconds."""
        return self._pump.stats.last_tick_ms

    def pump_count(self) -> int:
        """Return number of timer pump ticks."""
        return self._pump.stats.ticks

    def reset_stats(self) -> None:
        """Reset pump statistics."""
        self._pump.stats.ticks = 0
        self._pump.stats.overrun_cycles = 0
        self._pump.stats.last_tick_ms = 0.0


BlenderUiPump = BlenderTimerPump


def create_dispatcher(
    ui_mode: bool = True,
    timeout_ms: int = 30000,
) -> Any:
    """Create a Blender dispatcher for UI or standalone mode."""
    if ui_mode:
        return BlenderUiDispatcher(timeout_ms=timeout_ms)

    from dcc_mcp_blender.dispatcher.standalone import BlenderStandaloneDispatcher

    return BlenderStandaloneDispatcher(timeout_ms=timeout_ms)


def create_pumped_dispatcher(
    ui_mode: bool = True,
    timeout_ms: int = 30000,
    budget_ms: int = DEFAULT_BUDGET_MS,
) -> Any:
    """Create a dispatcher configured with a Blender timer pump."""
    if ui_mode:
        return BlenderUiDispatcher(timeout_ms=timeout_ms, budget_ms=budget_ms)
    return create_dispatcher(ui_mode=False, timeout_ms=timeout_ms)


class PyPumpedDispatcher:
    """Compatibility wrapper that pumps before delegating string-payload dispatch."""

    def __init__(
        self,
        dispatcher: Any,
        pump: Optional[_CorePump] = None,
    ) -> None:
        self.dispatcher = dispatcher
        self._pump = pump

    def dispatch(self, func: Callable, *args: Any, **kwargs: Any) -> Any:
        """Dispatch after recording one optional pump tick."""
        if self._pump:
            self._pump.stats.ticks += 1
        return self.dispatcher.dispatch(func, *args, **kwargs)

    def pump(self) -> None:
        """Record a manual pump tick for compatibility callers."""
        if self._pump:
            self._pump.stats.ticks += 1


__all__ = [
    "DEFAULT_BUDGET_MS",
    "OVERRUN_MULTIPLIER",
    "BlenderTimerPump",
    "BlenderUiPump",
    "PyPumpedDispatcher",
    "_CorePump",
    "create_dispatcher",
    "create_pumped_dispatcher",
]
