"""Keyframe a bounded camera-data property without evaluating the playhead."""

from __future__ import annotations

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success

from dcc_mcp_blender._animation_ops import action_fcurves
from dcc_mcp_blender._camera_validation import camera_number


def set_camera_keyframe(
    name: str,
    frame: int,
    data_path: str = "lens",
    interpolation: str = "LINEAR",
) -> dict:
    """Insert the current lens or ortho_scale value on the camera data-block.

    Set the value with set_camera_properties first. This operation neither moves
    nor evaluates the playhead; changing frames before insertion could replace
    the newly posed value with an existing animation value. Camera data can be
    shared by multiple objects, so the result reports its name and user count.
    """
    try:
        # Validate before allocating animation data or inserting any key.
        if data_path not in {"lens", "ortho_scale"}:
            return skill_error("Unsupported camera data path", "Use lens or ortho_scale.")
        if interpolation not in {"LINEAR", "BEZIER", "CONSTANT"}:
            return skill_error("Unsupported interpolation", "Use LINEAR, BEZIER, or CONSTANT.")
        if isinstance(frame, bool) or not isinstance(frame, int) or not -1048574 <= frame <= 1048574:
            return skill_error("Invalid frame", "frame must be an integer from -1048574 to 1048574.")
        import bpy

        obj = bpy.data.objects.get(name)
        if obj is None or obj.type != "CAMERA":
            return skill_error("Camera not found", "No camera object named '{}' exists.".format(name))
        camera = obj.data
        if getattr(getattr(camera, "animation_data", None), "use_tweak_mode", False):
            return skill_error(
                "Camera NLA tweak mode is unsupported",
                "Exit NLA tweak mode before keyframing camera data; scene and action times may differ.",
            )
        value = getattr(camera, data_path)
        camera_number(value, data_path)
        if not camera.keyframe_insert(data_path=data_path, frame=frame):
            return skill_error("Camera keyframe was not inserted", "Blender rejected the keyframe insertion.")
        matched = False
        for _, curve in action_fcurves(camera):
            if curve.data_path != data_path:
                continue
            for key in curve.keyframe_points:
                co = key.co
                key_frame = float(co.x if hasattr(co, "x") else co[0])
                if abs(key_frame - frame) < 1e-4:
                    key.interpolation = interpolation
                    matched = True
        if not matched:
            return skill_error(
                "Camera keyframe interpolation was not verified",
                "The key was inserted but its assigned action slot could not be read; inspect camera animation.",
            )
        return skill_success(
            "Camera keyframe set on {} at frame {}".format(name, frame),
            camera_name=name,
            camera_data_name=camera.name,
            camera_data_users=camera.users,
            frame=frame,
            data_path=data_path,
            value=float(value),
            interpolation=interpolation,
            frame_current=int(bpy.context.scene.frame_current),
            prompt=(
                "The playhead was preserved. Use set_current_frame and list_cameras for evaluated readback. "
                "All objects sharing this camera data-block use this animation."
            ),
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message="Failed to keyframe camera: {}".format(name))


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`set_camera_keyframe`."""
    return set_camera_keyframe(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
