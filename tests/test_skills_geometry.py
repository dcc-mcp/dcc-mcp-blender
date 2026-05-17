"""Tests for the blender-geometry skill."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from conftest import load_and_call, make_mock_bpy


def test_create_sphere_calls_bpy_operator():
    active = SimpleNamespace(name="Sphere", data=SimpleNamespace(name="Sphere"))
    mock_bpy = make_mock_bpy(context_attrs={"active_object": active})

    result = load_and_call(
        "blender-geometry/scripts/create_sphere.py",
        mock_bpy,
        radius=2.5,
        name="CI Sphere",
        location=[1.0, 2.0, 3.0],
    )

    assert result["success"] is True
    assert result["context"]["object_name"] == "CI Sphere"
    assert result["context"]["thread_ident"] > 0
    mock_bpy.ops.mesh.primitive_uv_sphere_add.assert_called_once_with(radius=2.5, location=[1.0, 2.0, 3.0])


def test_save_blend_calls_save_as_mainfile():
    mock_bpy = make_mock_bpy()

    result = load_and_call("blender-geometry/scripts/save_blend.py", mock_bpy, path="/tmp/out.blend")

    assert result["success"] is True
    assert result["context"]["filepath"] == "/tmp/out.blend"
    mock_bpy.ops.wm.save_as_mainfile.assert_called_once_with(filepath="/tmp/out.blend")


def test_file_exists_reports_size(tmp_path):
    target = tmp_path / "asset.fbx"
    target.write_bytes(b"fbx")

    result = load_and_call("blender-geometry/scripts/file_exists.py", None, path=str(target))

    assert result["success"] is True
    assert result["context"]["exists"] is True
    assert result["context"]["size"] == 3


def test_export_fbx_calls_export_scene():
    mock_bpy = make_mock_bpy()
    mock_bpy.ops.export_scene = MagicMock()

    result = load_and_call("blender-geometry/scripts/export_fbx.py", mock_bpy, path="/tmp/out.fbx")

    assert result["success"] is True
    mock_bpy.ops.export_scene.fbx.assert_called_once_with(filepath="/tmp/out.fbx")


def test_export_obj_prefers_blender_3_plus_operator():
    mock_bpy = make_mock_bpy()

    result = load_and_call("blender-geometry/scripts/export_obj.py", mock_bpy, path="/tmp/out.obj")

    assert result["success"] is True
    mock_bpy.ops.wm.obj_export.assert_called_once_with(filepath="/tmp/out.obj")
