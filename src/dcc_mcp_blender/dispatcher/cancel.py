"""Cooperative cancellation checkpoint for Blender.

Provides ``check_blender_cancelled()`` — a lightweight function that
skill authors can call periodically to abort long-running operations
when the user requests cancellation.
"""

# Import future modules
from __future__ import annotations

# Import built-in modules
import logging

logger = logging.getLogger(__name__)

# Cancellation flag (module-level, can be set by external code)
_cancelled = False


def set_blender_cancelled(value: bool = True) -> None:
    """Set the cancellation flag.

    Args:
        value: ``True`` to request cancellation, ``False`` to clear.
    """
    global _cancelled  # noqa: PLW0603
    _cancelled = value
    if value:
        logger.debug("Blender operation cancellation requested")


def check_blender_cancelled() -> bool:
    """Return ``True`` when the current operation should be aborted.

    Skill authors can call this periodically in long-running loops::

        for i in range(large_number):
            if check_blender_cancelled():
                return blender_error("Operation cancelled")
            # ... do work ...

    Returns:
        ``True`` if cancellation has been requested.
    """
    return _cancelled
