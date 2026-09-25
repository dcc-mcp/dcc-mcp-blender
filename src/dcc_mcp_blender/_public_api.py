"""Single source of truth for the public ``dcc_mcp_blender`` import surface.

Both distribution channels must expose the *same* top-level names:

* the wheel / site-packages channel, where ``dcc_mcp_blender/__init__.py`` is
  this package's real ``__init__``;
* the Blender 4.2+ extension channel, where the add-on package root *is*
  ``dcc_mcp_blender`` and its ``__init__.py`` is the Blender add-on entrypoint
  (``bl_info`` / ``register`` / ``unregister``).

The add-on entrypoint cannot ``import *`` this module eagerly: Blender imports
every add-on module just to read ``bl_info``, so a heavy (or failing) import at
that point would hide the add-on from Preferences entirely. It re-exports these
names lazily instead — see ``packaging/addon_entry/__init__.py``.

Every import below is relative on purpose. This module is executed both as
``dcc_mcp_blender._public_api`` and as
``bl_ext.<repository>.dcc_mcp_blender._public_api``, and only relative imports
resolve correctly in both namespaces.
"""

# The host gate and the compatibility gate must both run before imports that
# bind core integrations.
# ruff: noqa: E402

from __future__ import annotations

from .__version__ import __version__
from ._core_compat import require_compatible_core
from ._host_support import require_supported_host
from ._isolated_path import repair_sys_path

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

from ._capability_manifest import (
    BlenderCapabilityManifestBuilder,
    CapabilityRecord,
    build_manifest_payload,
    register_capability_mcp_tool,
)
from ._project_tools import (
    ENV_PROJECT_TOOLS,
    BlenderSceneResolver,
    ProjectToolsIntegration,
)
from ._project_tools import (
    attach_to_server as attach_project_tools,
)
from ._provenance import (
    PackageProvenanceError,
    ProvenanceReport,
    check_provenance,
    collect_report,
    require_expected_origin,
)
from ._readiness import (
    ENV_READINESS_TIMEOUT_SECS,
    ReadinessBinder,
    install_readiness,
    resolve_readiness_timeout_secs,
)
from ._resources import (
    DEFAULT_SCENE_HANDLERS,
    DEFAULT_SCENE_THROTTLE_SECS,
    ENV_RESOURCES,
    SCHEME_BLENDER_DATA,
    BlenderResourceBinder,
    install_resources,
)
from ._semantic_index import (
    ENV_SEMANTIC_EMBEDDER,
    ENV_SEMANTIC_INDEX,
    BlenderSemanticIndex,
    build_semantic_index,
)
from .api import skill_entry, skill_error, skill_exception, skill_success
from .capabilities import blender_capabilities, blender_capabilities_dict
from .context_snapshot import (
    BlenderContextSnapshotProvider,
    collect_gateway_metadata,
    make_snapshot_provider,
)
from .host import BlenderHost, BlenderTimerPump, BlenderUiDispatcher
from .server import (
    DEFAULT_PORT,
    SERVER_NAME,
    BlenderMcpServer,
    BlenderServerOptions,
    get_server,
    start_server,
    stop_server,
)

# Report a runtime that the host resolved from a stale user-level copy before
# any capability is served. This stays advisory on purpose: the package
# ``__init__`` is the import path of the CLI (``dcc_mcp_blender.install:main``)
# and of the ``dcc_mcp.adapters`` entry point, and raising here would break the
# very commands an operator needs to repair the host -- before the add-on entry
# or the startup hook can print their far clearer diagnosis. A package manager
# that resolves each dcc-mcp package separately can also leave core outside a
# root declared for the adapter alone, which is legitimate, not a violation.
# The gate that fails closed lives in the add-on entry and the startup hook.
IMPORT_PROVENANCE_REPORT = check_provenance(raise_on_violation=False)

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
    # Compatibility gate, re-exported so skills can pre-flight a host.
    "require_compatible_core",
    # PYTHONPATH repair for hosts that boot an isolated Python (Blender 5.x).
    "repair_sys_path",
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

#: Gates this module runs, in order, before the rest of the surface is ready.
#: Both channels execute exactly this sequence: the path repair first so that a
#: host it can rescue is judged after the repair, then the host boundary, then
#: the core-compatibility contract. ``tests/test_public_import_contract.py``
#: asserts the sequence per channel, so a gate added to one channel only is
#: caught by the suite instead of silently dropping from the other.
PUBLIC_API_GATE_NAMES = (
    "repair_sys_path",
    "require_supported_host",
    "require_compatible_core",
)
