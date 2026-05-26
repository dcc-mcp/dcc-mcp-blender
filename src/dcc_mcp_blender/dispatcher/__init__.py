"""Blender dispatcher compatibility exports backed by dcc-mcp-core."""

from __future__ import annotations

# Import local modules
from dcc_mcp_blender.dispatcher.cancel import check_blender_cancelled
from dcc_mcp_blender.dispatcher.job import DEFAULT_JOB_TIMEOUT_MS, _current_job, _JobEntry
from dcc_mcp_blender.dispatcher.pump import (
    DEFAULT_BUDGET_MS,
    OVERRUN_MULTIPLIER,
    BlenderTimerPump,
    BlenderUiPump,
    PyPumpedDispatcher,
    _CorePump,
    create_dispatcher,
    create_pumped_dispatcher,
)
from dcc_mcp_blender.dispatcher.standalone import BlenderStandaloneDispatcher
from dcc_mcp_blender.dispatcher.ui import BlenderUiDispatcher

__all__ = [
    # Cancellation
    "check_blender_cancelled",
    # Constants
    "DEFAULT_BUDGET_MS",
    "DEFAULT_JOB_TIMEOUT_MS",
    "OVERRUN_MULTIPLIER",
    # Dispatchers
    "BlenderUiDispatcher",
    "BlenderStandaloneDispatcher",
    # Pumps
    "BlenderTimerPump",
    "BlenderUiPump",
    # Factories
    "create_dispatcher",
    "create_pumped_dispatcher",
    # Core dispatcher used by create_pumped_dispatcher
    "PyPumpedDispatcher",
    # Internals exposed for advanced use
    "_CorePump",
    "_JobEntry",
    "_current_job",
]
