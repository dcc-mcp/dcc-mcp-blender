"""Configure Blender camera properties."""

from __future__ import annotations

from typing import Optional

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success

from dcc_mcp_blender._camera_validation import positive_number

VALID_CAMERA_TYPES = {"PERSP", "ORTHO", "PANO"}


def set_camera_properties(
    name: str,
    lens: Optional[float] = None,
    camera_type: Optional[str] = None,
    clip_start: Optional[float] = None,
    clip_end: Optional[float] = None,
    ortho_scale: Optional[float] = None,
) -> dict:
    """Configure camera data properties.

    Args:
        name: Name of the camera object.
        lens: Focal length in mm; does not change orthographic framing.
        camera_type: Camera projection type: PERSP, ORTHO, or PANO.
        clip_start: Near clipping distance.
        clip_end: Far clipping distance.
        ortho_scale: Orthographic view width in scene units.

    Returns:
        ActionResultModel dict.
    """
    try:
        import bpy

        obj = bpy.data.objects.get(name)
        if obj is None:
            return skill_error(f"Object not found: {name}", f"No object named '{name}'.")
        if obj.type != "CAMERA":
            return skill_error(f"{name} is not a camera", f"Object type is {obj.type}.")

        cam = obj.data
        # Validate the entire request before applying any field.
        if camera_type is not None:
            camera_type = camera_type.upper()
            if camera_type not in VALID_CAMERA_TYPES:
                return skill_error(
                    f"Invalid camera type: {camera_type}",
                    f"Valid types: {', '.join(sorted(VALID_CAMERA_TYPES))}",
                )
        for key, value in (
            ("lens", lens),
            ("clip_start", clip_start),
            ("clip_end", clip_end),
            ("ortho_scale", ortho_scale),
        ):
            if value is not None:
                positive_number(value, key)
        near = clip_start if clip_start is not None else cam.clip_start
        far = clip_end if clip_end is not None else cam.clip_end
        if (clip_start is not None or clip_end is not None) and near >= far:
            return skill_error("Invalid clipping range", "clip_start must be less than clip_end.")

        if lens is not None:
            cam.lens = lens
        if camera_type is not None:
            cam.type = camera_type
        if clip_start is not None:
            cam.clip_start = clip_start
        if clip_end is not None:
            cam.clip_end = clip_end
        if ortho_scale is not None:
            cam.ortho_scale = ortho_scale

        return skill_success(
            f"Camera properties updated: {name}",
            camera_name=name,
            lens=cam.lens,
            camera_type=cam.type,
            clip_start=cam.clip_start,
            clip_end=cam.clip_end,
            ortho_scale=cam.ortho_scale,
            prompt="Camera configured. Use render_scene to render.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to set camera properties: {name}")


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`set_camera_properties`."""
    return set_camera_properties(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
