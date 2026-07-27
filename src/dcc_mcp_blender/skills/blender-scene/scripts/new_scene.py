"""Create a new empty Blender scene.

After ``read_factory_settings`` Blender wipes all registered timers — including
the MCP main-thread dispatcher pump.  This module restores the pump so subsequent
tool calls succeed without restarting Blender.
"""

from __future__ import annotations

import logging

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success

logger = logging.getLogger(__name__)


def _preserve_mcp_dispatcher() -> None:
    """Re-register the MCP main-thread dispatcher timer after Blender factory reset.

    ``bpy.ops.wm.read_factory_settings(use_empty=True)`` unregisters all
    ``bpy.app.timers`` callbacks including the dispatcher pump.  The HTTP
    server stays alive (port remains open) but subsequent tool calls hang
    because the queue is never drained.

    This is best-effort — it must not raise or the ``new_scene`` operation
    would fail with a half-applied factory reset.
    """
    try:
        from dcc_mcp_blender.server import get_server

        server = get_server()
        if server is None:
            return

        dispatcher = getattr(server, "_blender_dispatcher", None)
        if dispatcher is None:
            return

        start_pump = getattr(dispatcher, "start_pump", None)
        if callable(start_pump):
            start_pump()
            logger.info("new_scene: re-registered MCP dispatcher timer after factory reset")

        # Re-run the readiness probe so /v1/readyz reflects the restored pump.
        readiness = getattr(server, "readiness", None)
        if readiness is not None and hasattr(readiness, "revalidate_dispatcher"):
            readiness.revalidate_dispatcher()
    except Exception:
        # Best-effort: never let dispatcher preservation break new_scene.
        logger.debug("new_scene: dispatcher preservation skipped", exc_info=True)


def new_scene() -> dict:
    """Create a new Blender scene by loading the default startup file.

    Returns:
        ActionResultModel dict.
    """
    try:
        import bpy

        bpy.ops.wm.read_factory_settings(use_empty=True)
        _preserve_mcp_dispatcher()
        return skill_success(
            "New scene created",
            prompt="Check the result with list_objects or use related actions to continue.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message="Failed to create new scene")


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`new_scene`."""
    return new_scene(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
