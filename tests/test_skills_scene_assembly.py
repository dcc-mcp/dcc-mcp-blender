"""Unit tests for blender-scene-assembly skill scripts (bpy mocked)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import yaml

from tests.conftest import load_and_call, make_mock_bpy

ASSEMBLY_PATH = "src/dcc_mcp_blender/skills/blender-scene-assembly/tools.yaml"


def _make_scene(name="Scene"):
    scene = MagicMock()
    scene.name = name
    scene.view_layers = MagicMock()
    scene.view_layers.__iter__ = MagicMock(return_value=iter([]))
    scene.view_layers.__contains__ = MagicMock(return_value=False)
    scene.view_layers.__len__ = MagicMock(return_value=0)
    return scene


def test_list_view_layers_default():
    bpy = make_mock_bpy()
    scene = _make_scene("Scene")
    bpy.context.scene = scene
    bpy.data.scenes.__iter__ = MagicMock(return_value=iter([]))

    result = load_and_call("blender-scene-assembly/scripts/list_view_layers.py", bpy)
    assert result["success"] is True


def test_list_external_references_empty():
    bpy = make_mock_bpy()
    bpy.data.libraries = MagicMock()
    bpy.data.libraries.__iter__ = MagicMock(return_value=iter([]))

    result = load_and_call("blender-scene-assembly/scripts/list_external_references.py", bpy)
    assert result["success"] is True
    assert result["context"]["count"] == 0


def test_merge_scene_file_not_found():
    bpy = make_mock_bpy()

    result = load_and_call("blender-scene-assembly/scripts/merge_scene.py", bpy, filepath="/nonexistent/file.blend")
    assert result["success"] is False
    assert "not found" in result["message"].lower()


def test_append_from_blend_file_not_found():
    bpy = make_mock_bpy()

    result = load_and_call(
        "blender-scene-assembly/scripts/append_from_blend.py",
        bpy,
        filepath="/nonexistent/file.blend",
        data_type="objects",
    )
    assert result["success"] is False


def test_append_from_blend_invalid_type():
    bpy = make_mock_bpy()

    result = load_and_call(
        "blender-scene-assembly/scripts/append_from_blend.py",
        bpy,
        filepath="/some/path.blend",
        data_type="invalid_type",
    )
    assert result["success"] is False


def test_create_view_layer():
    bpy = make_mock_bpy()
    scene = _make_scene("Scene")
    bpy.context.scene = scene
    bpy.data.scenes.get = MagicMock(return_value=None)

    new_vl = MagicMock()
    new_vl.name = "NewLayer"
    scene.view_layers.new = MagicMock(return_value=new_vl)

    result = load_and_call("blender-scene-assembly/scripts/create_view_layer.py", bpy, name="NewLayer")
    assert result["success"] is True
    scene.view_layers.new.assert_called_once_with("NewLayer")


def test_remove_view_layer_last_one():
    bpy = make_mock_bpy()
    scene = _make_scene("Scene")
    bpy.context.scene = scene
    scene.view_layers.__len__ = MagicMock(return_value=1)

    result = load_and_call("blender-scene-assembly/scripts/remove_view_layer.py", bpy, name="ViewLayer")
    assert result["success"] is False


def test_set_active_view_layer():
    bpy = make_mock_bpy()
    scene = _make_scene("Scene")
    bpy.context.scene = scene
    bpy.context.window = MagicMock()
    bpy.context.window.view_layer = MagicMock()

    vl = MagicMock()
    vl.name = "RenderLayer"
    scene.view_layers.__contains__ = MagicMock(return_value=True)
    scene.view_layers.__getitem__ = MagicMock(return_value=vl)

    result = load_and_call("blender-scene-assembly/scripts/set_active_view_layer.py", bpy, name="RenderLayer")
    assert result["success"] is True


def test_link_from_blend_file_not_found():
    bpy = make_mock_bpy()

    result = load_and_call(
        "blender-scene-assembly/scripts/link_from_blend.py",
        bpy,
        filepath="/nonexistent/file.blend",
        data_type="objects",
    )
    assert result["success"] is False


def test_tools_yaml_declares_tools():
    doc = yaml.safe_load(Path(ASSEMBLY_PATH).read_text(encoding="utf-8"))
    tools = {tool["name"]: tool for tool in doc["tools"]}
    assert {
        "merge_scene",
        "append_from_blend",
        "link_from_blend",
        "list_view_layers",
        "create_view_layer",
        "remove_view_layer",
        "set_active_view_layer",
        "list_external_references",
    }.issubset(tools)
    for tool in tools.values():
        assert tool["execution"] == "sync"
        assert tool["affinity"] == "main"
        assert "annotations" in tool
