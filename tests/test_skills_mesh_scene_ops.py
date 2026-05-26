"""Unit tests for expanded Blender object and mesh operation skill scripts."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import yaml

from tests.conftest import load_and_call, make_mock_bpy

SKILLS_ROOT = Path(__file__).parent.parent / "src" / "dcc_mcp_blender" / "skills"
OBJECTS_DIR = SKILLS_ROOT / "blender-objects"
MESH_OPS_DIR = SKILLS_ROOT / "blender-mesh-ops"

NEW_OBJECT_TOOLS = {
    "get_selection",
    "set_selection",
    "select_by_type",
    "find_by_pattern",
    "rename_object",
    "parent_object",
    "group_objects",
    "set_visibility",
    "get_bounding_box",
    "center_origin",
    "freeze_transforms",
}

MESH_OPS_TOOLS = {
    "get_poly_count",
    "cleanup_mesh",
    "triangulate_mesh",
    "separate_mesh",
    "combine_meshes",
    "merge_vertices",
    "extract_faces",
    "mirror_mesh",
    "select_by_material",
}


class FakeObjects(list):
    def get(self, name):
        return next((obj for obj in self if obj.name == name), None)


class FakeCollectionObjects(list):
    def link(self, obj):
        if obj not in self:
            self.append(obj)


class FakeCollection:
    def __init__(self, name):
        self.name = name
        self.objects = FakeCollectionObjects()


class FakeCollections(list):
    def get(self, name):
        return next((collection for collection in self if collection.name == name), None)

    def new(self, name):
        collection = FakeCollection(name)
        self.append(collection)
        return collection


class FakeMesh:
    def __init__(self, name="Mesh", polygon_vertices=None):
        self.name = name
        self.vertices = [object()] * 4
        self.edges = [object()] * 4
        self.loops = [object()] * 4
        self.polygons = [
            FakePolygon(index, vertices) for index, vertices in enumerate(polygon_vertices or [(0, 1, 2, 3)])
        ]
        self.materials = []
        self.uv_layers = []


class FakePolygon:
    def __init__(self, index, vertices):
        self.index = index
        self.vertices = vertices
        self.material_index = 0
        self.select = False


class FakeObject:
    def __init__(self, name="Cube", obj_type="MESH", mesh=None):
        self.name = name
        self.type = obj_type
        self.data = mesh or FakeMesh(name)
        self.mode = "OBJECT"
        self.parent = None
        self.hide_viewport = False
        self.hide_render = False
        self.bound_box = [
            (-1.0, -1.0, -1.0),
            (-1.0, -1.0, 1.0),
            (-1.0, 1.0, -1.0),
            (-1.0, 1.0, 1.0),
            (1.0, -1.0, -1.0),
            (1.0, -1.0, 1.0),
            (1.0, 1.0, -1.0),
            (1.0, 1.0, 1.0),
        ]
        self.matrix_world = None
        self.modifiers = FakeModifiers()
        self._selected = False

    def select_set(self, state):
        self._selected = bool(state)

    def select_get(self):
        return self._selected

    def hide_set(self, state):
        self.hide_viewport = bool(state)


class FakeModifier:
    def __init__(self, name, type):
        self.name = name
        self.type = type
        self.use_axis = [False, False, False]


class FakeModifiers(list):
    def new(self, name, type):
        modifier = FakeModifier(name, type)
        self.append(modifier)
        return modifier


def _bpy_for_objects(objects):
    bpy = make_mock_bpy()
    bpy.data.objects = FakeObjects(objects)
    bpy.context.selected_objects = None

    def select_all(action="DESELECT"):
        if action == "DESELECT":
            for obj in objects:
                obj.select_set(False)
        return {"FINISHED"}

    bpy.ops.object.select_all.side_effect = select_all
    return bpy


def test_object_tools_yaml_declares_modern_contract_for_new_tools():
    doc = yaml.safe_load((OBJECTS_DIR / "tools.yaml").read_text(encoding="utf-8"))
    tools = {tool["name"]: tool for tool in doc["tools"]}
    assert NEW_OBJECT_TOOLS <= set(tools)

    for name in NEW_OBJECT_TOOLS:
        tool = tools[name]
        assert (OBJECTS_DIR / tool["source_file"]).exists(), name
        assert tool["execution"] == "sync"
        assert tool["affinity"] == "main"
        assert isinstance(tool["timeout_hint_secs"], int)
        assert tool["input_schema"]["type"] == "object"
        assert tool["output_schema"]["properties"]["success"]["type"] == "boolean"
        assert "annotations" in tool


def test_mesh_ops_yaml_declares_modern_contract():
    doc = yaml.safe_load((MESH_OPS_DIR / "tools.yaml").read_text(encoding="utf-8"))
    tools = {tool["name"]: tool for tool in doc["tools"]}
    assert set(tools) == MESH_OPS_TOOLS

    for name, tool in tools.items():
        assert (MESH_OPS_DIR / tool["source_file"]).exists(), name
        assert tool["execution"] == "sync"
        assert tool["affinity"] == "main"
        assert isinstance(tool["timeout_hint_secs"], int)
        assert tool["input_schema"]["type"] == "object"
        assert tool["output_schema"]["properties"]["success"]["type"] == "boolean"
        assert "annotations" in tool


def test_selection_find_rename_parent_visibility_and_bounds():
    cube = FakeObject("Cube")
    light = FakeObject("KeyLight", "LIGHT", mesh=None)
    bpy = _bpy_for_objects([cube, light])

    selected = load_and_call("blender-objects/scripts/set_selection.py", bpy, object_names=["Cube"])
    assert selected["success"] is True
    assert selected["context"]["selected"] == ["Cube"]
    assert cube.select_get() is True

    by_type = load_and_call("blender-objects/scripts/select_by_type.py", bpy, type="light")
    assert by_type["success"] is True
    assert by_type["context"]["selected"] == ["KeyLight"]

    found = load_and_call("blender-objects/scripts/find_by_pattern.py", bpy, pattern="Key*", type="LIGHT")
    assert found["success"] is True
    assert found["context"]["objects"] == [{"name": "KeyLight", "type": "LIGHT"}]

    renamed = load_and_call("blender-objects/scripts/rename_object.py", bpy, object_name="Cube", new_name="HeroCube")
    assert renamed["success"] is True
    assert cube.name == "HeroCube"
    assert cube.data.name == "HeroCube"

    parented = load_and_call(
        "blender-objects/scripts/parent_object.py", bpy, child_name="HeroCube", parent_name="KeyLight"
    )
    assert parented["success"] is True
    assert cube.parent is light

    visibility = load_and_call("blender-objects/scripts/set_visibility.py", bpy, object_name="HeroCube", visible=False)
    assert visibility["success"] is True
    assert cube.hide_viewport is True
    assert cube.hide_render is True

    bounds = load_and_call(
        "blender-objects/scripts/get_bounding_box.py", bpy, object_name="HeroCube", world_space=False
    )
    assert bounds["success"] is True
    assert bounds["context"]["size"] == [2.0, 2.0, 2.0]


def test_group_origin_freeze_and_scene_error_paths():
    cube = FakeObject("Cube")
    bpy = _bpy_for_objects([cube])
    bpy.data.collections = FakeCollections()

    grouped = load_and_call(
        "blender-objects/scripts/group_objects.py",
        bpy,
        object_names=["Cube"],
        collection_name="Agents",
    )
    assert grouped["success"] is True
    assert bpy.data.collections.get("Agents").objects == [cube]

    centered = load_and_call("blender-objects/scripts/center_origin.py", bpy, object_name="Cube", mode="bounds")
    assert centered["success"] is True
    bpy.ops.object.origin_set.assert_called_once_with(type="ORIGIN_GEOMETRY", center="BOUNDS")

    frozen = load_and_call("blender-objects/scripts/freeze_transforms.py", bpy, object_name="Cube", scale=True)
    assert frozen["success"] is True
    bpy.ops.object.transform_apply.assert_called_once_with(location=False, rotation=True, scale=True)

    missing = load_and_call("blender-objects/scripts/set_selection.py", bpy, object_names=["Ghost"])
    assert missing["success"] is False

    invalid_mode = load_and_call("blender-objects/scripts/center_origin.py", bpy, object_name="Cube", mode="sideways")
    assert invalid_mode["success"] is False


def test_mesh_count_cleanup_triangulate_and_errors():
    mesh = FakeMesh("QuadMesh")
    cube = FakeObject("Cube", mesh=mesh)
    bpy = _bpy_for_objects([cube])

    counts = load_and_call("blender-mesh-ops/scripts/get_poly_count.py", bpy, object_name="Cube")
    assert counts["success"] is True
    assert counts["context"]["face_count"] == 1
    assert counts["context"]["triangle_count"] == 2

    cleaned = load_and_call("blender-mesh-ops/scripts/cleanup_mesh.py", bpy, object_name="Cube")
    assert cleaned["success"] is True
    bpy.ops.mesh.merge_by_distance.assert_called_once()
    bpy.ops.mesh.normals_make_consistent.assert_called_once_with(inside=False)

    triangulated = load_and_call("blender-mesh-ops/scripts/triangulate_mesh.py", bpy, object_name="Cube")
    assert triangulated["success"] is True
    bpy.ops.mesh.quads_convert_to_tris.assert_called_once()

    missing = load_and_call("blender-mesh-ops/scripts/get_poly_count.py", bpy, object_name="Ghost")
    assert missing["success"] is False

    light = FakeObject("Light", "LIGHT", mesh=None)
    bpy = _bpy_for_objects([light])
    non_mesh = load_and_call("blender-mesh-ops/scripts/get_poly_count.py", bpy, object_name="Light")
    assert non_mesh["success"] is False

    invalid_threshold = load_and_call(
        "blender-mesh-ops/scripts/merge_vertices.py", bpy, object_name="Light", threshold=-1
    )
    assert invalid_threshold["success"] is False


def test_mesh_combine_extract_mirror_select_material_and_invalid_modes():
    cube = FakeObject("Cube")
    sphere = FakeObject("Sphere")
    bpy = _bpy_for_objects([cube, sphere])

    combined = load_and_call(
        "blender-mesh-ops/scripts/combine_meshes.py",
        bpy,
        object_names=["Cube", "Sphere"],
        new_name="Combined",
    )
    assert combined["success"] is True
    assert combined["context"]["object_name"] == "Combined"
    bpy.ops.object.join.assert_called_once()

    invalid_separate = load_and_call(
        "blender-mesh-ops/scripts/separate_mesh.py", bpy, object_name="Combined", mode="explode"
    )
    assert invalid_separate["success"] is False

    invalid_face = load_and_call(
        "blender-mesh-ops/scripts/extract_faces.py",
        bpy,
        object_name="Combined",
        face_indices=[99],
    )
    assert invalid_face["success"] is False

    mirrored = load_and_call(
        "blender-mesh-ops/scripts/mirror_mesh.py",
        bpy,
        object_name="Combined",
        axis="y",
        use_modifier=False,
    )
    assert mirrored["success"] is True
    assert cube.modifiers[0].use_axis == [False, True, False]
    bpy.ops.object.modifier_apply.assert_called_once_with(modifier="Mirror_Y")

    material = MagicMock()
    material.name = "Red"
    cube.data.materials = [material]
    cube.data.polygons[0].material_index = 0
    selected = load_and_call(
        "blender-mesh-ops/scripts/select_by_material.py",
        bpy,
        object_name="Combined",
        material_name="Red",
    )
    assert selected["success"] is True
    assert cube.data.polygons[0].select is True
