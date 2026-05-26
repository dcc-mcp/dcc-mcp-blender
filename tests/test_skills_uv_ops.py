"""Unit tests for blender-uv-ops skill scripts (bpy mocked)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import yaml

from tests.conftest import load_and_call, make_mock_bpy

SKILL_DIR = Path(__file__).parent.parent / "src" / "dcc_mcp_blender" / "skills" / "blender-uv-ops"


class FakeVertex:
    def __init__(self, co):
        self.co = co


class FakeLoop:
    def __init__(self, vertex_index):
        self.vertex_index = vertex_index


class FakePolygon:
    def __init__(self, index, loop_indices, normal=(0.0, 0.0, 1.0)):
        self.index = index
        self.loop_indices = loop_indices
        self.normal = normal


class FakeUVData:
    def __init__(self, uv=(0.0, 0.0)):
        self.uv = list(uv)


class FakeUVLayer:
    def __init__(self, name, loop_count, coords=None):
        self.name = name
        values = coords or [(0.0, 0.0)] * loop_count
        self.data = [FakeUVData(uv) for uv in values]


class FakeUVLayers:
    def __init__(self, loop_count, layers=None):
        self._loop_count = loop_count
        self._layers = layers or []
        self.active = self._layers[0] if self._layers else None
        self.active_index = 0

    def __iter__(self):
        return iter(self._layers)

    def __len__(self):
        return len(self._layers)

    def get(self, name):
        return next((layer for layer in self._layers if layer.name == name), None)

    def new(self, name):
        layer = FakeUVLayer(name, self._loop_count)
        self._layers.append(layer)
        self.active = layer
        self.active_index = len(self._layers) - 1
        return layer

    def remove(self, layer):
        self._layers.remove(layer)
        self.active = self._layers[0] if self._layers else None
        self.active_index = 0


class FakeMesh:
    def __init__(self, name="Plane", two_islands=False, with_uv=True):
        self.name = name
        if two_islands:
            self.vertices = [
                FakeVertex((0.0, 0.0, 0.0)),
                FakeVertex((1.0, 0.0, 0.0)),
                FakeVertex((1.0, 1.0, 0.0)),
                FakeVertex((0.0, 1.0, 0.0)),
                FakeVertex((3.0, 0.0, 0.0)),
                FakeVertex((4.0, 0.0, 0.0)),
                FakeVertex((4.0, 1.0, 0.0)),
                FakeVertex((3.0, 1.0, 0.0)),
            ]
            self.loops = [FakeLoop(index) for index in range(8)]
            self.polygons = [FakePolygon(0, [0, 1, 2, 3]), FakePolygon(1, [4, 5, 6, 7])]
            coords = [
                (0.0, 0.0),
                (1.0, 0.0),
                (1.0, 1.0),
                (0.0, 1.0),
                (2.0, 0.0),
                (3.0, 0.0),
                (3.0, 1.0),
                (2.0, 1.0),
            ]
        else:
            self.vertices = [
                FakeVertex((0.0, 0.0, 0.0)),
                FakeVertex((2.0, 0.0, 0.0)),
                FakeVertex((2.0, 1.0, 0.0)),
                FakeVertex((0.0, 1.0, 0.0)),
            ]
            self.loops = [FakeLoop(index) for index in range(4)]
            self.polygons = [FakePolygon(0, [0, 1, 2, 3])]
            coords = [(2.0, 5.0), (4.0, 5.0), (4.0, 7.0), (2.0, 7.0)]
        layers = [FakeUVLayer("UVMap", len(self.loops), coords)] if with_uv else []
        self.uv_layers = FakeUVLayers(len(self.loops), layers=layers)
        self.update = MagicMock()


def _mesh_obj(mesh=None, name="Plane"):
    obj = MagicMock()
    obj.name = name
    obj.type = "MESH"
    obj.data = mesh or FakeMesh(name)
    obj.mode = "OBJECT"
    obj.select_set = MagicMock()
    return obj


def _bpy_for(obj):
    bpy = make_mock_bpy()
    bpy.data.objects.get.return_value = obj
    bpy.ops.uv = MagicMock()
    bpy.ops.uv.smart_project.return_value = {"FINISHED"}
    bpy.ops.uv.pack_islands.return_value = {"FINISHED"}
    return bpy


def test_tools_yaml_declares_modern_contract():
    doc = yaml.safe_load((SKILL_DIR / "tools.yaml").read_text(encoding="utf-8"))
    expected = {
        "list_uv_maps",
        "create_uv_map",
        "delete_uv_map",
        "copy_uv_map",
        "get_uv_info",
        "get_uv_islands",
        "project_uvs",
        "unwrap_uvs",
        "pack_uvs",
        "normalize_uvs",
    }
    tools = {tool["name"]: tool for tool in doc["tools"]}
    assert set(tools) == expected
    for name, tool in tools.items():
        assert tool["source_file"].startswith("scripts/")
        assert (SKILL_DIR / tool["source_file"]).exists(), name
        assert tool["input_schema"]["type"] == "object"
        assert tool["output_schema"]["properties"]["success"]["type"] == "boolean"
        assert tool["execution"] == "sync"
        assert tool["affinity"] == "main"
        assert isinstance(tool["timeout_hint_secs"], int)
        assert "annotations" in tool


def test_list_and_create_uv_maps():
    obj = _mesh_obj(FakeMesh(with_uv=False))
    bpy = _bpy_for(obj)

    result = load_and_call("blender-uv-ops/scripts/create_uv_map.py", bpy, object_name="Plane", name="Lightmap")

    assert result["success"] is True
    assert result["context"]["created_uv_map"] == "Lightmap"
    assert result["context"]["active_uv_map"] == "Lightmap"

    result = load_and_call("blender-uv-ops/scripts/list_uv_maps.py", bpy, object_name="Plane")
    assert result["context"]["uv_map_count"] == 1


def test_copy_and_delete_uv_map():
    obj = _mesh_obj(FakeMesh())
    bpy = _bpy_for(obj)

    result = load_and_call(
        "blender-uv-ops/scripts/copy_uv_map.py",
        bpy,
        object_name="Plane",
        source="UVMap",
        target="UVCopy",
    )

    assert result["success"] is True
    copied = obj.data.uv_layers.get("UVCopy")
    assert copied is not None
    assert list(copied.data[0].uv) == [2.0, 5.0]

    result = load_and_call("blender-uv-ops/scripts/delete_uv_map.py", bpy, object_name="Plane", name="UVCopy")
    assert result["success"] is True
    assert obj.data.uv_layers.get("UVCopy") is None


def test_get_uv_info_and_islands():
    obj = _mesh_obj(FakeMesh(two_islands=True))
    bpy = _bpy_for(obj)

    info = load_and_call("blender-uv-ops/scripts/get_uv_info.py", bpy, object_name="Plane")
    assert info["success"] is True
    assert info["context"]["island_count"] == 2
    assert info["context"]["uv_coordinate_count"] == 8

    islands = load_and_call("blender-uv-ops/scripts/get_uv_islands.py", bpy, object_name="Plane")
    assert islands["success"] is True
    assert islands["context"]["island_count"] == 2
    assert islands["context"]["islands"][0]["face_count"] == 1


def test_project_planar_uvs_writes_normalized_coordinates():
    obj = _mesh_obj(FakeMesh(with_uv=False))
    bpy = _bpy_for(obj)

    result = load_and_call(
        "blender-uv-ops/scripts/project_uvs.py",
        bpy,
        object_name="Plane",
        method="planar",
        axis="z",
        margin=0.1,
    )

    assert result["success"] is True
    layer = obj.data.uv_layers.active
    coords = [coord for loop in layer.data for coord in loop.uv]
    assert min(coords) >= 0.1
    assert max(coords) <= 0.9


def test_unwrap_smart_uses_blender_uv_operator():
    obj = _mesh_obj(FakeMesh())
    bpy = _bpy_for(obj)

    result = load_and_call(
        "blender-uv-ops/scripts/unwrap_uvs.py",
        bpy,
        object_name="Plane",
        method="smart",
        margin=0.01,
    )

    assert result["success"] is True
    bpy.ops.uv.smart_project.assert_called_once()
    bpy.ops.object.mode_set.assert_any_call(mode="EDIT")
    bpy.ops.object.mode_set.assert_any_call(mode="OBJECT")


def test_pack_and_normalize_uvs():
    obj = _mesh_obj(FakeMesh())
    bpy = _bpy_for(obj)

    packed = load_and_call(
        "blender-uv-ops/scripts/pack_uvs.py",
        bpy,
        object_name="Plane",
        margin=0.05,
        rotate=False,
        normalize=True,
    )
    assert packed["success"] is True
    bpy.ops.uv.pack_islands.assert_called_once()

    normalized = load_and_call("blender-uv-ops/scripts/normalize_uvs.py", bpy, object_name="Plane")
    assert normalized["success"] is True
    assert normalized["context"]["bounds"]["min"] == [0.0, 0.0]
    assert normalized["context"]["bounds"]["max"] == [1.0, 1.0]


def test_missing_and_non_mesh_objects_return_errors():
    bpy = make_mock_bpy()
    bpy.data.objects.get.return_value = None
    missing = load_and_call("blender-uv-ops/scripts/list_uv_maps.py", bpy, object_name="Ghost")
    assert missing["success"] is False

    obj = MagicMock()
    obj.type = "LIGHT"
    bpy.data.objects.get.return_value = obj
    non_mesh = load_and_call("blender-uv-ops/scripts/get_uv_info.py", bpy, object_name="Sun")
    assert non_mesh["success"] is False
