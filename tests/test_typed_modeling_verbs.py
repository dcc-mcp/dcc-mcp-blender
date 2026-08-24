"""Public contract and host-readback tests for the shared modeling vocabulary."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import yaml

from tests.conftest import load_and_call, make_mock_bpy

SKILL_ROOT = Path(__file__).parent.parent / "src" / "dcc_mcp_blender" / "skills" / "blender-mesh-ops"

MODELING_TOOLS = {
    "add_edge_loop",
    "array_instances",
    "assign_material",
    "auto_uv",
    "bevel_edges",
    "boolean_op",
    "create_primitive",
    "delete_history",
    "extrude_faces",
    "freeze_transforms",
    "group_parent",
    "inset",
    "lathe_profile",
    "loft_sections",
    "mirror",
    "set_pivot",
    "uv_project",
}


def test_modeling_group_covers_the_shared_vocabulary() -> None:
    tools = yaml.safe_load((SKILL_ROOT / "tools.yaml").read_text(encoding="utf-8"))["tools"]
    groups = yaml.safe_load((SKILL_ROOT / "groups.yaml").read_text(encoding="utf-8"))["groups"]
    modeling = next(group for group in groups if group["name"] == "modeling")
    contracts = {tool["name"]: tool for tool in tools}

    assert set(modeling["tools"]) == MODELING_TOOLS
    for name in MODELING_TOOLS:
        contract = contracts[name]
        assert contract["group"] == "modeling"
        assert contract["execution"] == "sync"
        assert contract["affinity"] == "main"
        assert contract["input_schema"]["additionalProperties"] is False
        assert (SKILL_ROOT / contract["source_file"]).is_file(), name


def test_extrude_faces_is_in_inactive_modeling_group_and_verifies_host_effect() -> None:
    tools = yaml.safe_load((SKILL_ROOT / "tools.yaml").read_text(encoding="utf-8"))["tools"]
    groups = yaml.safe_load((SKILL_ROOT / "groups.yaml").read_text(encoding="utf-8"))["groups"]
    contract = next(tool for tool in tools if tool["name"] == "extrude_faces")
    modeling = next(group for group in groups if group["name"] == "modeling")

    assert modeling["default_active"] is False
    assert "extrude_faces" in modeling["tools"]
    assert contract["execution"] == "sync"
    assert contract["affinity"] == "main"
    assert contract["group"] == "modeling"
    assert contract["input_schema"]["additionalProperties"] is False
    assert contract["input_schema"]["properties"]["face_indices"]["maxItems"] == 4096

    mesh = MagicMock()
    mesh.name = "BodyMesh"
    mesh.vertices = [MagicMock() for _ in range(4)]
    mesh.edges = [MagicMock() for _ in range(4)]
    mesh.loops = [MagicMock() for _ in range(4)]
    mesh.polygons = [MagicMock(index=0, select=False)]
    mesh.materials = []
    mesh.uv_layers = []
    obj = MagicMock()
    obj.name = "Body"
    obj.type = "MESH"
    obj.mode = "OBJECT"
    obj.data = mesh

    bpy = make_mock_bpy()
    bpy.data.objects.get.return_value = obj

    def extrude(**_kwargs):
        mesh.polygons.append(MagicMock(index=1, select=False))
        return {"FINISHED"}

    bpy.ops.mesh.extrude_region_move.side_effect = extrude
    result = load_and_call(
        "blender-mesh-ops/scripts/extrude_faces.py",
        bpy,
        object_name="Body",
        face_indices=[0],
        distance=0.25,
        direction=[0.0, 0.0, 1.0],
    )

    assert result["success"] is True, result
    assert result["context"]["parameters"] == {
        "direction": [0.0, 0.0, 1.0],
        "distance": 0.25,
        "face_indices": [0],
    }
    assert result["context"]["readback"]["verified"] is True
    assert result["context"]["readback"]["before"]["face_count"] == 1
    assert result["context"]["readback"]["after"]["face_count"] == 2


def test_create_primitive_sets_name_and_transform_with_exact_readback() -> None:
    bpy = make_mock_bpy()
    bpy.data.objects.get.return_value = None
    mesh = MagicMock(name="RotorMesh")
    obj = MagicMock()
    obj.name = "Cube"
    obj.type = "MESH"
    obj.data = mesh
    obj.location = [1.0, 2.0, 3.0]
    obj.rotation_euler = [0.0, 0.0, 1.5707963267948966]
    obj.scale = [2.0, 1.0, 0.5]

    def create(**_kwargs):
        bpy.context.active_object = obj
        return {"FINISHED"}

    bpy.ops.mesh.primitive_cube_add.side_effect = create
    result = load_and_call(
        "blender-mesh-ops/scripts/create_primitive.py",
        bpy,
        primitive_type="cube",
        name="RotorHub",
        location=[1.0, 2.0, 3.0],
        rotation=[0.0, 0.0, 90.0],
        scale=[2.0, 1.0, 0.5],
        size=2.0,
    )

    assert result["success"] is True, result
    assert obj.name == "RotorHub"
    assert obj.data.name == "RotorHub"
    assert result["context"]["readback"] == {
        "location": [1.0, 2.0, 3.0],
        "name": "RotorHub",
        "rotation": [0.0, 0.0, 90.0],
        "scale": [2.0, 1.0, 0.5],
        "type": "MESH",
        "verified": True,
    }


def test_bevel_inset_and_edge_loop_fail_closed_without_topology_readback() -> None:
    mesh = MagicMock()
    mesh.name = "BodyMesh"
    mesh.vertices = [MagicMock(index=index, select=False) for index in range(4)]
    mesh.edges = [MagicMock(index=index, select=False) for index in range(4)]
    mesh.polygons = [MagicMock(index=0, select=False)]
    mesh.loops = [MagicMock() for _ in range(4)]
    mesh.materials = []
    mesh.uv_layers = []
    obj = MagicMock(name="Body")
    obj.name = "Body"
    obj.type = "MESH"
    obj.mode = "OBJECT"
    obj.data = mesh
    bpy = make_mock_bpy()
    bpy.data.objects.get.return_value = obj

    bpy.ops.mesh.bevel.side_effect = lambda **_kwargs: (
        mesh.edges.append(MagicMock(index=len(mesh.edges), select=False)) or {"FINISHED"}
    )
    beveled = load_and_call(
        "blender-mesh-ops/scripts/bevel_edges.py",
        bpy,
        object_name="Body",
        edge_indices=[0, 1],
        width=0.05,
        segments=3,
    )
    assert beveled["success"] is True, beveled
    assert beveled["context"]["readback"]["verified"] is True
    assert beveled["context"]["readback"]["after"]["edge_count"] == 5

    bpy.ops.mesh.inset.side_effect = lambda **_kwargs: (
        mesh.polygons.append(MagicMock(index=len(mesh.polygons), select=False)) or {"FINISHED"}
    )
    inset_result = load_and_call(
        "blender-mesh-ops/scripts/inset.py",
        bpy,
        object_name="Body",
        face_indices=[0],
        thickness=0.1,
        depth=0.02,
    )
    assert inset_result["success"] is True, inset_result
    assert inset_result["context"]["readback"]["after"]["face_count"] == 2

    bpy.ops.mesh.subdivide.side_effect = lambda **_kwargs: (
        mesh.edges.append(MagicMock(index=len(mesh.edges), select=False)) or {"FINISHED"}
    )
    loop = load_and_call(
        "blender-mesh-ops/scripts/add_edge_loop.py",
        bpy,
        object_name="Body",
        edge_indices=[0, 2],
        cuts=2,
    )
    assert loop["success"] is True, loop
    assert loop["context"]["readback"]["after"]["edge_count"] == 6

    bpy.ops.mesh.bevel.side_effect = None
    bpy.ops.mesh.bevel.return_value = {"FINISHED"}
    unchanged = load_and_call(
        "blender-mesh-ops/scripts/bevel_edges.py",
        bpy,
        object_name="Body",
        edge_indices=[0],
        width=0.01,
    )
    assert unchanged["success"] is False


class _Modifiers(list):
    def new(self, name, type):
        modifier = MagicMock()
        modifier.name = name
        modifier.type = type
        self.append(modifier)
        return modifier

    def get(self, name):
        return next((modifier for modifier in self if modifier.name == name), None)


class _LinkedObjects(list):
    def link(self, obj):
        if obj not in self:
            self.append(obj)


class _Collections(list):
    def get(self, name):
        return next((collection for collection in self if collection.name == name), None)

    def new(self, name):
        collection = MagicMock()
        collection.name = name
        collection.objects = _LinkedObjects()
        self.append(collection)
        return collection


class _UVLayers(list):
    def __init__(self):
        super().__init__()
        self.active = None
        self.active_index = 0

    def new(self, name):
        layer = MagicMock()
        layer.name = name
        layer.data = []
        self.append(layer)
        self.active = layer
        self.active_index = len(self) - 1
        return layer

    def get(self, name):
        return next((layer for layer in self if layer.name == name), None)


def test_array_mirror_and_boolean_use_typed_modifiers_with_readback() -> None:
    body = MagicMock()
    body.name = "Body"
    body.type = "MESH"
    body.data = MagicMock(name="BodyMesh")
    body.modifiers = _Modifiers()
    cutter = MagicMock()
    cutter.name = "Cutter"
    cutter.type = "MESH"
    cutter.data = MagicMock(name="CutterMesh")
    cutter.modifiers = _Modifiers()
    bpy = make_mock_bpy()
    bpy.data.objects.get.side_effect = lambda name: {"Body": body, "Cutter": cutter}.get(name)

    def apply_modifier(*, modifier):
        current = body.modifiers.get(modifier)
        if current is not None:
            body.modifiers.remove(current)
        return {"FINISHED"}

    bpy.ops.object.modifier_apply.side_effect = apply_modifier

    array = load_and_call(
        "blender-mesh-ops/scripts/array_instances.py",
        bpy,
        object_name="Body",
        count=4,
        offset=[2.0, 0.0, 0.0],
        modifier_name="RotorArray",
    )
    assert array["success"] is True, array
    assert array["context"]["readback"] == {
        "applied": False,
        "constant_offset": [2.0, 0.0, 0.0],
        "count": 4,
        "modifier_name": "RotorArray",
        "modifier_type": "ARRAY",
        "verified": True,
    }

    mirrored = load_and_call(
        "blender-mesh-ops/scripts/mirror.py",
        bpy,
        object_name="Body",
        axis="y",
        merge=True,
        bisect=True,
        modifier_name="PylonMirror",
    )
    assert mirrored["success"] is True, mirrored
    assert mirrored["context"]["readback"]["axis"] == "y"
    assert mirrored["context"]["readback"]["use_axis"] == [False, True, False]
    assert mirrored["context"]["readback"]["verified"] is True

    boolean = load_and_call(
        "blender-mesh-ops/scripts/boolean_op.py",
        bpy,
        input_a="Body",
        input_b="Cutter",
        operation="subtract",
        output_name="CutBody",
        apply=True,
    )
    assert boolean["success"] is True, boolean
    assert body.name == "CutBody"
    assert boolean["context"]["readback"] == {
        "applied": True,
        "modifier_present": False,
        "object_name": "CutBody",
        "operand": "Cutter",
        "operation": "subtract",
        "verified": True,
    }


def test_pivot_group_freeze_history_and_material_return_host_readback() -> None:
    parent = MagicMock()
    parent.name = "Aircraft"
    parent.type = "EMPTY"
    left = MagicMock()
    left.name = "LeftPylon"
    left.type = "MESH"
    left.data = MagicMock()
    left.data.name = "LeftPylonMesh"
    left.material_slots = []
    left.modifiers = _Modifiers()
    left.location = [1.0, 2.0, 3.0]
    left.rotation_euler = [0.2, 0.3, 0.4]
    left.scale = [2.0, 2.0, 2.0]
    left.matrix_world.translation = [1.0, 2.0, 3.0]
    right = MagicMock()
    right.name = "RightPylon"
    right.type = "MESH"
    right.data = MagicMock()
    right.modifiers = _Modifiers()
    bpy = make_mock_bpy()
    bpy.data.objects.get.side_effect = lambda name: {
        "Aircraft": parent,
        "LeftPylon": left,
        "RightPylon": right,
    }.get(name)
    bpy.data.collections = _Collections()
    bpy.context.scene.cursor.location = [9.0, 9.0, 9.0]

    def origin_set(**_kwargs):
        left.matrix_world.translation = list(bpy.context.scene.cursor.location)
        return {"FINISHED"}

    bpy.ops.object.origin_set.side_effect = origin_set
    pivot = load_and_call(
        "blender-mesh-ops/scripts/set_pivot.py",
        bpy,
        object_name="LeftPylon",
        position=[0.0, 2.5, 0.0],
    )
    assert pivot["success"] is True, pivot
    assert pivot["context"]["readback"] == {"position": [0.0, 2.5, 0.0], "verified": True}
    assert bpy.context.scene.cursor.location == [9.0, 9.0, 9.0]

    grouped = load_and_call(
        "blender-mesh-ops/scripts/group_parent.py",
        bpy,
        object_names=["LeftPylon", "RightPylon"],
        group_name="Pylons",
        parent_name="Aircraft",
    )
    assert grouped["success"] is True, grouped
    assert left.parent is parent
    assert right.parent is parent
    assert grouped["context"]["readback"]["members"] == ["LeftPylon", "RightPylon"]
    assert grouped["context"]["readback"]["verified"] is True

    def transform_apply(*, location, rotation, scale):
        if location:
            left.location = [0.0, 0.0, 0.0]
        if rotation:
            left.rotation_euler = [0.0, 0.0, 0.0]
        if scale:
            left.scale = [1.0, 1.0, 1.0]
        return {"FINISHED"}

    bpy.ops.object.transform_apply.side_effect = transform_apply
    frozen = load_and_call(
        "blender-mesh-ops/scripts/modeling_freeze_transforms.py",
        bpy,
        object_name="LeftPylon",
        location=True,
        rotation=True,
        scale=True,
    )
    assert frozen["success"] is True, frozen
    assert frozen["context"]["readback"]["verified"] is True
    assert frozen["context"]["readback"]["scale"] == [1.0, 1.0, 1.0]

    bevel_modifier = MagicMock()
    bevel_modifier.name = "Bevel"
    bevel_modifier.type = "BEVEL"
    mirror_modifier = MagicMock()
    mirror_modifier.name = "Mirror"
    mirror_modifier.type = "MIRROR"
    left.modifiers.extend([bevel_modifier, mirror_modifier])

    def apply_modifier(*, modifier):
        current = left.modifiers.get(modifier)
        left.modifiers.remove(current)
        return {"FINISHED"}

    bpy.ops.object.modifier_apply.side_effect = apply_modifier
    history = load_and_call(
        "blender-mesh-ops/scripts/delete_history.py",
        bpy,
        object_name="LeftPylon",
    )
    assert history["success"] is True, history
    assert history["context"]["readback"] == {
        "applied_modifiers": ["Bevel", "Mirror"],
        "remaining_modifiers": [],
        "verified": True,
    }

    material = MagicMock()
    material.name = "Paint"
    bpy.data.materials.get.return_value = material

    def add_slot():
        left.material_slots.append(MagicMock(material=None))
        return {"FINISHED"}

    bpy.ops.object.material_slot_add.side_effect = add_slot
    assigned = load_and_call(
        "blender-mesh-ops/scripts/modeling_assign_material.py",
        bpy,
        object_name="LeftPylon",
        material_name="Paint",
        slot_index=0,
    )
    assert assigned["success"] is True, assigned
    assert assigned["context"]["readback"] == {
        "material_name": "Paint",
        "object_name": "LeftPylon",
        "slot_index": 0,
        "verified": True,
    }


def test_auto_uv_and_uv_project_delegate_to_native_uv_ops_with_readback() -> None:
    mesh = MagicMock()
    mesh.name = "BodyMesh"
    mesh.vertices = []
    mesh.edges = []
    mesh.loops = []
    mesh.polygons = []
    mesh.uv_layers = _UVLayers()
    obj = MagicMock()
    obj.name = "Body"
    obj.type = "MESH"
    obj.mode = "OBJECT"
    obj.data = mesh
    bpy = make_mock_bpy()
    bpy.data.objects.get.return_value = obj
    bpy.ops.uv = MagicMock()
    bpy.ops.uv.smart_project.return_value = {"FINISHED"}
    bpy.ops.uv.cylinder_project.return_value = {"FINISHED"}

    automatic = load_and_call(
        "blender-mesh-ops/scripts/auto_uv.py",
        bpy,
        object_name="Body",
        margin=0.01,
    )
    assert automatic["success"] is True, automatic
    assert automatic["context"]["readback"] == {
        "active_uv_map": "UVMap",
        "uv_map_count": 1,
        "verified": True,
    }

    projected = load_and_call(
        "blender-mesh-ops/scripts/uv_project.py",
        bpy,
        object_name="Body",
        projection="cylindrical",
        axis="y",
        margin=0.02,
    )
    assert projected["success"] is True, projected
    assert projected["context"]["parameters"]["projection"] == "cylindrical"
    assert projected["context"]["readback"]["active_uv_map"] == "UVMap"
    assert projected["context"]["readback"]["verified"] is True


def _profile_object(name):
    obj = MagicMock()
    obj.name = name
    obj.type = "MESH"
    obj.data = MagicMock()
    obj.data.name = f"{name}Mesh"
    obj.data.vertices = [MagicMock() for _ in range(4)]
    obj.data.edges = [MagicMock() for _ in range(4)]
    obj.data.polygons = []
    obj.modifiers = _Modifiers()
    obj.matrix_world.translation = [0.0, 0.0, 0.0]
    obj.select_set = MagicMock()
    return obj


def test_loft_and_lathe_preserve_sources_and_verify_generated_topology() -> None:
    section_a = _profile_object("SectionA")
    section_b = _profile_object("SectionB")
    lofted = _profile_object("SectionA_copy")
    section_b_copy = _profile_object("SectionB_copy")
    lathed = _profile_object("SectionA_lathe")
    copies = iter([lofted, section_b_copy, lathed])

    def copy_object():
        return next(copies)

    section_a.copy.side_effect = copy_object
    section_b.copy.side_effect = copy_object
    section_a.data.copy.side_effect = [lofted.data, lathed.data]
    section_b.data.copy.return_value = section_b_copy.data

    bpy = make_mock_bpy()
    bpy.data.objects.get.side_effect = lambda name: {"SectionA": section_a, "SectionB": section_b}.get(name)
    bpy.context.collection.objects.link = MagicMock()
    bpy.ops.mesh.bridge_edge_loops.side_effect = lambda **_kwargs: (
        lofted.data.polygons.append(MagicMock(index=0)) or {"FINISHED"}
    )

    def apply_modifier(*, modifier):
        current = lathed.modifiers.get(modifier)
        lathed.modifiers.remove(current)
        lathed.data.polygons.append(MagicMock(index=0))
        return {"FINISHED"}

    bpy.ops.object.modifier_apply.side_effect = apply_modifier

    loft = load_and_call(
        "blender-mesh-ops/scripts/loft_sections.py",
        bpy,
        sections=["SectionA", "SectionB"],
        output_name="Fuselage",
    )
    assert loft["success"] is True, loft
    assert loft["context"]["readback"]["object_name"] == "Fuselage"
    assert loft["context"]["readback"]["face_count"] == 1
    assert loft["context"]["readback"]["verified"] is True
    assert section_a.name == "SectionA"
    assert section_b.name == "SectionB"

    revolved = load_and_call(
        "blender-mesh-ops/scripts/lathe_profile.py",
        bpy,
        profile="SectionA",
        axis="y",
        origin=[0.0, 0.0, 0.0],
        segments=48,
        output_name="RotorHub",
    )
    assert revolved["success"] is True, revolved
    assert revolved["context"]["parameters"]["segments"] == 48
    assert revolved["context"]["readback"]["object_name"] == "RotorHub"
    assert revolved["context"]["readback"]["face_count"] == 1
    assert revolved["context"]["readback"]["verified"] is True
