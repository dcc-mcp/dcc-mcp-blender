"""dcc-mcp-blender — MCP Streamable HTTP server embedded in Blender.

The public surface lives in :mod:`dcc_mcp_blender._public_api` so that the
wheel channel and the Blender 4.2+ extension channel (where the add-on package
root *is* ``dcc_mcp_blender`` and its ``__init__.py`` is the Blender add-on
entrypoint) expose exactly the same top-level names.

The import gates this module used to run inline -- ``repair_sys_path()``, then
``require_supported_host(adapter_version=__version__)``, then
``require_compatible_core()``, and the advisory provenance check -- now run in
that shared module. Keeping them there is what stops the extension channel from
shipping a surface that skipped them: a gate added here alone would silently
vanish from the add-on build.
"""

from __future__ import annotations

from ._public_api import *  # noqa: F401,F403
from ._public_api import __all__  # noqa: F401
