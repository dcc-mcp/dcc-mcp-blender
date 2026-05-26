"""Blender cooperative-cancellation compatibility helpers."""

# Import future modules
from __future__ import annotations

# Import built-in modules
from dcc_mcp_core import CancelledError, check_dcc_cancelled


def set_blender_cancelled(value: bool = True) -> None:
    """Deprecated no-op kept for callers from older adapter builds.

    Cancellation state is now owned by dcc-mcp-core per request/job.
    """
    _ = value


def check_blender_cancelled() -> bool:
    """Return ``True`` when core reports the active request/job was cancelled.

    New code should call ``dcc_mcp_core.check_dcc_cancelled()``, which raises
    ``CancelledError`` and composes MCP-request and host-dispatcher signals.
    """
    try:
        check_dcc_cancelled()
    except CancelledError:
        return True
    return False


__all__ = ["check_blender_cancelled", "set_blender_cancelled"]
