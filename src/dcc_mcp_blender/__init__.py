"""dcc-mcp-blender — MCP Streamable HTTP server embedded in Blender."""

# The host gate and the compatibility gate must both run before imports that
# bind core integrations.
# ruff: noqa: E402

from __future__ import annotations

from dcc_mcp_blender.__version__ import __version__
from dcc_mcp_blender._core_compat import require_compatible_core
from dcc_mcp_blender._host_support import require_supported_host
from dcc_mcp_blender._isolated_path import repair_sys_path

# Blender 5.x starts its embedded interpreter with an isolated configuration that
# ignores PYTHONPATH, so dependencies injected by the launcher are invisible from
# inside the host. Restore them before the compatibility gate imports core; on
# hosts that already honoured PYTHONPATH this is a no-op.
#
# Order matters: the repair runs first so that hosts it can rescue are judged
# after the repair, not before it. Running the host gate first would turn every
# Blender 5.x host into a hard HostSupportError even when the repair would have
# made the dependencies visible.
repair_sys_path()

# A host whose interpreter cannot see dcc-mcp-core fails here with a named
# boundary error instead of a ModuleNotFoundError raised from a deeper import.
require_supported_host(adapter_version=__version__)
require_compatible_core()

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
from dcc_mcp_blender._provenance import (
    PackageProvenanceError,
    ProvenanceReport,
    check_provenance,
    collect_report,
    require_expected_origin,
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

# Report a runtime that the host resolved from a stale user-level copy before
# any capability is served. A verbose warning is the loudest safe default here:
# this module is imported by the copy that may itself be the stale one, so the
# gate that fails closed lives in the add-on entry rather than in here.
IMPORT_PROVENANCE_REPORT = check_provenance()

__all__ = [
    "__version__",
    "IMPORT_PROVENANCE_REPORT",
    "PackageProvenanceError",
    "ProvenanceReport",
    "check_provenance",
    "collect_report",
    "require_expected_origin",
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
