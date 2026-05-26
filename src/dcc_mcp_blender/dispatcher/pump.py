"""Blender dispatcher and timer-pump factory helpers."""

from __future__ import annotations

from typing import Any

from dcc_mcp_core import PyPumpedDispatcher

from dcc_mcp_blender.host import BlenderTimerPump, BlenderUiDispatcher

DEFAULT_BUDGET_MS = 200
OVERRUN_MULTIPLIER = 1.0

BlenderUiPump = BlenderTimerPump
_CorePump = BlenderTimerPump


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
