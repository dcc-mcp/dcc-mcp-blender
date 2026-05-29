"""dcc-mcp-blender — MCP Streamable HTTP server embedded in Blender."""

from __future__ import annotations

from dcc_mcp_blender.__version__ import __version__
from dcc_mcp_blender._capability_manifest import (
    BlenderCapabilityManifestBuilder,
    CapabilityRecord,
    build_manifest_payload,
    register_capability_mcp_tool,
)
from dcc_mcp_blender._project_tools import (
    ENV_PROJECT_TOOLS,
    BlenderSceneResolver,
    ProjectToolsIntegration,
)
from dcc_mcp_blender._project_tools import (
    attach_to_server as attach_project_tools,
)
from dcc_mcp_blender._readiness import (
    ENV_READINESS_TIMEOUT_SECS,
    ReadinessBinder,
    install_readiness,
    resolve_readiness_timeout_secs,
)
from dcc_mcp_blender._resources import (
    DEFAULT_SCENE_HANDLERS,
    DEFAULT_SCENE_THROTTLE_SECS,
    ENV_RESOURCES,
    SCHEME_BLENDER_DATA,
    BlenderResourceBinder,
    install_resources,
)
from dcc_mcp_blender._semantic_index import (
    ENV_SEMANTIC_EMBEDDER,
    ENV_SEMANTIC_INDEX,
    BlenderSemanticIndex,
    build_semantic_index,
)
from dcc_mcp_blender.api import skill_entry, skill_error, skill_exception, skill_success
from dcc_mcp_blender.capabilities import blender_capabilities, blender_capabilities_dict
from dcc_mcp_blender.context_snapshot import (
    BlenderContextSnapshotProvider,
    collect_gateway_metadata,
    make_snapshot_provider,
)
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
    # Capability manifest
    "CapabilityRecord",
    "BlenderCapabilityManifestBuilder",
    "build_manifest_payload",
    "register_capability_mcp_tool",
    # Context snapshot
    "BlenderContextSnapshotProvider",
    "collect_gateway_metadata",
    "make_snapshot_provider",
    # Project-state persistence
    "ENV_PROJECT_TOOLS",
    "BlenderSceneResolver",
    "ProjectToolsIntegration",
    "attach_project_tools",
    # Resource publishing
    "ENV_RESOURCES",
    "DEFAULT_SCENE_HANDLERS",
    "DEFAULT_SCENE_THROTTLE_SECS",
    "SCHEME_BLENDER_DATA",
    "BlenderResourceBinder",
    "install_resources",
    # Runtime readiness
    "ENV_READINESS_TIMEOUT_SECS",
    "ReadinessBinder",
    "install_readiness",
    "resolve_readiness_timeout_secs",
    # Semantic skill recall (opt-in)
    "ENV_SEMANTIC_INDEX",
    "ENV_SEMANTIC_EMBEDDER",
    "BlenderSemanticIndex",
    "build_semantic_index",
]
