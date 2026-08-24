"""Public contract and host-readback tests for the shared modeling vocabulary."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, PropertyMock

import pytest
import yaml

from dcc_mcp_blender._modeling_common import MAX_EVIDENCE_ELEMENTS
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


def test_modeling_evidence_bound_fits_declared_destructive_timeouts() -> None:
    tools = yaml.safe_load((SKILL_ROOT / "tools.yaml").read_text(encoding="utf-8"))["tools"]
    contracts = {tool["name"]: tool for tool in tools}

    assert MAX_EVIDENCE_ELEMENTS <= 1_000_000
    for name in {"loft_sections", "lathe_profile", "boolean_op", "delete_history"}:
        assert contracts[name]["timeout_hint_secs"] >= 30, name


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
    mesh.vertices = [MagicMock() for _ in range(8)]
    mesh.edges = [MagicMock() for _ in range(12)]
    mesh.polygons = [MagicMock() for _ in range(6)]
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
        "vertex_count": 8,
        "edge_count": 12,
        "face_count": 6,
        "verified": True,
    }


def test_create_primitive_rejects_a_preexisting_active_object_replay() -> None:
    bpy = make_mock_bpy()
    existing = MagicMock()
    existing.name = "ExistingBody"
    existing.type = "MESH"
    existing.data = MagicMock(name="ExistingMesh")
    existing.location = [0.0, 0.0, 0.0]
    existing.rotation_euler = [0.0, 0.0, 0.0]
    existing.scale = [1.0, 1.0, 1.0]
    bpy.data.objects.get.return_value = None
    bpy.data.objects.__iter__.return_value = iter([existing])
    bpy.context.active_object = existing
    bpy.ops.mesh.primitive_cube_add.return_value = {"FINISHED"}

    result = load_and_call(
        "blender-mesh-ops/scripts/create_primitive.py",
        bpy,
        primitive_type="cube",
        name="NewBody",
    )

    assert result["success"] is False
    assert existing.name == "ExistingBody"
    bpy.data.objects.remove.assert_not_called()


def test_create_primitive_removes_a_new_object_after_cancelled_operator() -> None:
    bpy = make_mock_bpy()
    bpy.data.objects.get.return_value = None
    created = MagicMock()
    created.name = "Cube"
    created.type = "MESH"
    created.data = MagicMock(name="CubeMesh")
    bpy.context.active_object = created
    bpy.ops.mesh.primitive_cube_add.return_value = {"CANCELLED"}

    result = load_and_call(
        "blender-mesh-ops/scripts/create_primitive.py",
        bpy,
        primitive_type="cube",
        name="NewBody",
    )

    assert result["success"] is False
    assert result["context"]["rollback_attempted"] is True
    bpy.data.objects.remove.assert_called_once_with(created, do_unlink=True)


def test_create_primitive_reports_failed_rollback_after_renamed_output_remains() -> None:
    bpy = make_mock_bpy()
    bpy.data.objects.get.return_value = None
    created = MagicMock()
    created.name = "Cube"
    created.type = "MESH"
    created.data = MagicMock(name="CubeMesh")
    created.data.vertices = [MagicMock() for _ in range(8)]
    created.data.edges = [MagicMock() for _ in range(12)]
    created.data.polygons = [MagicMock() for _ in range(6)]
    created.location = [0.0, 0.0, 0.0]
    created.rotation_euler = [0.0, 0.0, 0.0]
    created.scale = [1.0, 1.0, 1.0]
    bpy.data.objects.__iter__.side_effect = [iter([]), iter([created])]
    bpy.data.objects.remove.side_effect = RuntimeError("remove failed")

    def create(**_kwargs):
        bpy.context.active_object = created
        return {"FINISHED"}

    bpy.ops.mesh.primitive_cube_add.side_effect = create
    result = load_and_call(
        "blender-mesh-ops/scripts/create_primitive.py",
        bpy,
        primitive_type="cube",
        name="NewBody",
        location=[1.0, 2.0, 3.0],
    )

    assert result["success"] is False
    assert created.name == "NewBody"
    assert result["context"]["mutation_applied"] is True
    assert result["context"]["rollback_attempted"] is True
    assert result["context"]["rollback_verified"] is False


def test_create_primitive_claims_and_removes_output_when_operator_raises() -> None:
    registry = []
    bpy = make_mock_bpy()
    bpy.data.objects.get.return_value = None
    bpy.data.objects.__iter__.side_effect = lambda: iter(registry)
    bpy.data.objects.remove.side_effect = lambda obj, **_kwargs: registry.remove(obj)
    created = MagicMock()
    created.name = "Cube"
    created.type = "MESH"
    created.data = MagicMock(name="CubeMesh")

    def create_then_raise(**_kwargs):
        registry.append(created)
        bpy.context.active_object = created
        raise RuntimeError("operator failed after create")

    bpy.ops.mesh.primitive_cube_add.side_effect = create_then_raise
    result = load_and_call(
        "blender-mesh-ops/scripts/create_primitive.py",
        bpy,
        primitive_type="cube",
        name="NewBody",
    )

    assert result["success"] is False
    assert result["context"]["mutation_applied"] is True
    assert result["context"]["rollback_attempted"] is True
    assert result["context"]["rollback_verified"] is True
    assert result["context"]["error_type"] == "RuntimeError"
    assert registry == []


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


def test_extrude_rejects_a_cancelled_operator_even_if_topology_changed() -> None:
    mesh = MagicMock()
    mesh.name = "BodyMesh"
    mesh.vertices = [MagicMock(index=index, select=False) for index in range(4)]
    mesh.edges = [MagicMock(index=index, select=False) for index in range(4)]
    mesh.polygons = [MagicMock(index=0, select=False)]
    obj = MagicMock()
    obj.name = "Body"
    obj.type = "MESH"
    obj.data = mesh
    bpy = make_mock_bpy()
    bpy.data.objects.get.return_value = obj

    def cancelled_extrude(**_kwargs):
        mesh.polygons.append(MagicMock(index=1, select=False))
        return {"CANCELLED"}

    bpy.ops.mesh.extrude_region_move.side_effect = cancelled_extrude
    result = load_and_call(
        "blender-mesh-ops/scripts/extrude_faces.py",
        bpy,
        object_name="Body",
        face_indices=[0],
        distance=1.0,
    )

    assert result["success"] is False
    assert result["context"]["mutation_applied"] is True
    assert result["context"]["rollback_verified"] is False


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
    body.data.vertices = [MagicMock() for _ in range(4)]
    body.data.edges = [MagicMock() for _ in range(4)]
    body.data.polygons = [MagicMock()]
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
            body.data.polygons.append(MagicMock())
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
    assert array["context"]["readback"]["applied"] is False
    assert array["context"]["readback"]["constant_offset"] == [2.0, 0.0, 0.0]
    assert array["context"]["readback"]["count"] == 4
    assert array["context"]["readback"]["modifier_name"] == "RotorArray"
    assert array["context"]["readback"]["modifier_type"] == "ARRAY"
    assert array["context"]["readback"]["verified"] is True

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
    assert boolean["context"]["readback"]["applied"] is True
    assert boolean["context"]["readback"]["modifier_present"] is False
    assert boolean["context"]["readback"]["object_name"] == "CutBody"
    assert boolean["context"]["readback"]["operand"] == "Cutter"
    assert boolean["context"]["readback"]["operation"] == "subtract"
    assert boolean["context"]["readback"]["mesh_before"]["face_count"] == 1
    assert boolean["context"]["readback"]["mesh_after"]["face_count"] == 2
    assert boolean["context"]["readback"]["verified"] is True


def test_applied_array_rejects_modifier_removal_without_mesh_change() -> None:
    body = MagicMock()
    body.name = "Body"
    body.type = "MESH"
    body.data = MagicMock(name="BodyMesh")
    body.data.vertices = [MagicMock() for _ in range(4)]
    body.data.edges = [MagicMock() for _ in range(4)]
    body.data.polygons = [MagicMock()]
    body.modifiers = _Modifiers()
    bpy = make_mock_bpy()
    bpy.data.objects.get.return_value = body

    def remove_modifier_only(*, modifier):
        body.modifiers.remove(body.modifiers.get(modifier))
        return {"FINISHED"}

    bpy.ops.object.modifier_apply.side_effect = remove_modifier_only
    result = load_and_call(
        "blender-mesh-ops/scripts/array_instances.py",
        bpy,
        object_name="Body",
        count=4,
        offset=[2.0, 0.0, 0.0],
        apply=True,
    )

    assert result["success"] is False
    assert result["context"]["mutation_applied"] is True
    assert result["context"]["rollback_attempted"] is False
    assert result["context"]["rollback_verified"] is False


def test_applied_array_reports_mutation_when_post_apply_evidence_exceeds_the_bound() -> None:
    class _TooLarge:
        def __len__(self):
            return 10_000_001

        def __iter__(self):
            raise AssertionError("bounded failure receipts must not iterate oversized evidence")

    body = MagicMock()
    body.name = "Body"
    body.type = "MESH"
    body.data = MagicMock(name="BodyMesh")
    body.data.vertices = [MagicMock() for _ in range(4)]
    body.data.edges = [MagicMock() for _ in range(4)]
    body.data.polygons = [MagicMock()]
    body.modifiers = _Modifiers()
    bpy = make_mock_bpy()
    bpy.data.objects.get.return_value = body

    def expand_beyond_evidence_limit(*, modifier):
        body.modifiers.remove(body.modifiers.get(modifier))
        body.data.vertices = _TooLarge()
        return {"FINISHED"}

    bpy.ops.object.modifier_apply.side_effect = expand_beyond_evidence_limit
    result = load_and_call(
        "blender-mesh-ops/scripts/array_instances.py",
        bpy,
        object_name="Body",
        count=4,
        offset=[2.0, 0.0, 0.0],
        apply=True,
    )

    assert result["success"] is False
    assert result["context"]["mutation_applied"] is True
    assert result["context"]["rollback_attempted"] is False
    assert result["context"]["rollback_verified"] is False
    assert result["context"]["mesh_after_counts"]["vertex_count"] == 10_000_001
    assert result["context"]["mesh_after_counts"]["evidence_limited"] is True


def test_applied_array_rejects_configuration_drift_before_apply() -> None:
    class _IgnoringArrayModifier:
        name = "Array_Instances"
        type = "ARRAY"
        count = 2
        use_relative_offset = True
        use_constant_offset = False
        constant_offset_displace = [9.0, 0.0, 0.0]

        def __setattr__(self, name, value):
            if name in {"count", "use_relative_offset", "use_constant_offset", "constant_offset_displace"}:
                return
            super().__setattr__(name, value)

    body = MagicMock()
    body.name = "Body"
    body.type = "MESH"
    body.data = MagicMock(name="BodyMesh")
    body.data.vertices = [MagicMock() for _ in range(4)]
    body.data.edges = [MagicMock() for _ in range(4)]
    body.data.polygons = [MagicMock()]
    body.modifiers = _Modifiers()
    body.modifiers.new = MagicMock(
        side_effect=lambda **_kwargs: body.modifiers.append(_IgnoringArrayModifier()) or body.modifiers[-1]
    )
    bpy = make_mock_bpy()
    bpy.data.objects.get.return_value = body

    result = load_and_call(
        "blender-mesh-ops/scripts/array_instances.py",
        bpy,
        object_name="Body",
        count=4,
        offset=[2.0, 0.0, 0.0],
        apply=True,
    )

    assert result["success"] is False
    bpy.ops.object.modifier_apply.assert_not_called()
    assert result["context"]["actual_configuration"]["count"] == 2
    assert result["context"]["actual_configuration"]["constant_offset"] == [9.0, 0.0, 0.0]
    assert result["context"]["rollback_verified"] is True


def test_applied_mirror_rejects_configuration_drift_before_apply() -> None:
    class _IgnoringMirrorModifier:
        name = "Mirror_Y"
        type = "MIRROR"
        use_axis = [False, False, False]
        use_bisect_axis = [False, False, False]
        use_mirror_merge = False

        def __setattr__(self, name, value):
            if name in {"use_axis", "use_bisect_axis", "use_mirror_merge"}:
                return
            super().__setattr__(name, value)

    body = MagicMock()
    body.name = "Body"
    body.type = "MESH"
    body.data = MagicMock(name="BodyMesh")
    body.data.vertices = [MagicMock() for _ in range(4)]
    body.data.edges = [MagicMock() for _ in range(4)]
    body.data.polygons = [MagicMock()]
    body.modifiers = _Modifiers()
    body.modifiers.new = MagicMock(
        side_effect=lambda **_kwargs: body.modifiers.append(_IgnoringMirrorModifier()) or body.modifiers[-1]
    )
    bpy = make_mock_bpy()
    bpy.data.objects.get.return_value = body

    result = load_and_call(
        "blender-mesh-ops/scripts/mirror.py",
        bpy,
        object_name="Body",
        axis="y",
        merge=True,
        bisect=True,
        apply=True,
    )

    assert result["success"] is False
    bpy.ops.object.modifier_apply.assert_not_called()
    assert result["context"]["actual_configuration"]["use_axis"] == [False, False, False]
    assert result["context"]["rollback_verified"] is True


def test_boolean_rejects_an_output_name_owned_by_another_object() -> None:
    body = MagicMock()
    body.name = "Body"
    body.type = "MESH"
    body.data = MagicMock(name="BodyMesh")
    body.data.vertices = [MagicMock() for _ in range(4)]
    body.data.edges = [MagicMock() for _ in range(4)]
    body.data.polygons = [MagicMock()]
    body.modifiers = _Modifiers()
    cutter = MagicMock()
    cutter.name = "Cutter"
    cutter.type = "MESH"
    occupied = MagicMock()
    occupied.name = "Occupied"
    bpy = make_mock_bpy()
    bpy.data.objects.get.side_effect = lambda name: {"Body": body, "Cutter": cutter, "Occupied": occupied}.get(name)

    result = load_and_call(
        "blender-mesh-ops/scripts/boolean_op.py",
        bpy,
        input_a="Body",
        input_b="Cutter",
        operation="subtract",
        output_name="Occupied",
    )

    assert result["success"] is False
    assert len(body.modifiers) == 0
    bpy.ops.object.modifier_apply.assert_not_called()


def test_boolean_rejects_host_suffixed_output_name_after_mesh_mutation() -> None:
    state = {"name": "Body"}

    def object_name(*args):
        if args:
            state["name"] = f"{args[0]}.001"
        return state["name"]

    body = MagicMock()
    type(body).name = PropertyMock(side_effect=object_name)
    body.type = "MESH"
    body.data = MagicMock(name="BodyMesh")
    body.data.name = "BodyMesh"
    body.data.vertices = [MagicMock() for _ in range(4)]
    body.data.edges = [MagicMock() for _ in range(4)]
    body.data.polygons = [MagicMock()]
    body.modifiers = _Modifiers()
    cutter = MagicMock()
    cutter.name = "Cutter"
    cutter.type = "MESH"
    bpy = make_mock_bpy()
    bpy.data.objects.get.side_effect = lambda name: {"Body": body, "Cutter": cutter}.get(name)

    def apply_modifier(*, modifier):
        body.modifiers.remove(body.modifiers.get(modifier))
        body.data.polygons.append(MagicMock())
        return {"FINISHED"}

    bpy.ops.object.modifier_apply.side_effect = apply_modifier
    result = load_and_call(
        "blender-mesh-ops/scripts/boolean_op.py",
        bpy,
        input_a="Body",
        input_b="Cutter",
        operation="subtract",
        output_name="Result",
    )

    assert result["success"] is False
    assert result["context"]["mutation_applied"] is True
    assert result["context"]["actual_object_name"] == "Result.001"
    assert result["context"]["requested_output_name"] == "Result"


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
    bpy.context.scene.collection.children = _LinkedObjects()
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


def test_group_parent_uses_stable_parent_identity_for_rewrapped_objects() -> None:
    parent = MagicMock()
    parent.name = "Aircraft"
    parent.as_pointer.return_value = 1001
    parent_proxy = MagicMock()
    parent_proxy.name = "Aircraft"
    parent_proxy.as_pointer.return_value = 1001

    class _Child:
        name = "Pylon"
        type = "MESH"
        matrix_world = None

        def __init__(self):
            self._parent = None

        @property
        def parent(self):
            return parent_proxy if self._parent is not None else None

        @parent.setter
        def parent(self, value):
            self._parent = value

    child = _Child()
    bpy = make_mock_bpy()
    bpy.data.objects.get.side_effect = lambda name: {"Aircraft": parent, "Pylon": child}.get(name)
    bpy.data.collections = _Collections()
    bpy.context.scene.collection.children = _LinkedObjects()

    result = load_and_call(
        "blender-mesh-ops/scripts/group_parent.py",
        bpy,
        object_names=["Pylon"],
        group_name="Pylons",
        parent_name="Aircraft",
    )

    assert result["success"] is True, result
    assert result["context"]["readback"]["parented"] == ["Pylon"]


def test_group_parent_reports_partial_parenting_when_collection_link_readback_fails() -> None:
    parent = MagicMock()
    parent.name = "Aircraft"
    child = MagicMock()
    child.name = "Pylon"
    child.type = "MESH"
    collection = MagicMock()
    collection.name = "Pylons"
    collection.objects = _LinkedObjects()
    collection.objects.link = MagicMock()
    bpy = make_mock_bpy()
    bpy.data.objects.get.side_effect = lambda name: {"Aircraft": parent, "Pylon": child}.get(name)
    bpy.data.collections.get.return_value = collection
    bpy.context.scene.collection.children = _LinkedObjects([collection])

    result = load_and_call(
        "blender-mesh-ops/scripts/group_parent.py",
        bpy,
        object_names=["Pylon"],
        group_name="Pylons",
        parent_name="Aircraft",
    )

    assert result["success"] is False
    assert result["context"]["mutation_applied"] is True
    assert result["context"]["rollback_attempted"] is True
    assert result["context"]["members"] == []
    assert result["context"]["parented"] == ["Pylon"]


def test_group_parent_rejects_and_removes_an_orphan_new_collection() -> None:
    child = MagicMock()
    child.name = "Pylon"
    child.type = "MESH"
    bpy = make_mock_bpy()
    bpy.data.objects.get.return_value = child
    bpy.data.collections = _Collections()
    bpy.context.scene.collection.children = _LinkedObjects()
    bpy.context.scene.collection.children.link = MagicMock()

    result = load_and_call(
        "blender-mesh-ops/scripts/group_parent.py",
        bpy,
        object_names=["Pylon"],
        group_name="Pylons",
    )

    assert result["success"] is False
    assert result["context"]["scene_linked"] is False
    assert result["context"]["rollback_attempted"] is True
    assert result["context"]["rollback_verified"] is True
    assert bpy.data.collections == []


def test_group_parent_rolls_back_when_existing_collection_link_mutates_then_raises() -> None:
    child = MagicMock()
    child.name = "Pylon"
    child.type = "MESH"
    collection = MagicMock()
    collection.name = "Pylons"
    collection.objects = _LinkedObjects()

    def link_then_raise(obj):
        collection.objects.append(obj)
        raise RuntimeError("link failed after mutation")

    collection.objects.link = link_then_raise
    bpy = make_mock_bpy()
    bpy.data.objects.get.return_value = child
    bpy.data.collections.get.return_value = collection
    bpy.context.scene.collection.children = _LinkedObjects([collection])

    result = load_and_call(
        "blender-mesh-ops/scripts/group_parent.py",
        bpy,
        object_names=["Pylon"],
        group_name="Pylons",
    )

    assert result["success"] is False
    assert result["context"]["mutation_applied"] is True
    assert result["context"]["rollback_attempted"] is True
    assert result["context"]["rollback_verified"] is True
    assert child not in collection.objects


def test_material_assignment_exception_rolls_back_new_slots_with_receipt() -> None:
    class _FailingSlot:
        def __init__(self):
            self._material = None

        @property
        def material(self):
            return self._material

        @material.setter
        def material(self, value):
            raise RuntimeError("assignment failed")

    body = MagicMock()
    body.name = "Body"
    body.type = "MESH"
    body.data = MagicMock(name="BodyMesh")
    body.material_slots = []
    material = MagicMock()
    material.name = "Paint"
    bpy = make_mock_bpy()
    bpy.data.objects.get.return_value = body
    bpy.data.materials.get.return_value = material
    bpy.ops.object.material_slot_add.side_effect = lambda: body.material_slots.append(_FailingSlot()) or {"FINISHED"}
    bpy.ops.object.material_slot_remove.side_effect = lambda: body.material_slots.pop() and {"FINISHED"}

    result = load_and_call(
        "blender-mesh-ops/scripts/modeling_assign_material.py",
        bpy,
        object_name="Body",
        material_name="Paint",
    )

    assert result["success"] is False
    assert result["context"]["mutation_applied"] is True
    assert result["context"]["rollback_attempted"] is True
    assert result["context"]["rollback_verified"] is True
    assert body.material_slots == []


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

    def smart_project(**_kwargs):
        mesh.uv_layers.active.data = [MagicMock(uv=[0.0, 0.0]), MagicMock(uv=[1.0, 1.0])]
        return {"FINISHED"}

    def cylinder_project(**_kwargs):
        mesh.uv_layers.active.data = [MagicMock(uv=[0.25, 0.0]), MagicMock(uv=[0.75, 1.0])]
        return {"FINISHED"}

    bpy.ops.uv.smart_project.side_effect = smart_project
    bpy.ops.uv.cylinder_project.side_effect = cylinder_project

    automatic = load_and_call(
        "blender-mesh-ops/scripts/auto_uv.py",
        bpy,
        object_name="Body",
        margin=0.01,
    )
    assert automatic["success"] is True, automatic
    assert automatic["context"]["readback"]["active_uv_map"] == "UVMap"
    assert automatic["context"]["readback"]["uv_map_count"] == 1
    assert automatic["context"]["readback"]["uv_coordinate_count"] == 2
    assert len(automatic["context"]["readback"]["uv_digest"]) == 64
    assert automatic["context"]["readback"]["verified"] is True

    projected = load_and_call(
        "blender-mesh-ops/scripts/uv_project.py",
        bpy,
        object_name="Body",
        projection="cylindrical",
        axis="z",
        margin=0.02,
    )
    assert projected["success"] is True, projected
    assert projected["context"]["parameters"]["projection"] == "cylindrical"
    assert projected["context"]["parameters"]["axis"] is None
    assert projected["context"]["readback"]["active_uv_map"] == "UVMap"
    assert projected["context"]["readback"]["verified"] is True


def test_uv_project_rejects_non_planar_axis_instead_of_echoing_it() -> None:
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

    result = load_and_call(
        "blender-mesh-ops/scripts/uv_project.py",
        bpy,
        object_name="Body",
        projection="cylindrical",
        axis="y",
    )

    assert result["success"] is False
    assert "planar projection only" in result["error"]
    bpy.ops.uv.cylinder_project.assert_not_called()


def test_auto_uv_rejects_cancelled_operator_with_layer_mutation_receipt() -> None:
    mesh = MagicMock()
    mesh.name = "BodyMesh"
    mesh.vertices = []
    mesh.edges = []
    mesh.loops = [MagicMock(), MagicMock()]
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

    def cancelled_projection(**_kwargs):
        mesh.uv_layers.active.data = [MagicMock(uv=[0.0, 0.0]), MagicMock(uv=[0.0, 0.0])]
        return {"CANCELLED"}

    bpy.ops.uv.smart_project.side_effect = cancelled_projection
    result = load_and_call(
        "blender-mesh-ops/scripts/auto_uv.py",
        bpy,
        object_name="Body",
        margin=0.01,
    )

    assert result["success"] is False
    assert result["context"]["operator_result"] == ["CANCELLED"]
    assert result["context"]["mutation_applied"] is True
    assert result["context"]["uv_before"]["uv_map_count"] == 0
    assert result["context"]["uv_after"]["uv_map_count"] == 1


def test_pivot_and_freeze_reject_cancelled_operators_even_when_readback_already_matches() -> None:
    obj = MagicMock()
    obj.name = "Body"
    obj.type = "MESH"
    obj.location = [0.0, 0.0, 0.0]
    obj.rotation_euler = [0.0, 0.0, 0.0]
    obj.scale = [1.0, 1.0, 1.0]
    obj.matrix_world.translation = [0.0, 0.0, 0.0]
    bpy = make_mock_bpy()
    bpy.data.objects.get.return_value = obj
    bpy.context.scene.cursor.location = [3.0, 4.0, 5.0]
    bpy.ops.object.origin_set.return_value = {"CANCELLED"}
    bpy.ops.object.transform_apply.return_value = {"CANCELLED"}

    pivot = load_and_call(
        "blender-mesh-ops/scripts/set_pivot.py",
        bpy,
        object_name="Body",
        position=[0.0, 0.0, 0.0],
    )
    frozen = load_and_call(
        "blender-mesh-ops/scripts/modeling_freeze_transforms.py",
        bpy,
        object_name="Body",
        location=True,
        rotation=True,
        scale=True,
    )

    for result in (pivot, frozen):
        assert result["success"] is False
        assert result["context"]["mutation_applied"] is False
        assert result["context"]["rollback_attempted"] is False
        assert result["context"]["rollback_verified"] is False
    assert bpy.context.scene.cursor.location == [3.0, 4.0, 5.0]


def test_pivot_and_freeze_report_mutation_when_operators_raise_after_changes() -> None:
    obj = MagicMock()
    obj.name = "Body"
    obj.type = "MESH"
    obj.matrix_world.translation = [1.0, 2.0, 3.0]
    obj.location = [1.0, 2.0, 3.0]
    obj.rotation_euler = [0.2, 0.3, 0.4]
    obj.scale = [2.0, 2.0, 2.0]
    bpy = make_mock_bpy()
    bpy.data.objects.get.return_value = obj
    bpy.context.scene.cursor.location = [9.0, 9.0, 9.0]

    def origin_then_raise(**_kwargs):
        obj.matrix_world.translation = [0.0, 0.0, 0.0]
        raise RuntimeError("origin readback failed")

    bpy.ops.object.origin_set.side_effect = origin_then_raise
    pivot = load_and_call(
        "blender-mesh-ops/scripts/set_pivot.py",
        bpy,
        object_name="Body",
        position=[0.0, 0.0, 0.0],
    )
    assert pivot["success"] is False
    assert pivot["context"]["mutation_applied"] is True
    assert pivot["context"]["position_before"] == [1.0, 2.0, 3.0]
    assert pivot["context"]["position_after"] == [0.0, 0.0, 0.0]

    def transform_then_raise(**_kwargs):
        obj.rotation_euler = [0.0, 0.0, 0.0]
        raise RuntimeError("transform readback failed")

    bpy.ops.object.transform_apply.side_effect = transform_then_raise
    frozen = load_and_call(
        "blender-mesh-ops/scripts/modeling_freeze_transforms.py",
        bpy,
        object_name="Body",
        rotation=True,
        scale=False,
    )
    assert frozen["success"] is False
    assert frozen["context"]["mutation_applied"] is True
    assert frozen["context"]["transform_before"]["rotation"] == [0.2, 0.3, 0.4]
    assert frozen["context"]["transform_after"]["rotation"] == [0.0, 0.0, 0.0]


def test_freeze_transforms_reports_partial_mutation_when_finished_readback_fails() -> None:
    obj = MagicMock()
    obj.name = "Body"
    obj.type = "MESH"
    obj.location = [0.0, 0.0, 0.0]
    obj.rotation_euler = [0.2, 0.3, 0.4]
    obj.scale = [2.0, 2.0, 2.0]
    bpy = make_mock_bpy()
    bpy.data.objects.get.return_value = obj

    def partial_apply(*, location, rotation, scale):
        assert location is False
        assert rotation is True
        assert scale is True
        obj.rotation_euler = [0.0, 0.0, 0.0]
        return {"FINISHED"}

    bpy.ops.object.transform_apply.side_effect = partial_apply
    result = load_and_call(
        "blender-mesh-ops/scripts/modeling_freeze_transforms.py",
        bpy,
        object_name="Body",
        location=False,
        rotation=True,
        scale=True,
    )

    assert result["success"] is False
    assert result["context"]["mutation_applied"] is True
    assert result["context"]["rollback_attempted"] is False
    assert result["context"]["rollback_verified"] is False
    assert result["context"]["transform_before"]["rotation"] == [0.2, 0.3, 0.4]
    assert result["context"]["transform_after"]["rotation"] == [0.0, 0.0, 0.0]
    assert result["context"]["transform_after"]["scale"] == [2.0, 2.0, 2.0]


def test_assign_material_stops_when_slot_creation_is_cancelled_or_makes_no_progress() -> None:
    material = MagicMock(name="Paint")
    material.name = "Paint"
    obj = MagicMock(name="Body")
    obj.name = "Body"
    obj.type = "MESH"
    obj.data = MagicMock(name="BodyMesh")
    obj.material_slots = []
    bpy = make_mock_bpy()
    bpy.data.objects.get.return_value = obj
    bpy.data.materials.get.return_value = material

    bpy.ops.object.material_slot_add.return_value = {"CANCELLED"}
    cancelled = load_and_call(
        "blender-mesh-ops/scripts/modeling_assign_material.py",
        bpy,
        object_name="Body",
        material_name="Paint",
        slot_index=0,
    )
    assert cancelled["success"] is False
    assert bpy.ops.object.material_slot_add.call_count == 1

    bpy.ops.object.material_slot_add.reset_mock(return_value=True, side_effect=True)
    bpy.ops.object.material_slot_add.return_value = {"FINISHED"}
    no_progress = load_and_call(
        "blender-mesh-ops/scripts/modeling_assign_material.py",
        bpy,
        object_name="Body",
        material_name="Paint",
        slot_index=0,
    )
    assert no_progress["success"] is False
    assert bpy.ops.object.material_slot_add.call_count == 1


def test_delete_history_reports_partial_mutation_and_stops_on_cancelled_modifier() -> None:
    first = MagicMock(name="Bevel")
    first.name = "Bevel"
    second = MagicMock(name="Mirror")
    second.name = "Mirror"
    obj = MagicMock(name="Body")
    obj.name = "Body"
    obj.type = "MESH"
    obj.data = MagicMock(name="BodyMesh")
    obj.data.vertices = [MagicMock() for _ in range(4)]
    obj.data.edges = [MagicMock() for _ in range(4)]
    obj.data.polygons = [MagicMock()]
    obj.modifiers = _Modifiers([first, second])
    bpy = make_mock_bpy()
    bpy.data.objects.get.return_value = obj

    def apply_modifier(*, modifier):
        if modifier == "Bevel":
            obj.modifiers.remove(first)
            obj.data.polygons.append(MagicMock())
            return {"FINISHED"}
        return {"CANCELLED"}

    bpy.ops.object.modifier_apply.side_effect = apply_modifier
    result = load_and_call(
        "blender-mesh-ops/scripts/delete_history.py",
        bpy,
        object_name="Body",
    )

    assert result["success"] is False
    assert result["context"]["mutation_applied"] is True
    assert result["context"]["applied_modifiers"] == ["Bevel"]
    assert result["context"]["remaining_modifiers"] == ["Mirror"]
    assert result["context"]["failed_modifier"] == "Mirror"
    assert result["context"]["mesh_before"]["face_count"] == 1
    assert result["context"]["mesh_after"]["face_count"] == 2


def test_boolean_operand_uses_blender_pointer_identity_instead_of_python_wrapper_identity() -> None:
    pointer = 4242
    right = MagicMock(name="Cutter")
    right.name = "Cutter"
    right.type = "MESH"
    right.as_pointer.return_value = pointer
    wrapper = MagicMock(name="CutterWrapper")
    wrapper.name = "Cutter"
    wrapper.as_pointer.return_value = pointer

    class _BooleanModifier:
        name = "Boolean_Operation"
        type = "BOOLEAN"
        operation = "DIFFERENCE"
        solver = "EXACT"

        @property
        def object(self):
            return wrapper

        @object.setter
        def object(self, _value):
            pass

    class _BooleanModifiers(_Modifiers):
        def new(self, name, type):
            modifier = _BooleanModifier()
            modifier.name = name
            modifier.type = type
            self.append(modifier)
            return modifier

    left = MagicMock(name="Body")
    left.name = "Body"
    left.type = "MESH"
    left.data = MagicMock(name="BodyMesh")
    left.data.vertices = [MagicMock() for _ in range(4)]
    left.data.edges = [MagicMock() for _ in range(4)]
    left.data.polygons = [MagicMock()]
    left.modifiers = _BooleanModifiers()
    bpy = make_mock_bpy()
    bpy.data.objects.get.side_effect = lambda name: {"Body": left, "Cutter": right}.get(name)

    result = load_and_call(
        "blender-mesh-ops/scripts/boolean_op.py",
        bpy,
        input_a="Body",
        input_b="Cutter",
        operation="subtract",
        apply=False,
    )

    assert result["success"] is True, result
    assert result["context"]["readback"]["modifier_present"] is True


def test_boolean_configuration_failure_removes_the_new_modifier() -> None:
    right = MagicMock(name="Cutter")
    right.name = "Cutter"
    right.type = "MESH"
    right.as_pointer.return_value = 4242
    wrong_wrapper = MagicMock(name="WrongOperand")
    wrong_wrapper.as_pointer.return_value = 7331

    class _RejectedBooleanModifier:
        name = "Boolean_Operation"
        type = "BOOLEAN"
        operation = "DIFFERENCE"
        solver = "EXACT"

        @property
        def object(self):
            return wrong_wrapper

        @object.setter
        def object(self, _value):
            pass

    class _RejectedModifiers(_Modifiers):
        def new(self, name, type):
            modifier = _RejectedBooleanModifier()
            modifier.name = name
            modifier.type = type
            self.append(modifier)
            return modifier

    left = MagicMock(name="Body")
    left.name = "Body"
    left.type = "MESH"
    left.data = MagicMock(name="BodyMesh")
    left.data.vertices = [MagicMock() for _ in range(4)]
    left.data.edges = [MagicMock() for _ in range(4)]
    left.data.polygons = [MagicMock()]
    left.modifiers = _RejectedModifiers()
    bpy = make_mock_bpy()
    bpy.data.objects.get.side_effect = lambda name: {"Body": left, "Cutter": right}.get(name)

    result = load_and_call(
        "blender-mesh-ops/scripts/boolean_op.py",
        bpy,
        input_a="Body",
        input_b="Cutter",
        operation="subtract",
        apply=False,
    )

    assert result["success"] is False
    assert result["context"]["rollback_attempted"] is True
    assert result["context"]["rollback_verified"] is True
    assert result["context"]["mutation_applied"] is False
    assert left.modifiers == []


def test_delete_history_keeps_partial_receipt_when_failure_evidence_raises() -> None:
    class _BrokenVertices:
        def __len__(self):
            return 4

        def __iter__(self):
            raise RuntimeError("vertex readback failed")

    body = MagicMock()
    body.name = "Body"
    body.type = "MESH"
    body.data = MagicMock(name="BodyMesh")
    body.data.vertices = [MagicMock() for _ in range(4)]
    body.data.edges = [MagicMock() for _ in range(4)]
    body.data.polygons = [MagicMock()]
    bevel = MagicMock(name="Bevel")
    bevel.name = "Bevel"
    mirror = MagicMock(name="Mirror")
    mirror.name = "Mirror"
    body.modifiers = _Modifiers([bevel, mirror])
    bpy = make_mock_bpy()
    bpy.data.objects.get.return_value = body

    def apply_modifier(*, modifier):
        if modifier == "Bevel":
            body.modifiers.remove(bevel)
            body.data.vertices = _BrokenVertices()
            return {"FINISHED"}
        return {"CANCELLED"}

    bpy.ops.object.modifier_apply.side_effect = apply_modifier
    result = load_and_call(
        "blender-mesh-ops/scripts/delete_history.py",
        bpy,
        object_name="Body",
    )

    assert result["success"] is False
    assert result["context"]["mutation_applied"] is True
    assert result["context"]["rollback_attempted"] is False
    assert result["context"]["applied_modifiers"] == ["Bevel"]
    assert result["context"]["remaining_modifiers"] == ["Mirror"]
    assert result["context"]["failed_modifier"] == "Mirror"
    assert result["context"]["error_type"] == "RuntimeError"


def test_modeling_contracts_mark_potentially_destructive_mesh_changes() -> None:
    tools = yaml.safe_load((SKILL_ROOT / "tools.yaml").read_text(encoding="utf-8"))["tools"]
    contracts = {tool["name"]: tool for tool in tools}
    destructive = {
        "add_edge_loop",
        "array_instances",
        "auto_uv",
        "bevel_edges",
        "boolean_op",
        "extrude_faces",
        "inset",
        "mirror",
        "uv_project",
    }

    for name in destructive:
        assert contracts[name]["destructive"] is True, name
        assert contracts[name]["annotations"]["destructive_hint"] is True, name


def test_mesh_state_rejects_unbounded_evidence_before_iteration() -> None:
    from dcc_mcp_blender._modeling_common import mesh_state

    class _TooLarge:
        def __len__(self):
            return 10_000_001

        def __iter__(self):
            raise AssertionError("oversized evidence must be rejected before iteration")

    obj = MagicMock()
    obj.data.vertices = _TooLarge()
    obj.data.edges = []
    obj.data.polygons = []

    with pytest.raises(ValueError, match="evidence limit"):
        mesh_state(obj)


def test_auto_uv_rejects_an_unchanged_positive_uv_map() -> None:
    mesh = MagicMock()
    mesh.name = "BodyMesh"
    mesh.vertices = [MagicMock() for _ in range(4)]
    mesh.edges = [MagicMock() for _ in range(4)]
    mesh.loops = [MagicMock() for _ in range(4)]
    mesh.polygons = [MagicMock()]
    mesh.uv_layers = _UVLayers()
    layer = mesh.uv_layers.new("UVMap")
    layer.data = [MagicMock(uv=[0.0, 0.0]), MagicMock(uv=[1.0, 1.0])]
    obj = MagicMock()
    obj.name = "Body"
    obj.type = "MESH"
    obj.mode = "OBJECT"
    obj.data = mesh
    bpy = make_mock_bpy()
    bpy.data.objects.get.return_value = obj
    bpy.ops.uv = MagicMock()
    bpy.ops.uv.smart_project.return_value = {"FINISHED"}

    result = load_and_call(
        "blender-mesh-ops/scripts/auto_uv.py",
        bpy,
        object_name="Body",
        margin=0.01,
    )

    assert result["success"] is False
    assert result["context"]["mutation_applied"] is True


def test_auto_uv_reports_mutation_when_post_operation_evidence_exceeds_the_bound() -> None:
    class _TooLarge:
        def __len__(self):
            return 10_000_001

        def __iter__(self):
            raise AssertionError("bounded failure receipts must not iterate oversized UV evidence")

    mesh = MagicMock()
    mesh.name = "BodyMesh"
    mesh.vertices = [MagicMock() for _ in range(4)]
    mesh.edges = [MagicMock() for _ in range(4)]
    mesh.loops = [MagicMock() for _ in range(4)]
    mesh.polygons = [MagicMock()]
    mesh.uv_layers = _UVLayers()
    mesh.uv_layers.new("UVMap")
    obj = MagicMock()
    obj.name = "Body"
    obj.type = "MESH"
    obj.mode = "OBJECT"
    obj.data = mesh
    bpy = make_mock_bpy()
    bpy.data.objects.get.return_value = obj
    bpy.ops.uv = MagicMock()

    def oversized_uv(**_kwargs):
        mesh.uv_layers.active.data = _TooLarge()
        return {"FINISHED"}

    bpy.ops.uv.smart_project.side_effect = oversized_uv
    result = load_and_call(
        "blender-mesh-ops/scripts/auto_uv.py",
        bpy,
        object_name="Body",
        margin=0.01,
    )

    assert result["success"] is False
    assert result["context"]["mutation_applied"] is True
    assert result["context"]["rollback_attempted"] is False
    assert result["context"]["rollback_verified"] is False
    assert result["context"]["uv_after_counts"]["uv_coordinate_count"] == 10_000_001
    assert result["context"]["uv_after_counts"]["evidence_limited"] is True


def test_lathe_refuses_to_overwrite_the_source_profile_name() -> None:
    profile = _profile_object("Profile")
    bpy = make_mock_bpy()
    bpy.data.objects.get.return_value = profile

    result = load_and_call(
        "blender-mesh-ops/scripts/lathe_profile.py",
        bpy,
        profile="Profile",
        output_name="Profile",
    )

    assert result["success"] is False
    assert "already exists" in result["message"].lower()
    profile.copy.assert_not_called()


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
    bpy.ops.object.join.return_value = {"FINISHED"}
    bpy.ops.object.origin_set.return_value = {"FINISHED"}
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


def test_loft_rejects_cancelled_bridge_after_partial_mutation_and_cleans_output() -> None:
    section_a = _profile_object("SectionA")
    section_b = _profile_object("SectionB")
    lofted = _profile_object("SectionA_copy")
    section_b_copy = _profile_object("SectionB_copy")
    copies = iter([lofted, section_b_copy])
    section_a.copy.side_effect = lambda: next(copies)
    section_b.copy.side_effect = lambda: next(copies)
    section_a.data.copy.return_value = lofted.data
    section_b.data.copy.return_value = section_b_copy.data
    bpy = make_mock_bpy()
    bpy.data.objects.get.side_effect = lambda name: {"SectionA": section_a, "SectionB": section_b}.get(name)
    bpy.ops.object.join.return_value = {"FINISHED"}

    def cancelled_bridge(**_kwargs):
        lofted.data.polygons.append(MagicMock(index=0))
        return {"CANCELLED"}

    bpy.ops.mesh.bridge_edge_loops.side_effect = cancelled_bridge
    result = load_and_call(
        "blender-mesh-ops/scripts/loft_sections.py",
        bpy,
        sections=["SectionA", "SectionB"],
        output_name="Fuselage",
    )

    assert result["success"] is False
    assert result["context"]["mutation_applied"] is True
    assert result["context"]["rollback_attempted"] is True
    assert result["context"]["rollback_verified"] is True
    assert result["context"]["failed_operator"] == "bridge_edge_loops"
    assert result["context"]["mesh_after"]["face_count"] == 1


def test_loft_claims_each_duplicate_before_a_later_copy_raises() -> None:
    section_a = _profile_object("SectionA")
    section_b = _profile_object("SectionB")
    first_copy = _profile_object("SectionA_copy")
    section_a.copy.return_value = first_copy
    section_a.data.copy.return_value = first_copy.data
    section_b.copy.side_effect = RuntimeError("second copy failed")
    registry = [section_a, section_b]
    bpy = make_mock_bpy()
    bpy.data.objects.get.side_effect = lambda name: {"SectionA": section_a, "SectionB": section_b}.get(name)
    bpy.data.objects.__iter__.side_effect = lambda: iter(registry)
    bpy.context.collection.objects.link.side_effect = lambda obj: registry.append(obj)
    bpy.data.objects.remove.side_effect = lambda obj, **_kwargs: registry.remove(obj)

    result = load_and_call(
        "blender-mesh-ops/scripts/loft_sections.py",
        bpy,
        sections=["SectionA", "SectionB"],
        output_name="Fuselage",
    )

    assert result["success"] is False
    assert result["context"]["mutation_applied"] is True
    assert result["context"]["rollback_attempted"] is True
    assert result["context"]["rollback_verified"] is True
    assert first_copy not in registry


def test_lathe_rejects_cancelled_apply_after_partial_mutation_and_cleans_output() -> None:
    source = _profile_object("Profile")
    duplicate = _profile_object("Profile_copy")
    source.copy.return_value = duplicate
    source.data.copy.return_value = duplicate.data
    bpy = make_mock_bpy()
    bpy.data.objects.get.side_effect = lambda name: source if name == "Profile" else None
    bpy.ops.object.origin_set.return_value = {"FINISHED"}

    def cancelled_apply(*, modifier):
        assert modifier == "Lathe_Profile"
        duplicate.data.polygons.append(MagicMock(index=0))
        return {"CANCELLED"}

    bpy.ops.object.modifier_apply.side_effect = cancelled_apply
    result = load_and_call(
        "blender-mesh-ops/scripts/lathe_profile.py",
        bpy,
        profile="Profile",
        axis="y",
        origin=[0.0, 0.0, 0.0],
        output_name="RotorHub",
    )

    assert result["success"] is False
    assert result["context"]["mutation_applied"] is True
    assert result["context"]["rollback_attempted"] is True
    assert result["context"]["rollback_verified"] is True
    assert result["context"]["failed_operator"] == "modifier_apply"
    assert result["context"]["mesh_after"]["face_count"] == 1
