"""dcc-mcp-blender — MCP Streamable HTTP server embedded in Blender."""

from __future__ import annotations

from dcc_mcp_blender.__version__ import __version__
from dcc_mcp_blender.api import skill_entry, skill_error, skill_exception, skill_success
from dcc_mcp_blender.capabilities import blender_capabilities, blender_capabilities_dict
from dcc_mcp_blender.host import BlenderHost, BlenderTimerPump, BlenderUiDispatcher
from dcc_mcp_blender.server import (
    DEFAULT_PORT,
    SERVER_NAME,
    BlenderMcpServer,
    BlenderServerOptions,
    get_server,
    start_server,
    stop_server,
)

__all__ = [
    "__version__",
    "skill_entry",
    "skill_error",
    "skill_exception",
    "skill_success",
    "blender_capabilities",
    "blender_capabilities_dict",
    "BlenderHost",
    "BlenderTimerPump",
    "BlenderUiDispatcher",
    "BlenderMcpServer",
    "BlenderServerOptions",
    "DEFAULT_PORT",
    "SERVER_NAME",
    "get_server",
    "start_server",
    "stop_server",
]
