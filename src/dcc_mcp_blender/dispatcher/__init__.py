"""Blender thread-affinity dispatchers.

Public dispatcher symbols are re-exported from their focused submodules
through the :pep:`8`-compliant ``__all__`` below.

The implementation is split per Single Responsibility into:

================  ====================================================
Module            Purpose
================  ====================================================
``job``           ``_JobEntry`` + ``_current_job`` ContextVar
``cancel``        ``check_blender_cancelled`` cooperative checkpoint
``ui``            ``BlenderUiDispatcher`` (interactive)
``standalone``    ``BlenderStandaloneDispatcher`` (background)
``pump``          ``BlenderUiPump`` / ``_CorePump`` + factory helpers
================  ====================================================

This re-export layer is **zero-overhead**: every name binds to the same
object as the originating submodule.  External callers do not need to
update their imports.

See: https://github.com/loonghao/dcc-mcp-blender/issues/XX
"""

# Import future modules
# Import future modules
from __future__ import annotations

# Import local modules
from dcc_mcp_blender.dispatcher.cancel import check_blender_cancelled
from dcc_mcp_blender.dispatcher.job import DEFAULT_JOB_TIMEOUT_MS, _current_job, _JobEntry
from dcc_mcp_blender.dispatcher.pump import (
    DEFAULT_BUDGET_MS,
    OVERRUN_MULTIPLIER,
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
