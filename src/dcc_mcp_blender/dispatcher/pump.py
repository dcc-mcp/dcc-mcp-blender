"""Blender UI pump and dispatcher factory helpers.

Provides ``BlenderUiPump``, ``_CorePump``, ``create_dispatcher``,
and ``create_pumped_dispatcher``.
"""

# Import future modules
from __future__ import annotations

# Import built-in modules
import logging
import time
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

DEFAULT_BUDGET_MS = 200  # 200ms budget per pump
OVERRUN_MULTIPLIER = 2.0  # Allow 2x budget before warning


class _CorePump:
    """Core pump logic (platform-independent)."""

    def __init__(self, budget_ms: int = DEFAULT_BUDGET_MS) -> None:
        self.budget_ms = budget_ms
        self._total_pumped_ms: float = 0.0
        self._pump_count: int = 0

    def pump(self) -> None:
        """Pump the event loop (override in subclass)."""
        pass

    def pumped_ms(self) -> float:
        """Return total pumped time in milliseconds."""
        return self._total_pumped_ms

    def pump_count(self) -> int:
        """Return number of pump operations."""
        return self._pump_count

    def reset_stats(self) -> None:
        """Reset statistics."""
        self._total_pumped_ms = 0.0
        self._pump_count = 0


class BlenderUiPump(_CorePump):
    """UI pump for Blender interactive mode.

    Pumps Blender's event loop to keep the UI responsive
    during long-running operations.
    """

    def pump(self) -> None:
        """Pump Blender's event loop."""
        start = time.time()
        try:
            import bpy  # noqa: PLC0415

            # Pump Blender's event loop
            if hasattr(bpy.ops.wm, "call_in_main_thread"):
                # Use timer-based approach
                pass  # TODO: Implement proper pumping
        except ImportError:
            pass
        elapsed = (time.time() - start) * 1000
        self._total_pumped_ms += elapsed
        self._pump_count += 1
        if elapsed > self.budget_ms * OVERRUN_MULTIPLIER:
            logger.warning(
                "BlenderUiPump: pump took %.1fms (budget: %dms)",
                elapsed,
                self.budget_ms,
            )


def create_dispatcher(
    ui_mode: bool = True,
    timeout_ms: int = 30000,
) -> Any:
    """Create a dispatcher based on mode.

    Args:
        ui_mode: ``True`` for UI mode, ``False`` for standalone.
        timeout_ms: Timeout in milliseconds.

    Returns:
        A dispatcher instance.
    """
    if ui_mode:
        from dcc_mcp_blender.dispatcher.ui import BlenderUiDispatcher

        return BlenderUiDispatcher(timeout_ms=timeout_ms)
    else:
        from dcc_mcp_blender.dispatcher.standalone import BlenderStandaloneDispatcher

        return BlenderStandaloneDispatcher(timeout_ms=timeout_ms)


def create_pumped_dispatcher(
    ui_mode: bool = True,
    timeout_ms: int = 30000,
    budget_ms: int = DEFAULT_BUDGET_MS,
) -> Any:
    """Create a pumped dispatcher (with UI pump).

    Args:
        ui_mode: ``True`` for UI mode, ``False`` for standalone.
        timeout_ms: Timeout in milliseconds.
        budget_ms: Budget per pump in milliseconds.

    Returns:
        A dispatcher instance with pumping support.
    """
    dispatcher = create_dispatcher(ui_mode=ui_mode, timeout_ms=timeout_ms)
    if ui_mode:
        pump = BlenderUiPump(budget_ms=budget_ms)
        # Attach pump to dispatcher
        setattr(dispatcher, "_pump", pump)
    return dispatcher


# For Rust-backed dispatch (string-payload dispatch)
class PyPumpedDispatcher:
    """Rust-backed dispatcher with pump support."""

    def __init__(
        self,
        dispatcher: Any,
        pump: Optional[_CorePump] = None,
    ) -> None:
        self.dispatcher = dispatcher
        self._pump = pump

    def dispatch(self, func: Callable, *args: Any, **kwargs: Any) -> Any:
        """Dispatch with pumping."""
        if self._pump:
            self._pump.pump()
        return self.dispatcher.dispatch(func, *args, **kwargs)

    def pump(self) -> None:
        """Manually pump."""
        if self._pump:
            self._pump.pump()
