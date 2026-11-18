"""Tests for the physical photographic camera skill."""

from __future__ import annotations

from types import SimpleNamespace

import yaml

from tests.conftest import load_and_call

SKILL_DIR = "blender-photographic-camera"


class _Dof:
    def __init__(self):
        self.use_dof = False
        self.aperture_fstop = 8.0
        self.aperture_blades = 6
        self.aperture_ratio = 1.5
        self.focus_object = None
        self.focus_distance = 10.0


class _CameraData:
    def __init__(self):
        self.type = "PERSP"
        self.lens = 50.0
        self.sensor_width = 36.0
        self.dof = _Dof()


class _Camera:
    def __init__(self, name="Camera"):
        self.name = name
        self.type = "CAMERA"
        self.data = _CameraData()
        self.location = [0.0, -0.5, 0.04]
        self.rotation_euler = [0.0, 0.0, 0.0]
        self.rotation_mode = "XYZ"
        self.keyframes = []
        self.animation_data = None

    def keyframe_insert(self, data_path, frame):
        self.keyframes.append(
            {
                "data_path": data_path,
                "frame": frame,
                "value": list(getattr(self, data_path)),
            }
        )
        return True


class _Objects:
    def __init__(self, objects):
        self._objects = {obj.name: obj for obj in objects}

    def get(self, name):
        return self._objects.get(name)


def _bpy(camera=None, focus=None):
    camera = camera or _Camera()
    objects = [camera]
    if focus is not None:
        objects.append(focus)
    return SimpleNamespace(
        data=SimpleNamespace(objects=_Objects(objects)),
        context=SimpleNamespace(scene=SimpleNamespace(frame_current=12)),
    )


def _call(script, bpy, **kwargs):
    return load_and_call(f"{SKILL_DIR}/scripts/{script}.py", bpy, **kwargs)


def test_configure_sets_physical_camera_and_eye_focus():
    camera = _Camera()
    eyes = SimpleNamespace(name="ToyEyes", type="EMPTY")

    result = _call(
        "configure_photographic_camera",
        _bpy(camera, eyes),
        camera_name="Camera",
        shot_type="CHARACTER",
        lens=85,
        aperture_fstop=5.6,
        focus_object="ToyEyes",
        camera_height_cm=3.0,
    )

    assert result["success"] is True, result
    assert camera.data.type == "PERSP"
    assert camera.data.sensor_width == 36.0
    assert camera.data.lens == 85.0
    assert camera.location[2] == 0.03
    assert camera.data.dof.use_dof is True
    assert camera.data.dof.aperture_fstop == 5.6
    assert camera.data.dof.aperture_blades == 0
    assert camera.data.dof.focus_object is eyes


def test_wide_shot_requires_f11():
    camera = _Camera()
    result = _call(
        "configure_photographic_camera",
        _bpy(camera),
        camera_name="Camera",
        shot_type="WIDE",
        aperture_fstop=5.6,
    )

    assert result["success"] is False
    assert camera.data.dof.aperture_fstop == 8.0


def test_invalid_lens_and_height_do_not_mutate_camera():
    camera = _Camera()
    before = (camera.data.lens, camera.location[2])
    result = _call(
        "configure_photographic_camera",
        _bpy(camera),
        camera_name="Camera",
        lens=20,
        camera_height_cm=10,
    )

    assert result["success"] is False
    assert (camera.data.lens, camera.location[2]) == before


def test_animation_adds_eased_endpoint_keys_and_unwraps_rotation():
    camera = _Camera()
    result = _call(
        "animate_photographic_camera",
        _bpy(camera),
        camera_name="Camera",
        frame_start=10,
        frame_end=20,
        start_location=[0, -1, 0.04],
        end_location=[0.1, -0.8, 0.04],
        start_rotation_degrees=[0, 0, 179],
        end_rotation_degrees=[0, 0, -179],
        interpolation="BEZIER",
    )

    assert result["success"] is True, result
    assert result["context"]["keyframe_frames"] == [9, 10, 20, 21]
    rotation_keys = [key for key in camera.keyframes if key["data_path"] == "rotation_euler"]
    assert len(rotation_keys) == 4
    assert result["context"]["end_rotation_degrees"][2] == 181.0
    assert result["context"]["camera_shake_added"] is False


def test_validation_reports_missing_focus_and_animation_without_mutating():
    camera = _Camera()
    camera.data.dof.use_dof = True
    camera.data.dof.aperture_fstop = 4.0
    camera.data.dof.aperture_blades = 0

    result = _call(
        "validate_photographic_camera",
        _bpy(camera),
        camera_name="Camera",
        frame_start=10,
        frame_end=20,
    )

    assert result["success"] is True
    assert result["context"]["valid"] is False
    codes = {issue["code"] for issue in result["context"]["issues"]}
    assert "CAMERA_FOCUS_OBJECT_MISSING" in codes
    assert "CAMERA_ENDPOINT_EXTENSION_MISSING" in codes
    assert camera.location[2] == 0.04


def test_camera_validation_rejects_noise_modifiers_as_camera_shake():
    camera = _Camera()
    curve = SimpleNamespace(
        data_path="location",
        array_index=0,
        modifiers=[SimpleNamespace(type="NOISE")],
        keyframe_points=[],
    )
    camera.animation_data = SimpleNamespace(action=SimpleNamespace(fcurves=[curve]))

    result = _call(
        "validate_photographic_camera",
        _bpy(camera),
        camera_name="Camera",
    )

    assert result["success"] is True
    assert any(issue["code"] == "CAMERA_SHAKE_DETECTED" for issue in result["context"]["issues"])


def test_tools_yaml_declares_the_photographic_camera_contract():
    from pathlib import Path

    path = Path("src/dcc_mcp_blender/skills/blender-photographic-camera/tools.yaml")
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    tools = {tool["name"]: tool for tool in doc["tools"]}
    assert set(tools) == {
        "configure_photographic_camera",
        "animate_photographic_camera",
        "validate_photographic_camera",
    }
    assert tools["configure_photographic_camera"]["input_schema"]["properties"]["lens"]["minimum"] == 24.0
