"""Unit tests for blender-camera skill scripts (bpy mocked)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from tests.conftest import load_and_call, make_mock_bpy


def _make_camera_obj(name="Camera"):
    obj = MagicMock()
    obj.name = name
    obj.type = "CAMERA"
    obj.location = [0.0, -8.0, 3.0]
    obj.data = MagicMock()
    obj.data.lens = 50.0
    obj.data.type = "PERSP"
    obj.data.clip_start = 0.1
    obj.data.clip_end = 1000.0
    obj.data.ortho_scale = 6.0
    return obj


class TestCreateCamera:
    @pytest.mark.parametrize(
        "args", [{"lens": 0}, {"lens": float("nan")}, {"location": []}, {"location": [0, 0, float("inf")]}]
    )
    def test_invalid_request_does_not_allocate_camera(self, args):
        bpy = make_mock_bpy()
        result = load_and_call("blender-camera/scripts/create_camera.py", bpy, **args)
        assert result["success"] is False
        bpy.data.cameras.new.assert_not_called()
        bpy.data.objects.new.assert_not_called()

    def test_creates_camera(self):
        bpy = make_mock_bpy()
        cam_data = MagicMock()
        cam_data.name = "Camera"
        bpy.data.cameras.new = MagicMock(return_value=cam_data)

        obj = _make_camera_obj("Camera")
        bpy.data.objects.new.return_value = obj
        bpy.context.scene.collection.objects.link = MagicMock()

        result = load_and_call("blender-camera/scripts/create_camera.py", bpy)
        assert result["success"] is True
        bpy.data.cameras.new.assert_called_once()

    def test_sets_lens(self):
        bpy = make_mock_bpy()
        cam_data = MagicMock()
        bpy.data.cameras.new = MagicMock(return_value=cam_data)
        obj = _make_camera_obj()
        bpy.data.objects.new.return_value = obj
        bpy.context.scene.collection.objects.link = MagicMock()

        load_and_call("blender-camera/scripts/create_camera.py", bpy, lens=85.0)
        assert cam_data.lens == 85.0

    def test_set_as_active(self):
        bpy = make_mock_bpy()
        cam_data = MagicMock()
        bpy.data.cameras.new = MagicMock(return_value=cam_data)
        obj = _make_camera_obj()
        bpy.data.objects.new.return_value = obj
        bpy.context.scene.collection.objects.link = MagicMock()

        result = load_and_call("blender-camera/scripts/create_camera.py", bpy, set_as_active=True)
        assert result["success"] is True
        assert bpy.context.scene.camera == obj


class TestSetActiveCamera:
    def test_sets_active(self):
        bpy = make_mock_bpy()
        obj = _make_camera_obj("RenderCam")
        bpy.data.objects.get.return_value = obj

        result = load_and_call("blender-camera/scripts/set_active_camera.py", bpy, name="RenderCam")
        assert result["success"] is True
        assert bpy.context.scene.camera == obj

    def test_not_found_returns_error(self):
        bpy = make_mock_bpy()
        bpy.data.objects.get.return_value = None
        result = load_and_call("blender-camera/scripts/set_active_camera.py", bpy, name="Ghost")
        assert result["success"] is False

    def test_non_camera_returns_error(self):
        bpy = make_mock_bpy()
        obj = MagicMock()
        obj.type = "MESH"
        bpy.data.objects.get.return_value = obj
        result = load_and_call("blender-camera/scripts/set_active_camera.py", bpy, name="Cube")
        assert result["success"] is False


class TestSetCameraProperties:
    @pytest.mark.parametrize(
        "args",
        [
            {"lens": 85, "camera_type": "INVALID"},
            {"lens": 85, "clip_start": 1001},
            {"lens": 85, "clip_end": 0.01},
            {"camera_type": "ORTHO", "ortho_scale": -1},
            {"camera_type": "ORTHO", "lens": float("nan")},
            {"lens": 85, "clip_end": float("inf")},
            {"lens": True},
        ],
    )
    def test_invalid_request_preserves_every_property(self, args):
        bpy = make_mock_bpy()
        obj = _make_camera_obj()
        bpy.data.objects.get.return_value = obj
        result = load_and_call("blender-camera/scripts/set_camera_properties.py", bpy, name="Camera", **args)
        assert result["success"] is False
        assert (obj.data.lens, obj.data.type, obj.data.clip_start, obj.data.clip_end, obj.data.ortho_scale) == (
            50,
            "PERSP",
            0.1,
            1000,
            6,
        )

    def test_orthographic_framing_and_clipping_readback(self):
        bpy = make_mock_bpy()
        obj = _make_camera_obj()
        bpy.data.objects.get.return_value = obj
        result = load_and_call(
            "blender-camera/scripts/set_camera_properties.py",
            bpy,
            name="Camera",
            camera_type="ORTHO",
            ortho_scale=3.2,
            clip_start=0.02,
            clip_end=20,
        )
        assert result["success"] is True
        assert result["context"]["ortho_scale"] == 3.2
        assert result["context"]["lens"] == 50
        assert (obj.data.clip_start, obj.data.clip_end) == (0.02, 20)

    def test_set_lens(self):
        bpy = make_mock_bpy()
        obj = _make_camera_obj()
        bpy.data.objects.get.return_value = obj

        result = load_and_call("blender-camera/scripts/set_camera_properties.py", bpy, name="Camera", lens=35.0)
        assert result["success"] is True
        assert obj.data.lens == 35.0

    def test_set_type(self):
        bpy = make_mock_bpy()
        obj = _make_camera_obj()
        bpy.data.objects.get.return_value = obj

        result = load_and_call(
            "blender-camera/scripts/set_camera_properties.py",
            bpy,
            name="Camera",
            camera_type="ORTHO",
        )
        assert result["success"] is True
        assert obj.data.type == "ORTHO"

    def test_invalid_type_returns_error(self):
        bpy = make_mock_bpy()
        obj = _make_camera_obj()
        bpy.data.objects.get.return_value = obj

        result = load_and_call(
            "blender-camera/scripts/set_camera_properties.py",
            bpy,
            name="Camera",
            camera_type="INVALID",
        )
        assert result["success"] is False


class TestListCameras:
    def test_returns_cameras_only(self):
        bpy = make_mock_bpy()
        cam = _make_camera_obj("MainCam")
        mesh = MagicMock()
        mesh.type = "MESH"
        bpy.data.objects = [cam, mesh]
        bpy.context.scene.camera = cam

        result = load_and_call("blender-camera/scripts/list_cameras.py", bpy)
        assert result["success"] is True
        assert result["context"]["count"] == 1
        assert result["context"]["cameras"][0]["is_active"] is True

    def test_empty_returns_zero(self):
        bpy = make_mock_bpy(data_attrs={"objects": []})
        result = load_and_call("blender-camera/scripts/list_cameras.py", bpy)
        assert result["success"] is True
        assert result["context"]["count"] == 0
