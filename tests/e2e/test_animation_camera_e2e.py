"""E2E tests for blender-animation and blender-camera skills.

Requires a real Blender Python interpreter.

Run::

    blender --background --python -m pytest tests/e2e/test_animation_camera_e2e.py -- -v
"""

from __future__ import annotations

import pytest

bpy = pytest.importorskip("bpy", reason="bpy not available — run inside Blender Python interpreter")

pytestmark = pytest.mark.e2e

from dcc_mcp_blender._animation_ops import action_fcurves  # noqa: E402
from tests.e2e.conftest import load_skill  # noqa: E402


def _new_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)


# ── blender-animation ─────────────────────────────────────────────────────────


class TestAnimationSkillsE2E:
    def setup_method(self):
        _new_scene()

    def test_set_and_get_frame_range(self):
        mod_set = load_skill("blender-animation", "set_frame_range")
        result = mod_set.set_frame_range(start=5, end=120)
        assert result["success"] is True
        assert bpy.context.scene.frame_start == 5
        assert bpy.context.scene.frame_end == 120

        mod_get = load_skill("blender-animation", "get_frame_range")
        result = mod_get.get_frame_range()
        assert result["success"] is True
        ctx = result["context"]
        assert ctx["frame_start"] == 5
        assert ctx["frame_end"] == 120

    def test_set_current_frame(self):
        mod = load_skill("blender-animation", "set_current_frame")
        result = mod.set_current_frame(frame=42)
        assert result["success"] is True
        assert bpy.context.scene.frame_current == 42

    def test_set_keyframe_location(self):
        bpy.ops.mesh.primitive_cube_add(location=(0, 0, 0))
        cube_name = bpy.context.active_object.name

        mod = load_skill("blender-animation", "set_keyframe")
        # Keyframe at frame 1
        result = mod.set_keyframe(object_name=cube_name, frame=1, data_paths=["location"])
        assert result["success"] is True

        # Move and keyframe at frame 24
        bpy.data.objects[cube_name].location = (5.0, 0.0, 0.0)
        result = mod.set_keyframe(object_name=cube_name, frame=24, data_paths=["location"])
        assert result["success"] is True

        # Verify action was created
        obj = bpy.data.objects[cube_name]
        assert obj.animation_data is not None
        assert obj.animation_data.action is not None

    def test_set_keyframe_all_transforms(self):
        bpy.ops.mesh.primitive_cube_add()
        cube_name = bpy.context.active_object.name
        mod = load_skill("blender-animation", "set_keyframe")
        result = mod.set_keyframe(
            object_name=cube_name,
            frame=10,
            data_paths=["location", "rotation_euler", "scale"],
        )
        assert result["success"] is True

    def test_set_keyframe_nonexistent_object(self):
        mod = load_skill("blender-animation", "set_keyframe")
        result = mod.set_keyframe(object_name="NonExistent_XYZ", frame=1)
        assert result["success"] is False

    def test_set_keyframe_keeps_the_posed_value(self):
        """PIP-3582: the second key must store the new pose, not the first key's value."""
        bpy.ops.mesh.primitive_cube_add(location=(0, 0, 0))
        cube_name = bpy.context.active_object.name
        obj = bpy.data.objects[cube_name]
        mod = load_skill("blender-animation", "set_keyframe")

        set_current_frame = load_skill("blender-animation", "set_current_frame")
        set_current_frame.set_current_frame(frame=1)
        obj.location = (0.0, 0.0, 0.0)
        assert mod.set_keyframe(object_name=cube_name, frame=1, data_paths=["location"])["success"]

        set_current_frame.set_current_frame(frame=25)
        obj.location = (5.0, 0.0, 0.0)
        assert mod.set_keyframe(object_name=cube_name, frame=25, data_paths=["location"])["success"]

        fcurve = next(fc for _coll, fc in action_fcurves(obj) if fc.data_path == "location" and fc.array_index == 0)
        values = {round(kp.co.x): kp.co.y for kp in fcurve.keyframe_points}
        assert values[1] == pytest.approx(0.0)
        assert values[25] == pytest.approx(5.0)

    def test_animation_is_evaluated_at_intermediate_frames(self):
        """PIP-3582: moving the playhead must evaluate the fcurves, not hold frame 1."""
        bpy.ops.mesh.primitive_cube_add(location=(0, 0, 0))
        cube_name = bpy.context.active_object.name
        obj = bpy.data.objects[cube_name]

        set_current_frame = load_skill("blender-animation", "set_current_frame")
        set_keyframe = load_skill("blender-animation", "set_keyframe")

        set_current_frame.set_current_frame(frame=1)
        obj.location = (0.0, 0.0, 0.0)
        set_keyframe.set_keyframe(object_name=cube_name, frame=1, data_paths=["location"], interpolation="LINEAR")

        set_current_frame.set_current_frame(frame=49)
        obj.location = (48.0, 0.0, 0.0)
        set_keyframe.set_keyframe(object_name=cube_name, frame=49, data_paths=["location"], interpolation="LINEAR")

        for frame, expected in ((1, 0.0), (13, 12.0), (25, 24.0), (37, 36.0), (49, 48.0)):
            set_current_frame.set_current_frame(frame=frame)
            assert bpy.context.scene.frame_current == frame
            assert obj.location.x == pytest.approx(expected, abs=1e-4), f"frame {frame}"

    def test_frame_range_invalid_order(self):
        mod = load_skill("blender-animation", "set_frame_range")
        result = mod.set_frame_range(start=100, end=10)
        assert result["success"] is False


# ── blender-camera ────────────────────────────────────────────────────────────


class TestCameraSkillsE2E:
    def setup_method(self):
        _new_scene()

    def test_create_camera(self):
        mod = load_skill("blender-camera", "create_camera")
        result = mod.create_camera(name="E2ECam")
        assert result["success"] is True
        assert "E2ECam" in bpy.data.objects
        assert bpy.data.objects["E2ECam"].type == "CAMERA"

    def test_create_camera_with_lens(self):
        mod = load_skill("blender-camera", "create_camera")
        result = mod.create_camera(name="TeleCam", lens=85.0)
        assert result["success"] is True
        cam_data = bpy.data.objects["TeleCam"].data
        assert abs(cam_data.lens - 85.0) < 0.1

    def test_create_camera_set_active(self):
        mod = load_skill("blender-camera", "create_camera")
        result = mod.create_camera(name="ActiveCam", set_as_active=True)
        assert result["success"] is True
        assert bpy.context.scene.camera is not None
        assert bpy.context.scene.camera.name == "ActiveCam"

    def test_set_active_camera(self):
        bpy.ops.object.camera_add()
        cam_name = bpy.context.active_object.name
        mod = load_skill("blender-camera", "set_active_camera")
        result = mod.set_active_camera(name=cam_name)
        assert result["success"] is True
        assert bpy.context.scene.camera.name == cam_name

    def test_set_active_camera_not_found(self):
        mod = load_skill("blender-camera", "set_active_camera")
        result = mod.set_active_camera(name="NoSuchCamera_XYZ")
        assert result["success"] is False

    def test_set_camera_properties_lens(self):
        bpy.ops.object.camera_add()
        cam_name = bpy.context.active_object.name
        mod = load_skill("blender-camera", "set_camera_properties")
        result = mod.set_camera_properties(name=cam_name, lens=50.0)
        assert result["success"] is True
        assert abs(bpy.data.objects[cam_name].data.lens - 50.0) < 0.1

    def test_set_camera_type_ortho(self):
        bpy.ops.object.camera_add()
        cam_name = bpy.context.active_object.name
        mod = load_skill("blender-camera", "set_camera_properties")
        result = mod.set_camera_properties(name=cam_name, camera_type="ORTHO")
        assert result["success"] is True
        assert bpy.data.objects[cam_name].data.type == "ORTHO"

    def test_list_cameras(self):
        bpy.ops.object.camera_add()
        bpy.ops.object.camera_add()
        mod = load_skill("blender-camera", "list_cameras")
        result = mod.list_cameras()
        assert result["success"] is True
        assert result["context"]["count"] >= 2

    def test_list_cameras_empty_scene(self):
        mod = load_skill("blender-camera", "list_cameras")
        result = mod.list_cameras()
        assert result["success"] is True
        assert result["context"]["count"] == 0
