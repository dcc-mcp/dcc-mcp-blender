"""Tests for the blender-geometry skill."""

from __future__ import annotations

from pathlib import Path
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


def test_create_sphere_uses_context_object_fallback():
    active = SimpleNamespace(name="Sphere", data=SimpleNamespace(name="Sphere"))
    mock_bpy = make_mock_bpy(context_attrs={"active_object": None, "object": active})

    result = load_and_call(
        "blender-geometry/scripts/create_sphere.py",
        mock_bpy,
        radius=1.5,
        name="Fallback Sphere",
    )

    assert result["success"] is True
    assert result["context"]["object_name"] == "Fallback Sphere"


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


def test_export_fbx_calls_export_scene(tmp_path):
    mock_bpy = make_mock_bpy()
    mock_bpy.ops.export_scene = MagicMock()

    target = tmp_path / "out.fbx"

    def write_fbx(filepath, **_kwargs):
        Path(filepath).write_bytes(b"fbx")
        return {"FINISHED"}

    mock_bpy.ops.export_scene.fbx.side_effect = write_fbx
    result = load_and_call("blender-geometry/scripts/export_fbx.py", mock_bpy, path=str(target))

    assert result["success"] is True
    mock_bpy.ops.export_scene.fbx.assert_called_once()
    _, kwargs = mock_bpy.ops.export_scene.fbx.call_args
    assert Path(kwargs["filepath"]).name == "out.fbx"
    assert kwargs["use_selection"] is False


def test_export_obj_prefers_blender_3_plus_operator(tmp_path):
    mock_bpy = make_mock_bpy()

    def write_obj(filepath, **_kwargs):
        Path(filepath).write_text("obj", encoding="utf-8")
        return {"FINISHED"}

    mock_bpy.ops.wm.obj_export.side_effect = write_obj
    out_path = tmp_path / "out.obj"

    result = load_and_call("blender-geometry/scripts/export_obj.py", mock_bpy, path=str(out_path))

    assert result["success"] is True
    mock_bpy.ops.wm.obj_export.assert_called_once_with(filepath=str(out_path), export_selected_objects=False)


def test_export_obj_reports_native_context_failure(tmp_path):
    mock_bpy = make_mock_bpy()
    mock_bpy.ops.wm.obj_export.side_effect = RuntimeError("context is incorrect")
    mesh = SimpleNamespace(
        vertices=[
            SimpleNamespace(co=(0.0, 0.0, 0.0)),
            SimpleNamespace(co=(1.0, 0.0, 0.0)),
            SimpleNamespace(co=(0.0, 1.0, 0.0)),
        ],
        polygons=[SimpleNamespace(vertices=[0, 1, 2])],
    )
    mock_bpy.data.objects = [SimpleNamespace(name="Triangle", type="MESH", data=mesh)]
    out_path = tmp_path / "fallback.obj"

    result = load_and_call("blender-geometry/scripts/export_obj.py", mock_bpy, path=str(out_path))

    assert result["success"] is False
    assert not out_path.exists()
    mock_bpy.ops.wm.obj_export.assert_called_once()


def test_export_obj_reports_missing_native_output(tmp_path):
    mock_bpy = make_mock_bpy()
    mock_bpy.ops.wm.obj_export.return_value = {"FINISHED"}
    mesh = SimpleNamespace(
        vertices=[
            SimpleNamespace(co=(0.0, 0.0, 0.0)),
            SimpleNamespace(co=(1.0, 0.0, 0.0)),
            SimpleNamespace(co=(0.0, 1.0, 0.0)),
        ],
        polygons=[SimpleNamespace(vertices=[0, 1, 2])],
    )
    mock_bpy.data.objects = [SimpleNamespace(name="Triangle", type="MESH", data=mesh)]
    out_path = tmp_path / "fallback.obj"

    result = load_and_call("blender-geometry/scripts/export_obj.py", mock_bpy, path=str(out_path))

    assert result["success"] is False
    assert not out_path.exists()
