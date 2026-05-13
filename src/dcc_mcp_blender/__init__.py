"""dcc-mcp-blender — Blender MCP server package.

Quick start::

    import dcc_mcp_blender

    # Start the server (auto-gateway: first Blender wins port 8765)
    server = dcc_mcp_blender.start_server()

    # Progressive loading
    server.discover_skills()                # scan SKILL.md, register metadata
    server.load_skill("blender-scene")      # lazy-import skill scripts on demand
    server.unload_skill("blender-scene")    # free memory when no longer needed

    dcc_mcp_blender.stop_server()
"""

from __future__ import annotations

from dcc_mcp_blender.__version__ import __version__
from dcc_mcp_blender._env import (
    ENV_DISABLE_ARBITRARY_SCRIPT,
    ENV_DISABLE_EXECUTE_PYTHON,
    ENV_ENABLE_GATEWAY_FAILOVER,
    ENV_ENABLE_WORKFLOWS,
    ENV_METRICS,
    ENV_STRICT_SKILL_SCAN,
    resolve_enable_gateway_failover,
    resolve_enable_workflows,
    resolve_execute_python_disabled,
    resolve_metrics_enabled,
    resolve_strict_skill_scan,
)
from dcc_mcp_blender.api import (
    skill_entry,
    skill_error,
    skill_exception,
    skill_success,
)
from dcc_mcp_blender.capabilities import blender_capabilities, blender_capabilities_dict
from dcc_mcp_blender.dispatcher import (
    DEFAULT_BUDGET_MS,
    DEFAULT_JOB_TIMEOUT_MS,
    OVERRUN_MULTIPLIER,
    BlenderStandaloneDispatcher,
    BlenderUiDispatcher,
    BlenderUiPump,
    PyPumpedDispatcher,
    _CorePump,
    _current_job,
    _JobEntry,
    check_blender_cancelled,
    create_dispatcher,
    create_pumped_dispatcher,
)
from dcc_mcp_blender.server import (
    BlenderMcpServer,
    get_server,
    start_server,
    stop_server,
)

__all__ = [
    "__version__",
    # server lifecycle
    "BlenderMcpServer",
    "start_server",
    "stop_server",
    "get_server",
    # capabilities
    "blender_capabilities",
    "blender_capabilities_dict",
    # skill helpers
    "skill_entry",
    "skill_error",
    "skill_exception",
    "skill_success",
    # Environment variables
    "ENV_METRICS",
    "ENV_STRICT_SKILL_SCAN",
    "ENV_ENABLE_WORKFLOWS",
    "ENV_ENABLE_GATEWAY_FAILOVER",
    "ENV_DISABLE_EXECUTE_PYTHON",
    "ENV_DISABLE_ARBITRARY_SCRIPT",
    "resolve_enable_gateway_failover",
    "resolve_execute_python_disabled",
    "resolve_metrics_enabled",
    "resolve_strict_skill_scan",
    "resolve_enable_workflows",
    # Dispatchers
    "BlenderUiDispatcher",
    "BlenderStandaloneDispatcher",
    "BlenderUiPump",
    "PyPumpedDispatcher",
    "create_dispatcher",
    "create_pumped_dispatcher",
    "check_blender_cancelled",
    "DEFAULT_BUDGET_MS",
    "DEFAULT_JOB_TIMEOUT_MS",
    "OVERRUN_MULTIPLIER",
    "_CorePump",
    "_JobEntry",
    "_current_job",
]
