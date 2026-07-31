"""Unit tests for blender-animation skill scripts (bpy mocked)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from tests.conftest import load_and_call, make_mock_bpy


class TestSetKeyframe:
    def test_inserts_default_paths(self):
        bpy = make_mock_bpy()
        obj = MagicMock()
        obj.name = "Cube"
        bpy.data.objects.get.return_value = obj
        bpy.context.scene.frame_current = 1

        result = load_and_call(
            "blender-animation/scripts/set_keyframe.py",
            bpy,
            object_name="Cube",
            frame=1,
        )
        assert result["success"] is True
        # Should have inserted keyframes for location, rotation_euler, scale
        assert obj.keyframe_insert.call_count == 3

    def test_custom_data_paths(self):
        bpy = make_mock_bpy()
        obj = MagicMock()
        bpy.data.objects.get.return_value = obj
        bpy.context.preferences.edit.keyframe_new_interpolation_type = "BEZIER"

        result = load_and_call(
            "blender-animation/scripts/set_keyframe.py",
            bpy,
            object_name="Cube",
            frame=10,
            data_paths=["location"],
            interpolation="LINEAR",
        )
        assert result["success"] is True
        assert obj.keyframe_insert.call_count == 1
        assert result["context"]["interpolation"] == "LINEAR"
        assert bpy.context.preferences.edit.keyframe_new_interpolation_type == "BEZIER"

    def test_applies_interpolation_to_inserted_key(self):
        bpy = make_mock_bpy()
        key = SimpleNamespace(co=(10.0, 1.0), interpolation="BEZIER")
        curve = SimpleNamespace(data_path="location", keyframe_points=[key])
        obj = MagicMock()
        obj.animation_data = SimpleNamespace(action=SimpleNamespace(fcurves=[curve]))
        bpy.data.objects.get.return_value = obj
        bpy.context.scene.frame_current = 10

        result = load_and_call(
            "blender-animation/scripts/set_keyframe.py",
            bpy,
            object_name="Cube",
            frame=10,
            data_paths=["location"],
            interpolation="LINEAR",
        )

        assert result["success"] is True
        assert key.interpolation == "LINEAR"

    def test_object_not_found(self):
        bpy = make_mock_bpy()
        bpy.data.objects.get.return_value = None

        result = load_and_call(
            "blender-animation/scripts/set_keyframe.py",
            bpy,
            object_name="Ghost",
        )
        assert result["success"] is False


class TestSetFrameRange:
    def test_sets_start_and_end(self):
        bpy = make_mock_bpy()
        result = load_and_call("blender-animation/scripts/set_frame_range.py", bpy, start=1, end=120)
        assert result["success"] is True
        assert bpy.context.scene.frame_start == 1
        assert bpy.context.scene.frame_end == 120

    def test_invalid_range_returns_error(self):
        bpy = make_mock_bpy()
        result = load_and_call("blender-animation/scripts/set_frame_range.py", bpy, start=100, end=10)
        assert result["success"] is False


class TestGetFrameRange:
    def test_returns_frame_info(self):
        bpy = make_mock_bpy()
        bpy.context.scene.frame_start = 1
        bpy.context.scene.frame_end = 250
        bpy.context.scene.frame_current = 42

        result = load_and_call("blender-animation/scripts/get_frame_range.py", bpy)
        assert result["success"] is True
        ctx = result["context"]
        assert ctx["frame_start"] == 1
        assert ctx["frame_end"] == 250
        assert ctx["frame_current"] == 42


class TestSetCurrentFrame:
    def test_sets_frame(self):
        bpy = make_mock_bpy()
        bpy.context.scene.frame_set = MagicMock()
        bpy.context.scene.frame_current = 50

        result = load_and_call("blender-animation/scripts/set_current_frame.py", bpy, frame=50)
        assert result["success"] is True
        bpy.context.scene.frame_set.assert_called_once_with(50)
