"""Real Blender tests for camera-data keyframes and intermediate evaluation."""

import pytest

bpy = pytest.importorskip("bpy", reason="Requires Blender")
pytestmark = pytest.mark.e2e

from dcc_mcp_blender._animation_ops import action_fcurves  # noqa: E402
from tests.e2e.conftest import load_skill  # noqa: E402


@pytest.mark.parametrize("data_path,values", [("lens", (35.0, 85.0)), ("ortho_scale", (8.0, 4.0))])
def test_camera_optics_evaluate_and_survive_reopen(tmp_path, data_path, values):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    create = load_skill("blender-camera", "create_camera")
    keyframe = load_skill("blender-camera", "set_camera_keyframe")
    assert create.create_camera(name="Optics", set_as_active=True)["success"]
    camera = bpy.data.objects["Optics"].data
    if data_path == "ortho_scale":
        camera.type = "ORTHO"
    bpy.context.scene.frame_set(7)
    for frame, value in ((1, values[0]), (25, values[1])):
        setattr(camera, data_path, value)
        result = keyframe.set_camera_keyframe(name="Optics", frame=frame, data_path=data_path)
        assert result["success"], result
        assert bpy.context.scene.frame_current == 7
    bpy.context.scene.frame_set(13)
    assert getattr(camera, data_path) == pytest.approx(sum(values) / 2)
    curve = next(fc for _, fc in action_fcurves(camera) if fc.data_path == data_path)
    assert {kp.interpolation for kp in curve.keyframe_points} == {"LINEAR"}
    path = str(tmp_path / "optics.blend")
    bpy.ops.wm.save_as_mainfile(filepath=path)
    bpy.ops.wm.open_mainfile(filepath=path)
    bpy.context.scene.frame_set(25)
    assert getattr(bpy.data.objects["Optics"].data, data_path) == pytest.approx(values[1])


def test_camera_keys_use_own_layered_slot_and_preserve_object_animation():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    load_skill("blender-camera", "create_camera").create_camera(name="Optics")
    obj = bpy.data.objects["Optics"]
    obj.location.x = 3
    obj.keyframe_insert(data_path="location", frame=1)
    obj.data.lens = 70
    result = load_skill("blender-camera", "set_camera_keyframe").set_camera_keyframe(
        name="Optics", frame=10, interpolation="CONSTANT"
    )
    assert result["success"], result
    assert {fc.data_path for _, fc in action_fcurves(obj)} == {"location"}
    assert {fc.data_path for _, fc in action_fcurves(obj.data)} == {"lens"}


def test_invalid_camera_key_does_not_allocate_animation_data():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    load_skill("blender-camera", "create_camera").create_camera(name="Optics")
    camera = bpy.data.objects["Optics"].data
    result = load_skill("blender-camera", "set_camera_keyframe").set_camera_keyframe(
        name="Optics", frame=10, data_path="location"
    )
    assert result["success"] is False
    assert camera.animation_data is None


def test_camera_nla_tweak_mode_rejects_unmapped_scene_time():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    load_skill("blender-camera", "create_camera").create_camera(name="Optics")
    camera = bpy.data.objects["Optics"].data
    camera.lens = 35
    camera.keyframe_insert(data_path="lens", frame=1)
    camera.lens = 85
    camera.keyframe_insert(data_path="lens", frame=25)
    data = camera.animation_data
    action, slot = data.action, data.action_slot
    track = data.nla_tracks.new()
    strip = track.strips.new("Offset", 101, action)
    strip.action_slot = slot
    data.action = None
    track.select = strip.select = True
    data.use_tweak_mode = True
    assert data.use_tweak_mode is True
    try:
        curves = list(action_fcurves(camera))
        before = [(tuple(key.co), key.interpolation) for _, curve in curves for key in curve.keyframe_points]
        result = load_skill("blender-camera", "set_camera_keyframe").set_camera_keyframe(name="Optics", frame=113)
        assert result["success"] is False
        assert "tweak mode" in result["message"]
        after = [(tuple(key.co), key.interpolation) for _, curve in curves for key in curve.keyframe_points]
        assert after == before
    finally:
        data.use_tweak_mode = False


def test_shared_layered_action_keeps_other_camera_slot_unchanged():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    create = load_skill("blender-camera", "create_camera")
    create.create_camera(name="First")
    create.create_camera(name="Second")
    first, second = bpy.data.objects["First"].data, bpy.data.objects["Second"].data
    first.lens = 35
    first.keyframe_insert(data_path="lens", frame=1)
    action = first.animation_data.action
    second.animation_data_create()
    second.animation_data.action = action
    second.animation_data.action_slot = action.slots.new(id_type="CAMERA", name="SecondOptics")
    second.lens = 85
    result = load_skill("blender-camera", "set_camera_keyframe").set_camera_keyframe(
        name="Second", frame=1, interpolation="CONSTANT"
    )
    assert result["success"], result
    first_key = next(curve for _, curve in action_fcurves(first)).keyframe_points[0]
    second_key = next(curve for _, curve in action_fcurves(second)).keyframe_points[0]
    assert first_key.co.y == pytest.approx(35)
    assert first_key.interpolation == "BEZIER"
    assert second_key.co.y == pytest.approx(85)
    assert second_key.interpolation == "CONSTANT"
