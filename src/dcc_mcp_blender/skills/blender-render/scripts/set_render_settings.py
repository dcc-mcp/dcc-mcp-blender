"""Configure Blender render settings."""

from __future__ import annotations

from typing import Optional

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success

VALID_ENGINES = {"CYCLES", "BLENDER_EEVEE", "BLENDER_EEVEE_NEXT", "BLENDER_WORKBENCH"}


def set_render_settings(
    engine: Optional[str] = None,
    resolution_x: Optional[int] = None,
    resolution_y: Optional[int] = None,
    resolution_percentage: Optional[int] = None,
    fps: Optional[int] = None,
    samples: Optional[int] = None,
    output_path: Optional[str] = None,
    file_format: Optional[str] = None,
) -> dict:
    """Configure render settings for the current scene.

    Args:
        engine: Render engine: CYCLES, BLENDER_EEVEE, BLENDER_EEVEE_NEXT, or BLENDER_WORKBENCH.
        resolution_x: Horizontal resolution in pixels.
        resolution_y: Vertical resolution in pixels.
        resolution_percentage: Render resolution percentage (1-100).
        samples: Number of render samples (Cycles or EEVEE).
        output_path: Output file path for renders.
        file_format: Output file format, e.g. PNG, JPEG, EXR.

    Returns:
        ActionResultModel dict with the updated settings.
    """
    try:
        import bpy

        scene = bpy.context.scene
        render = scene.render

        if engine:
            engine = engine.upper()
            if engine not in VALID_ENGINES:
                return skill_error(
                    f"Invalid engine: {engine}",
                    f"Valid engines: {', '.join(sorted(VALID_ENGINES))}",
                )
            render.engine = engine

        if resolution_x is not None:
            render.resolution_x = resolution_x
        if resolution_y is not None:
            render.resolution_y = resolution_y
        if resolution_percentage is not None:
            render.resolution_percentage = resolution_percentage
        if fps is not None:
            if fps <= 0:
                return skill_error("Invalid frame rate", "fps must be greater than zero")
            render.fps = fps
        if output_path:
            render.filepath = output_path
        if file_format:
            render.image_settings.file_format = file_format.upper()

        if samples is not None:
            if render.engine == "CYCLES":
                scene.cycles.samples = samples
            else:
                # EEVEE
                if hasattr(scene, "eevee"):
                    scene.eevee.taa_render_samples = samples

        return skill_success(
            "Render settings updated",
            engine=render.engine,
            resolution_x=render.resolution_x,
            resolution_y=render.resolution_y,
            resolution_percentage=render.resolution_percentage,
            fps=render.fps,
            output_path=render.filepath,
            prompt="Settings applied. Use render_scene to render.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message="Failed to set render settings")


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`set_render_settings`."""
    return set_render_settings(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
