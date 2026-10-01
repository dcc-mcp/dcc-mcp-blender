"""Unit tests for blender-uv-ops skill scripts (bpy mocked)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
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


@pytest.mark.parametrize(
    "tool,arguments",
    [
        ("unwrap_uvs", {"method": "smart"}),
        ("unwrap_uvs", {"method": "angle_based"}),
        ("unwrap_uvs", {"method": "conformal"}),
        ("project_uvs", {"method": "smart"}),
        ("project_uvs", {"method": "sphere"}),
        ("project_uvs", {"method": "cylinder"}),
        ("project_uvs", {"method": "view"}),
        ("pack_uvs", {"normalize": True}),
        ("pack_uvs", {"normalize": False}),
    ],
)
def test_uv_operator_reacquires_named_layer_and_mesh_after_mode_transition(tool, arguments):
    class ExpiringLayer(FakeUVLayer):
        expired = False

        def __getattribute__(self, name):
            if name in {"name", "data"} and self.expired:
                raise ReferenceError("UV RNA storage was replaced by mode transition")
            return super().__getattribute__(name)

    class ExpiringMesh(FakeMesh):
        expired = False

        def __getattribute__(self, name):
            if name in {"name", "uv_layers", "loops", "update"} and self.expired:
                raise ReferenceError("Mesh RNA storage was replaced by mode transition")
            return super().__getattribute__(name)

    old_mesh = ExpiringMesh()
    old_layer = ExpiringLayer("Original", len(old_mesh.loops))
    old_mesh.uv_layers = FakeUVLayers(len(old_mesh.loops), [old_layer])
    obj = _mesh_obj(old_mesh)
    fresh_mesh = FakeMesh()
    fresh = FakeUVLayer("Original", 4, [(2, 2), (4, 2), (4, 4), (2, 4)])
    other = FakeUVLayer("Other", 4, [(5, 6)] * 4)
    fresh_mesh.uv_layers = FakeUVLayers(4, [fresh, other])
    fresh_mesh.uv_layers.active = other
    bpy = _bpy_for(obj)
    for operator in ("unwrap", "sphere_project", "cylinder_project", "project_from_view"):
        getattr(bpy.ops.uv, operator).return_value = {"FINISHED"}

    def mode_set(mode):
        if mode == "OBJECT":
            old_layer.expired = True
            old_mesh.expired = True
            obj.data = fresh_mesh
        return {"FINISHED"}

    bpy.ops.object.mode_set.side_effect = mode_set
    result = load_and_call("blender-uv-ops/scripts/{}.py".format(tool), bpy, object_name=obj.name, **arguments)
    assert result["success"], result
    assert result["context"]["uv_map"] == "Original"
    assert result["context"]["active_uv_map"] == "Other"
    fresh_mesh.update.assert_called_once()
    assert [list(loop.uv) for loop in other.data] == [[5, 6]] * 4
    if tool == "pack_uvs":
        assert result["context"]["normalized_coordinate_count"] == (4 if arguments["normalize"] else 0)
        if arguments["normalize"]:
            assert list(fresh.data[0].uv) == [0.001, 0.001]


@pytest.mark.parametrize("tool", ["unwrap_uvs", "project_uvs", "pack_uvs"])
def test_uv_operator_rejects_disappearing_original_layer(tool):
    obj = _mesh_obj()
    bpy = _bpy_for(obj)
    other = FakeUVLayer("Other", 4, [(5, 6)] * 4)

    def mode_set(mode):
        if mode == "OBJECT":
            obj.data = FakeMesh()
            obj.data.uv_layers = FakeUVLayers(4, [other])
        return {"FINISHED"}

    bpy.ops.object.mode_set.side_effect = mode_set
    arguments = {} if tool == "pack_uvs" else {"method": "smart"}
    result = load_and_call("blender-uv-ops/scripts/{}.py".format(tool), bpy, object_name=obj.name, **arguments)
    assert result["success"] is False
    assert result["context"]["mutation_applied"] is True
    assert result["context"]["rollback_verified"] is False
    assert result["context"]["error_type"] == "RuntimeError"
    assert result["context"]["uv_before"]["active_uv_map"] == "UVMap"
    assert result["context"]["uv_after"]["active_uv_map"] == "Other"
    assert [list(loop.uv) for loop in other.data] == [[5, 6]] * 4


def test_cancelled_pack_reports_mutation_receipt_without_normalizing():
    obj = _mesh_obj()
    bpy = _bpy_for(obj)
    bpy.ops.uv.pack_islands.return_value = {"CANCELLED"}
    original = [list(loop.uv) for loop in obj.data.uv_layers.active.data]

    result = load_and_call("blender-uv-ops/scripts/pack_uvs.py", bpy, object_name=obj.name)

    assert result["success"] is False
    assert result["context"]["operator_result"] == ["CANCELLED"]
    assert result["context"]["mutation_applied"] is True
    assert result["context"]["rollback_verified"] is False
    assert [list(loop.uv) for loop in obj.data.uv_layers.active.data] == original


@pytest.mark.parametrize("tool", ["unwrap_uvs", "project_uvs", "pack_uvs"])
@pytest.mark.parametrize("mode", ["EDIT", "SCULPT"])
def test_uv_operator_rejects_non_object_entry_without_mutation(tool, mode):
    obj = _mesh_obj(FakeMesh(with_uv=False))
    obj.mode = mode
    bpy = _bpy_for(obj)
    arguments = {} if tool == "pack_uvs" else {"method": "smart"}

    result = load_and_call("blender-uv-ops/scripts/{}.py".format(tool), bpy, object_name=obj.name, **arguments)

    assert result["success"] is False
    assert result["context"]["mutation_applied"] is False
    assert len(obj.data.uv_layers) == 0
    bpy.ops.object.mode_set.assert_not_called()
    bpy.ops.object.select_all.assert_not_called()


@pytest.mark.parametrize("tool", ["unwrap_uvs", "project_uvs"])
def test_uv_operator_reacquires_newly_created_layer(tool):
    obj = _mesh_obj(FakeMesh(with_uv=False))
    bpy = _bpy_for(obj)

    def mode_set(mode):
        if mode == "OBJECT":
            obj.data = FakeMesh()
        return {"FINISHED"}

    bpy.ops.object.mode_set.side_effect = mode_set
    result = load_and_call("blender-uv-ops/scripts/{}.py".format(tool), bpy, object_name=obj.name, method="smart")
    assert result["success"], result
    assert result["context"]["uv_map"] == "UVMap"


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
        "audit_uv_layout",
        "export_uv_layout",
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


@pytest.mark.parametrize("sync_selection", [False, True])
def test_pack_selects_uvs_before_packing_without_changing_sync_setting(sync_selection):
    obj = _mesh_obj()
    bpy = _bpy_for(obj)
    bpy.context.scene.tool_settings.use_uv_select_sync = sync_selection
    uv_selected = False

    def select_uvs(action):
        nonlocal uv_selected
        assert action == "SELECT"
        uv_selected = True
        return {"FINISHED"}

    def pack(**kwargs):
        assert uv_selected, "Mesh face selection alone does not select UV vertices"
        return {"FINISHED"}

    bpy.ops.uv.select_all.side_effect = select_uvs
    bpy.ops.uv.pack_islands.side_effect = pack

    result = load_and_call("blender-uv-ops/scripts/pack_uvs.py", bpy, object_name=obj.name)

    assert result["success"], result
    bpy.ops.uv.select_all.assert_called_once_with(action="SELECT")
    assert bpy.context.scene.tool_settings.use_uv_select_sync is sync_selection


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
