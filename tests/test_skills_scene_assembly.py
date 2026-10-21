"""Unit tests for blender-scene-assembly skill scripts (bpy mocked)."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
import yaml

from tests.conftest import load_and_call, make_mock_bpy

ASSEMBLY_PATH = "src/dcc_mcp_blender/skills/blender-scene-assembly/tools.yaml"


class _LoadedDataBlock:
    """A loaded ID with a name distinct from Blender's non-JSON representation."""

    def __init__(self, name):
        self.name = name

    def __repr__(self):
        return f'<bpy_struct, Object("{self.name}") at 0x12345678>'


class _LibraryLoad:
    """Model libraries.load replacing the assigned names list in place on exit."""

    def __init__(self, data_type, loaded_by_name):
        self.data_type = data_type
        self.loaded_by_name = loaded_by_name
        self.data_from = SimpleNamespace(**{data_type: list(loaded_by_name)})
        self.data_to = SimpleNamespace()
        self.requested_names = None

    def __enter__(self):
        return self.data_from, self.data_to

    def __exit__(self, exc_type, exc_value, traceback):
        if exc_type is None:
            items = getattr(self.data_to, self.data_type)
            self.requested_names = list(items)
            items[:] = [self.loaded_by_name[name] for name in items]


@pytest.mark.parametrize("tool,link", [("append_from_blend", False), ("link_from_blend", True)])
@pytest.mark.parametrize("data_type", ["objects", "collections"])
@pytest.mark.parametrize(
    "source_names,requested_names,loaded_names,expected_names",
    [
        (["LabDomain"], ["LabDomain"], ["LabDomain"], ["LabDomain"]),
        (["LabDomain"], ["LabDomain"], ["LabDomain.001"], ["LabDomain.001"]),
        (["LabDomain", "Failed"], None, ["LabDomain", None], ["LabDomain"]),
        (["Failed"], ["Failed"], [None], []),
        (["LabDomain", "Other"], None, ["LabDomain", "Other"], ["LabDomain", "Other"]),
        (["LabDomain"], ["Missing"], ["LabDomain"], []),
    ],
    ids=["loaded", "renamed", "partial-load", "failed-load", "all-names", "no-match"],
)
def test_append_link_report_loaded_data_block_names(
    tmp_path, tool, link, data_type, source_names, requested_names, loaded_names, expected_names
):
    path = tmp_path / "library.blend"
    path.touch()
    loaded_by_name = {
        source: _LoadedDataBlock(loaded) if loaded is not None else None
        for source, loaded in zip(source_names, loaded_names)
    }
    loader = _LibraryLoad(data_type, loaded_by_name)
    bpy = make_mock_bpy()
    bpy.data.libraries.load.return_value = loader

    result = load_and_call(
        f"blender-scene-assembly/scripts/{tool}.py",
        bpy,
        filepath=str(path),
        data_type=data_type,
        names=requested_names,
    )

    assert result["success"] is True
    assert result["context"]["names"] == expected_names
    assert result["context"]["count"] == len(expected_names)
    assert result["context"]["link"] is link
    verb = "Linked" if link else "Appended"
    assert result["message"] == f"{verb} {len(expected_names)} {data_type} from library.blend"
    assert json.loads(json.dumps(result))["context"]["names"] == expected_names
    bpy.data.libraries.load.assert_called_once_with(str(path), link=link)
    assert loader.requested_names == (
        [name for name in requested_names if name in source_names] if requested_names else source_names
    )


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


def test_configure_view_layer_passes_and_collections():
    bpy = make_mock_bpy()
    scene = _make_scene("Scene")
    bpy.context.scene = scene
    layer = MagicMock()
    layer.use = True
    layer.use_pass_z = False
    layer.use_pass_cryptomatte_object = False
    layer.cycles.use_pass_volume_direct = False
    layer.pass_cryptomatte_depth = 6
    root = MagicMock()
    root.collection.name = "Scene Collection"
    fx = MagicMock()
    fx.collection.name = "FX"
    root.children = [fx]
    fx.children = []
    layer.layer_collection = root
    scene.view_layers.__contains__ = MagicMock(return_value=True)
    scene.view_layers.__getitem__ = MagicMock(return_value=layer)

    result = load_and_call(
        "blender-scene-assembly/scripts/configure_view_layer.py",
        bpy,
        name="Beauty",
        passes=["z", "cryptomatte_object", "volume_direct"],
        exclude_collections=["FX"],
        cryptomatte_depth=8,
    )

    assert result["success"] is True
    assert layer.use_pass_z is True
    assert layer.use_pass_cryptomatte_object is True
    assert layer.cycles.use_pass_volume_direct is True
    assert layer.pass_cryptomatte_depth == 8
    assert fx.exclude is True


def test_configure_view_layer_validates_before_mutation():
    bpy = make_mock_bpy()
    scene = _make_scene("Scene")
    bpy.context.scene = scene
    layer = MagicMock()
    layer.use_pass_z = False
    root = MagicMock()
    root.collection.name = "Scene Collection"
    root.children = []
    layer.layer_collection = root
    scene.view_layers.__contains__ = MagicMock(return_value=True)
    scene.view_layers.__getitem__ = MagicMock(return_value=layer)

    result = load_and_call(
        "blender-scene-assembly/scripts/configure_view_layer.py",
        bpy,
        name="Beauty",
        passes=["z"],
        exclude_collections=["Missing"],
    )

    assert result["success"] is False
    assert layer.use_pass_z is False


def test_configure_view_layer_rejects_unknown_pass():
    bpy = make_mock_bpy()
    result = load_and_call(
        "blender-scene-assembly/scripts/configure_view_layer.py",
        bpy,
        name="Beauty",
        passes=["not_a_pass"],
    )
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
        "configure_view_layer",
        "remove_view_layer",
        "set_active_view_layer",
        "list_external_references",
    }.issubset(tools)
    for tool in tools.values():
        assert tool["execution"] == "sync"
        assert tool["affinity"] == "main"
        assert "annotations" in tool
