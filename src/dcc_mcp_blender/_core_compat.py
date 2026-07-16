"""Validate the core runtime before importing adapter integrations."""

from __future__ import annotations

import re
from typing import Optional

MIN_CORE_VERSION = "0.19.45"


def _release_tuple(version: str) -> tuple[int, int, int]:
    match = re.match(r"^(\d+)\.(\d+)\.(\d+)", version)
    if match is None:
        raise RuntimeError(f"Invalid dcc-mcp-core version: {version!r}")
    major, minor, patch = match.groups()
    return int(major), int(minor), int(patch)


def require_compatible_core(version: Optional[str] = None, *, module_path: Optional[str] = None) -> None:
    """Reject a host-preloaded core that is older than the adapter contract."""
    if version is None:
        import dcc_mcp_core

        version = str(dcc_mcp_core.__version__)
        module_path = str(getattr(dcc_mcp_core, "__file__", "unknown"))

    if _release_tuple(version) >= _release_tuple(MIN_CORE_VERSION):
        return

    raise RuntimeError(
        f"dcc-mcp-blender requires dcc-mcp-core>={MIN_CORE_VERSION}, but Blender "
        f"preloaded dcc-mcp-core {version} from {module_path or 'unknown'}. "
        "Restart Blender with the bundled extension wheel ahead of host site-packages."
    )


__all__ = ["MIN_CORE_VERSION", "require_compatible_core"]
