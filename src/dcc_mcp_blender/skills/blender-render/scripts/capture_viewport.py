"""Capture the active Blender viewport to an image file."""

from __future__ import annotations

from typing import Optional

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success


def capture_viewport(
    filepath: str,
    resolution_x: Optional[int] = None,
    resolution_y: Optional[int] = None,
) -> dict:
    """Capture the active viewport.

    Args:
        filepath: Destination image path.
        resolution_x: Optional temporary output width.
        resolution_y: Optional temporary output height.

    Returns:
        ActionResultModel dict with the written filepath.
    """
    try:
        import bpy

        if not filepath:
            return skill_error("Missing filepath", "Provide a filepath for the viewport image.")

        scene = bpy.context.scene
        old_filepath = scene.render.filepath
        old_x = scene.render.resolution_x
        old_y = scene.render.resolution_y

        try:
            scene.render.filepath = filepath
            if resolution_x is not None:
                scene.render.resolution_x = int(resolution_x)
            if resolution_y is not None:
                scene.render.resolution_y = int(resolution_y)

            try:
                bpy.ops.screen.screenshot(filepath=filepath)
                method = "screen"
            except Exception:
                bpy.ops.render.opengl(write_still=True, view_context=True)
                method = "opengl"
        finally:
            scene.render.filepath = old_filepath
            scene.render.resolution_x = old_x
            scene.render.resolution_y = old_y

        return skill_success(
            "Viewport captured",
            filepath=filepath,
            method=method,
            prompt="Viewport image saved. Use the file path to inspect the current view.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message="Failed to capture viewport")


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`capture_viewport`."""
    return capture_viewport(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
