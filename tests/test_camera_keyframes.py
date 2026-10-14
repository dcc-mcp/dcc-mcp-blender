"""Camera optics keyframes are distinct from object-transform keyframes."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from tests.conftest import load_and_call, make_mock_bpy


def camera_fixture():
    bpy = make_mock_bpy()
    key = SimpleNamespace(co=(24.0, 85.0), interpolation="BEZIER")
    other = SimpleNamespace(co=(1.0, 35.0), interpolation="BEZIER")
    curve = SimpleNamespace(data_path="lens", keyframe_points=[other, key])
    camera = SimpleNamespace(
        name="SharedOptics",
        users=2,
        lens=85.0,
        ortho_scale=4.0,
        keyframe_insert=MagicMock(return_value=True),
        animation_data=SimpleNamespace(action=SimpleNamespace(is_action_layered=False, fcurves=[curve])),
    )
    obj = SimpleNamespace(name="Camera", type="CAMERA", data=camera)
    bpy.data.objects.get.return_value = obj
    bpy.context.scene.frame_current = 7
    return bpy, obj, key, other, curve


def call(bpy, **kwargs):
    return load_and_call("blender-camera/scripts/set_camera_keyframe.py", bpy, name="Camera", **kwargs)


def test_keys_camera_data_without_evaluating_scene_or_other_keys():
    bpy, obj, key, other, _ = camera_fixture()
    result = call(bpy, frame=24)
    assert result["success"] is True
    obj.data.keyframe_insert.assert_called_once_with(data_path="lens", frame=24)
    bpy.context.scene.frame_set.assert_not_called()
    assert key.interpolation == "LINEAR"
    assert other.interpolation == "BEZIER"
    assert result["context"]["value"] == 85.0
    assert result["context"]["frame_current"] == 7
    assert result["context"]["camera_data_users"] == 2


def test_orthographic_property_and_constant_interpolation():
    bpy, obj, key, _, curve = camera_fixture()
    curve.data_path = "ortho_scale"
    result = call(bpy, frame=24, data_path="ortho_scale", interpolation="CONSTANT")
    assert result["success"] is True
    obj.data.keyframe_insert.assert_called_once_with(data_path="ortho_scale", frame=24)
    assert result["context"]["value"] == 4.0
    assert key.interpolation == "CONSTANT"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"frame": True},
        {"frame": 1.5},
        {"frame": 1048575},
        {"frame": -1048575},
        {"frame": float("nan")},
        {"frame": 24, "data_path": "location"},
        {"frame": 24, "data_path": "dof.focus_distance"},
        {"frame": 24, "interpolation": "EASE"},
    ],
)
def test_invalid_request_does_not_insert(kwargs):
    bpy, obj, _, _, _ = camera_fixture()
    assert call(bpy, **kwargs)["success"] is False
    obj.data.keyframe_insert.assert_not_called()


def test_invalid_current_property_does_not_insert():
    bpy, obj, _, _, _ = camera_fixture()
    obj.data.lens = float("inf")
    assert call(bpy, frame=24)["success"] is False
    obj.data.keyframe_insert.assert_not_called()


@pytest.mark.parametrize("kind", ["missing", "MESH"])
def test_requires_camera(kind):
    bpy, obj, _, _, _ = camera_fixture()
    if kind == "missing":
        bpy.data.objects.get.return_value = None
    else:
        obj.type = kind
    assert call(bpy, frame=24)["success"] is False
    obj.data.keyframe_insert.assert_not_called()


def test_native_insertion_failure_is_not_success():
    bpy, obj, key, _, _ = camera_fixture()
    obj.data.keyframe_insert.return_value = False
    assert call(bpy, frame=24)["success"] is False
    assert key.interpolation == "BEZIER"


def test_nla_tweak_mode_is_rejected_before_inserting_or_editing_keys():
    bpy, obj, key, other, _ = camera_fixture()
    obj.data.animation_data.use_tweak_mode = True
    result = call(bpy, frame=24)
    assert result["success"] is False
    assert "tweak mode" in result["message"]
    obj.data.keyframe_insert.assert_not_called()
    assert key.interpolation == other.interpolation == "BEZIER"


def test_unreadable_inserted_key_is_reported_as_partial_failure():
    bpy, obj, _, _, _ = camera_fixture()
    obj.data.animation_data.action.fcurves = []
    result = call(bpy, frame=24)
    assert result["success"] is False
    assert "not verified" in result["message"]
