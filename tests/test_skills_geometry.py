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


def test_export_fbx_calls_export_scene():
    mock_bpy = make_mock_bpy()
    mock_bpy.ops.export_scene = MagicMock()

    result = load_and_call("blender-geometry/scripts/export_fbx.py", mock_bpy, path="/tmp/out.fbx")

    assert result["success"] is True
    mock_bpy.ops.export_scene.fbx.assert_called_once_with(filepath="/tmp/out.fbx")


def test_export_obj_prefers_blender_3_plus_operator(tmp_path):
    mock_bpy = make_mock_bpy()
    mock_bpy.ops.wm.obj_export.side_effect = lambda filepath: open(filepath, "w", encoding="utf-8").write("obj")
    out_path = tmp_path / "out.obj"

    result = load_and_call("blender-geometry/scripts/export_obj.py", mock_bpy, path=str(out_path))

    assert result["success"] is True
    mock_bpy.ops.wm.obj_export.assert_called_once_with(filepath=str(out_path))


def test_export_obj_writes_basic_obj_when_operator_context_fails(tmp_path):
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

    assert result["success"] is True
    assert out_path.read_text(encoding="utf-8").splitlines() == [
        "# Exported by dcc-mcp-blender",
        "o Triangle",
        "v 0 0 0",
        "v 1 0 0",
        "v 0 1 0",
        "f 1 2 3",
    ]


def test_export_obj_writes_basic_obj_when_operator_creates_no_file(tmp_path):
    mock_bpy = make_mock_bpy()
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

    assert result["success"] is True
    assert "f 1 2 3" in out_path.read_text(encoding="utf-8")
