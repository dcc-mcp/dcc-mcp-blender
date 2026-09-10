"""List all cameras in the Blender scene."""

from __future__ import annotations

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success


def list_cameras() -> dict:
    """List all camera objects in the current scene.

    Returns:
        ActionResultModel dict with cameras list.
    """
    try:
        import bpy

        active_camera = bpy.context.scene.camera
        cameras = [
            {
                "name": obj.name,
                "lens": obj.data.lens,
                "type": obj.data.type,
                "ortho_scale": obj.data.ortho_scale,
                "clip_start": obj.data.clip_start,
                "clip_end": obj.data.clip_end,
                "location": list(obj.location),
                "is_active": obj == active_camera,
            }
            for obj in bpy.data.objects
            if obj.type == "CAMERA"
        ]
        return skill_success(
            f"Found {len(cameras)} cameras",
            cameras=cameras,
            count=len(cameras),
            active_camera=active_camera.name if active_camera else None,
            prompt="Use set_active_camera to change the render camera.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message="Failed to list cameras")


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`list_cameras`."""
    return list_cameras(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
