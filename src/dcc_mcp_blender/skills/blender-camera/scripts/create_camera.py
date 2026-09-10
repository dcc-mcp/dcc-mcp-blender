"""Create a new camera in Blender."""

from __future__ import annotations

from typing import List, Optional

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success

from dcc_mcp_blender._camera_validation import camera_location, positive_number


def create_camera(
    name: Optional[str] = None,
    location: Optional[List[float]] = None,
    lens: float = 50.0,
    set_as_active: bool = False,
) -> dict:
    """Create a new camera object.

    Args:
        name: Optional name for the camera.
        location: [x, y, z] position. Defaults to [0, -8, 3].
        lens: Focal length in mm (default 50mm).
        set_as_active: If True, set this camera as the active scene camera.

    Returns:
        ActionResultModel dict.
    """
    try:
        import bpy

        loc = location if location is not None else [0.0, -8.0, 3.0]
        positive_number(lens, "lens")
        camera_location(loc)
        cam_data = bpy.data.cameras.new(name=name or "Camera")
        cam_data.lens = lens

        obj = bpy.data.objects.new(name=name or cam_data.name, object_data=cam_data)
        obj.location = loc
        bpy.context.scene.collection.objects.link(obj)

        if set_as_active:
            bpy.context.scene.camera = obj

        return skill_success(
            f"Created camera: {obj.name}",
            object_name=obj.name,
            lens=lens,
            location=loc,
            is_active=set_as_active,
            prompt="Camera created. Use set_active_camera to make it the render camera.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message="Failed to create camera")


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`create_camera`."""
    return create_camera(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
