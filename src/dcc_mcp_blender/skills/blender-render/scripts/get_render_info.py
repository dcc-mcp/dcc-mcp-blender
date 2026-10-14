"""Return current Blender render settings."""

from __future__ import annotations

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success

from dcc_mcp_blender._frame_rate import frame_rate_info


def get_render_info() -> dict:
    """Return the current render settings.

    Returns:
        ActionResultModel dict with render configuration.
    """
    try:
        import bpy

        scene = bpy.context.scene
        render = scene.render

        info = {
            **frame_rate_info(render),
            "engine": render.engine,
            "resolution_x": render.resolution_x,
            "resolution_y": render.resolution_y,
            "resolution_percentage": render.resolution_percentage,
            "output_path": render.filepath,
            "file_format": render.image_settings.file_format,
            "active_camera": scene.camera.name if scene.camera else None,
        }

        if render.engine == "CYCLES" and hasattr(scene, "cycles"):
            info["cycles_samples"] = scene.cycles.samples
            info["cycles_device"] = scene.cycles.device
        elif hasattr(scene, "eevee"):
            info["eevee_samples"] = scene.eevee.taa_render_samples

        return skill_success(
            "Render info retrieved",
            **info,
            prompt="Use set_render_settings to modify these settings.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message="Failed to get render info")


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`get_render_info`."""
    return get_render_info(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
