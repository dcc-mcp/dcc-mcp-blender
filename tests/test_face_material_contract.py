"""Bounded face-material discovery and mutation with truthful failure receipts."""

from __future__ import annotations

import re
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import jsonschema
import pytest
import yaml

from dcc_mcp_blender._face_material_ops import assign_face_materials, inspect_face_materials
from dcc_mcp_blender._mesh_query_ops import mesh_revision
from tests.conftest import SKILLS_ROOT, load_and_call

REVISION_PATTERN = r"^face-materials-v1:[0-9a-f]{64}$"
INSPECT_SCRIPT = "blender-materials/scripts/inspect_face_materials.py"
ASSIGN_SCRIPT = "blender-materials/scripts/assign_face_materials.py"


class Face:
    """A polygon whose setter can fail before or after changing host state."""

    def __init__(self, index, material_index):
        self.index = index
        self.vertices = (0, 1, 2)
        self.normal = (0.0, 0.0, 1.0)
        self.select = index % 2 == 0
        self._material_index = material_index
        self.writes = []
        self.on_write = None
        self.read_error = False

    @property
    def material_index(self):
        if self.read_error:
            raise RuntimeError("Injected readback failure")
        return self._material_index

    @material_index.setter
    def material_index(self, value):
        self.writes.append(value)
        if self.on_write is not None:
            self.on_write(self, value)
        else:
            self._material_index = value


def material_host(face_count=4):
    """Keep mesh revision inputs real while rejecting any use of operators."""
    materials = [SimpleNamespace(name=name, library=None) for name in ("Red", "Blue", "Gold")]
    mesh = SimpleNamespace(
        name="PanelMesh",
        is_editmode=False,
        is_editable=True,
        library=None,
        override_library=None,
        users=1,
        vertices=[
            SimpleNamespace(index=index, co=co, normal=(0.0, 0.0, 1.0), select=False)
            for index, co in enumerate(((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)))
        ],
        edges=[
            SimpleNamespace(index=index, vertices=pair, select=False)
            for index, pair in enumerate(((0, 1), (1, 2), (2, 0)))
        ],
        polygons=[Face(index, (0, 1, 0, 2)[index % 4]) for index in range(face_count)],
        loops=[SimpleNamespace(vertex_index=index % 3, edge_index=index % 3) for index in range(3 * face_count)],
        materials=materials,
        update=Mock(),
    )
    obj = SimpleNamespace(
        name="Panel",
        type="MESH",
        mode="OBJECT",
        data=mesh,
        is_editable=True,
        library=None,
        override_library=None,
        material_slots=[SimpleNamespace(material=material, link="DATA") for material in materials],
        active_material_index=2,
        select_get=lambda: False,
        select_set=Mock(),
    )
    unrelated = SimpleNamespace(name="Unrelated", mode="OBJECT")
    host = SimpleNamespace(
        data=SimpleNamespace(objects={obj.name: obj, unrelated.name: unrelated}),
        context=SimpleNamespace(
            mode="OBJECT",
            active_object=unrelated,
            selected_objects=[unrelated],
            view_layer=SimpleNamespace(objects=SimpleNamespace(active=unrelated)),
        ),
        ops=Mock(),
    )
    return host, obj


@pytest.fixture
def host(monkeypatch):
    bpy, obj = material_host()
    monkeypatch.setitem(sys.modules, "bpy", bpy)
    return bpy, obj


def revision_for(obj):
    result = inspect_face_materials(obj.name)
    assert result["success"] is True, result
    revision = result["context"]["revision"]
    assert re.fullmatch(REVISION_PATTERN, revision)
    return revision


def assignments_of(obj):
    return [face._material_index for face in obj.data.polygons]


def host_snapshot(bpy, obj):
    return {
        "assignments": assignments_of(obj),
        "mesh_revision": mesh_revision(obj)[0],
        "object_mode": obj.mode,
        "mesh_editmode": obj.data.is_editmode,
        "active_object": id(bpy.context.active_object),
        "view_layer_active": id(bpy.context.view_layer.objects.active),
        "selected_objects": [id(item) for item in bpy.context.selected_objects],
        "face_selection": [face.select for face in obj.data.polygons],
        "vertex_selection": [vertex.select for vertex in obj.data.vertices],
        "edge_selection": [edge.select for edge in obj.data.edges],
        "active_material_index": obj.active_material_index,
        "slots": [(id(slot), id(slot.material), slot.link) for slot in obj.material_slots],
        "materials": [id(material) for material in obj.data.materials],
    }


def assert_preflight_failure(result, bpy, obj, before):
    assert result["success"] is False, result
    assert isinstance(result["context"]["error_code"], str)
    assert result["context"]["mutation_applied"] is False
    assert result["context"].get("rollback_attempted", False) is False
    assert host_snapshot(bpy, obj) == before
    assert not any(face.writes for face in obj.data.polygons)
    assert bpy.ops.mock_calls == []
    obj.select_set.assert_not_called()
    obj.data.update.assert_not_called()


def test_inspection_pages_are_bounded_revision_pinned_and_read_only(host):
    bpy, obj = host
    before = host_snapshot(bpy, obj)

    first = inspect_face_materials(obj.name, limit=2)
    assert first["success"] is True
    context = first["context"]
    assert context["object_name"] == obj.name
    assert context["mesh_name"] == obj.data.name
    assert context["face_count"] == 4
    assert context["assignments"] == [
        {"face_index": 0, "material_index": 0},
        {"face_index": 1, "material_index": 1},
    ]
    assert context["next_offset"] == 2
    assert context["material_slots"] == [
        {"material_index": index, "material_name": name, "link": "DATA"}
        for index, name in enumerate(("Red", "Blue", "Gold"))
    ]
    assert context["mutation_applied"] is False
    assert re.fullmatch(REVISION_PATTERN, context["revision"])

    second = inspect_face_materials(obj.name, offset=2, limit=2, expected_revision=context["revision"])
    assert second["success"] is True
    assert second["context"]["revision"] == context["revision"]
    assert second["context"]["assignments"] == [
        {"face_index": 2, "material_index": 0},
        {"face_index": 3, "material_index": 2},
    ]
    assert second["context"]["next_offset"] is None
    assert host_snapshot(bpy, obj) == before
    assert bpy.ops.mock_calls == []
    obj.data.update.assert_not_called()


@pytest.mark.parametrize("offset", [4, 100_000])
def test_inspection_past_end_returns_empty_page(host, offset):
    _, obj = host
    result = inspect_face_materials(obj.name, offset=offset, limit=256)
    assert result["success"] is True
    assert result["context"]["assignments"] == []
    assert result["context"]["next_offset"] is None


@pytest.mark.parametrize(
    "kwargs",
    [
        {"object_name": ""},
        {"object_name": " "},
        {"object_name": None},
        {"object_name": True},
        {"object_name": "x" * 1025},
        {"offset": -1},
        {"offset": 100_001},
        {"offset": True},
        {"offset": 0.5},
        {"limit": 0},
        {"limit": 257},
        {"limit": False},
        {"limit": 1.5},
        {"expected_revision": ""},
        {"expected_revision": True},
        {"expected_revision": "face-materials-v1:" + "g" * 64},
        {"expected_revision": "face-materials-v1:" + "a" * 63},
        {"expected_revision": "mesh-query-v1:" + "a" * 64},
    ],
)
def test_invalid_inspection_arguments_do_not_mutate(host, kwargs):
    bpy, obj = host
    before = host_snapshot(bpy, obj)
    arguments = {"object_name": obj.name}
    arguments.update(kwargs)
    result = inspect_face_materials(**arguments)
    assert_preflight_failure(result, bpy, obj, before)


def test_assignment_changes_only_requested_faces_and_repeats_safely(host):
    bpy, obj = host
    revision = revision_for(obj)
    before = host_snapshot(bpy, obj)
    assignments = [
        {"face_index": 2, "material_index": 1},
        {"face_index": 0, "material_index": 2},
        {"face_index": 1, "material_index": 1},
    ]
    result = assign_face_materials(obj.name, assignments, revision)

    assert result["success"] is True, result
    context = result["context"]
    assert context["object_name"] == obj.name
    assert context["mesh_name"] == obj.data.name
    assert context["face_count"] == 4
    assert context["revision"] == revision
    assert context["assignments"] == assignments
    assert context["affected_count"] == 3
    assert context["changed_count"] == 2
    assert context["mutation_applied"] is True
    assert result["postcondition"]["verified"] is True
    assert result["postcondition"]["method"] == "exact_polygon_material_indices_and_revision"
    assert assignments_of(obj) == [2, 1, 1, 2]
    assert obj.data.polygons[3].writes == []
    after = host_snapshot(bpy, obj)
    assert {key: value for key, value in after.items() if key != "assignments"} == {
        key: value for key, value in before.items() if key != "assignments"
    }
    assert bpy.ops.mock_calls == []
    obj.select_set.assert_not_called()

    repeated = assign_face_materials(obj.name, assignments, revision)
    assert repeated["success"] is True, repeated
    assert repeated["context"]["revision"] == revision
    assert repeated["context"]["assignments"] == assignments
    assert repeated["context"]["affected_count"] == 3
    assert repeated["context"]["changed_count"] == 0
    assert repeated["context"]["mutation_applied"] is False
    assert repeated["postcondition"]["verified"] is True
    assert host_snapshot(bpy, obj) == after


def test_effective_object_linked_material_slot_can_be_assigned_without_editing_slots(host):
    bpy, obj = host
    obj.material_slots[1].link = "OBJECT"
    obj.material_slots[1].material = SimpleNamespace(name="ObjectOverride", library=None)
    revision = revision_for(obj)
    before = host_snapshot(bpy, obj)
    result = assign_face_materials(obj.name, [{"face_index": 0, "material_index": 1}], revision)
    assert result["success"] is True, result
    assert result["postcondition"]["verified"] is True
    assert host_snapshot(bpy, obj)["slots"] == before["slots"]
    assert host_snapshot(bpy, obj)["materials"] == before["materials"]
    inspected = inspect_face_materials(obj.name, expected_revision=revision)
    assert inspected["context"]["material_slots"][1] == {
        "material_index": 1,
        "material_name": "ObjectOverride",
        "link": "OBJECT",
    }


@pytest.mark.parametrize(
    "assignments",
    [
        None,
        [],
        {},
        "0:1",
        ({"face_index": 0, "material_index": 1},),
        [None],
        [[]],
        [{"face_index": 0}],
        [{"material_index": 1}],
        [{"face_index": 0, "material_index": 1, "extra": True}],
        [{"face_index": True, "material_index": 1}],
        [{"face_index": 0, "material_index": False}],
        [{"face_index": 0.0, "material_index": 1}],
        [{"face_index": 0, "material_index": 1.0}],
        [{"face_index": "0", "material_index": 1}],
        [{"face_index": 0, "material_index": "1"}],
        [{"face_index": -1, "material_index": 1}],
        [{"face_index": 4, "material_index": 1}],
        [{"face_index": 0, "material_index": -1}],
        [{"face_index": 0, "material_index": 3}],
        [{"face_index": 100_000, "material_index": 1}],
        [{"face_index": 0, "material_index": 1024}],
        [{"face_index": 0, "material_index": 1}, {"face_index": 0, "material_index": 2}],
        [{"face_index": 0, "material_index": 1}, {"face_index": 0, "material_index": 1}],
        [{"face_index": 0, "material_index": 1}] * 4097,
        [{"face_index": 0, "material_index": 1}, {"face_index": 3, "material_index": 9}],
    ],
)
def test_all_assignment_records_are_validated_before_first_write(host, assignments):
    bpy, obj = host
    revision = revision_for(obj)
    before = host_snapshot(bpy, obj)
    result = assign_face_materials(obj.name, assignments, revision)
    assert_preflight_failure(result, bpy, obj, before)


@pytest.mark.parametrize("revision", [None, True, "", "invalid", "face-materials-v1:" + "a" * 63])
def test_assignment_requires_well_formed_revision(host, revision):
    bpy, obj = host
    before = host_snapshot(bpy, obj)
    result = assign_face_materials(obj.name, [{"face_index": 0, "material_index": 1}], revision)
    assert_preflight_failure(result, bpy, obj, before)


@pytest.mark.parametrize(
    "change",
    ["coordinate", "topology", "replacement_mesh", "replacement_material", "slot_order", "slot_link"],
)
def test_revision_detects_geometry_and_slot_identity_changes_before_assignment(host, change):
    bpy, obj = host
    revision = revision_for(obj)
    if change == "coordinate":
        obj.data.vertices[0].co = (1e-12, 0.0, 0.0)
    elif change == "topology":
        obj.data.polygons[0].vertices = (2, 1, 0)
    elif change == "replacement_mesh":
        _, replacement = material_host()
        obj.data = replacement.data
    elif change == "replacement_material":
        # Same display name is not the same material data-block.
        material = SimpleNamespace(name=obj.material_slots[0].material.name, library=None)
        obj.material_slots[0].material = material
        obj.data.materials[0] = material
    elif change == "slot_order":
        obj.material_slots[0], obj.material_slots[1] = obj.material_slots[1], obj.material_slots[0]
        obj.data.materials[0], obj.data.materials[1] = obj.data.materials[1], obj.data.materials[0]
    else:
        obj.material_slots[0].link = "OBJECT"
    before = host_snapshot(bpy, obj)

    result = assign_face_materials(obj.name, [{"face_index": 0, "material_index": 1}], revision)
    assert_preflight_failure(result, bpy, obj, before)
    inspection = inspect_face_materials(obj.name, expected_revision=revision)
    assert inspection["success"] is False
    assert inspection["context"]["mutation_applied"] is False
    assert revision_for(obj) != revision


@pytest.mark.parametrize(
    ("condition", "error_code"),
    [
        ("shared", "shared_mesh_data"),
        ("mesh_linked", "readonly_mesh_data"),
        ("object_linked", "readonly_mesh_data"),
        ("mesh_readonly", "readonly_mesh_data"),
        ("object_readonly", "readonly_mesh_data"),
        ("mesh_override", "readonly_mesh_data"),
        ("object_override", "readonly_mesh_data"),
        ("empty_slot", "empty_material_slot"),
        ("no_slots", "material_index_out_of_range"),
        ("empty_mesh", "empty_mesh"),
    ],
)
def test_unsafe_assignment_targets_fail_before_mutation(host, condition, error_code):
    bpy, obj = host
    if condition == "shared":
        obj.data.users = 2
    elif condition == "mesh_linked":
        obj.data.library = SimpleNamespace(filepath="/linked.blend")
    elif condition == "object_linked":
        obj.library = SimpleNamespace(filepath="/linked.blend")
    elif condition == "mesh_readonly":
        obj.data.is_editable = False
    elif condition == "object_readonly":
        obj.is_editable = False
    elif condition == "mesh_override":
        obj.data.override_library = SimpleNamespace()
    elif condition == "object_override":
        obj.override_library = SimpleNamespace()
    elif condition == "empty_slot":
        obj.material_slots[1].material = None
        obj.data.materials[1] = None
    elif condition == "no_slots":
        obj.material_slots = []
        obj.data.materials = []
    elif condition == "empty_mesh":
        obj.data.polygons = []
        obj.data.loops = []
    # Read-only discovery can still explain shared, readonly and empty targets.
    inspection = inspect_face_materials(obj.name)
    assert inspection["success"] is True, inspection
    revision = inspection["context"]["revision"]
    before = host_snapshot(bpy, obj)

    result = assign_face_materials(obj.name, [{"face_index": 0, "material_index": 1}], revision)
    assert_preflight_failure(result, bpy, obj, before)
    assert result["context"]["error_code"] == error_code


@pytest.mark.parametrize("condition", ["missing", "nonmesh", "edit", "sculpt", "mesh_edit", "oversize", "slot_limit"])
def test_discovery_and_assignment_reject_unsupported_hosts(host, condition):
    bpy, obj = host
    revision = revision_for(obj)
    if condition == "missing":
        del bpy.data.objects[obj.name]
    elif condition == "nonmesh":
        obj.type = "CURVE"
    elif condition == "edit":
        obj.mode = "EDIT"
    elif condition == "sculpt":
        obj.mode = "SCULPT"
    elif condition == "mesh_edit":
        obj.data.is_editmode = True
    elif condition == "oversize":
        obj.data.loops = range(100_000)
    else:
        obj.material_slots = [obj.material_slots[0]] * 1025
        obj.data.materials = [obj.data.materials[0]] * 1025
    before = host_snapshot(bpy, obj)

    inspected = inspect_face_materials(obj.name)
    assert_preflight_failure(inspected, bpy, obj, before)
    assigned = assign_face_materials(obj.name, [{"face_index": 0, "material_index": 1}], revision)
    assert_preflight_failure(assigned, bpy, obj, before)


def test_scan_and_material_slot_limits_are_inclusive(host):
    _, obj = host
    obj.data.loops = range(99_990)  # 3 vertices + 3 edges + 4 faces + loops.
    obj.material_slots = [obj.material_slots[0]] * 1024
    obj.data.materials = [obj.data.materials[0]] * 1024
    revision = revision_for(obj)
    result = assign_face_materials(obj.name, [{"face_index": 0, "material_index": 1023}], revision)
    assert result["success"] is True, result
    assert result["context"]["assignments"] == [{"face_index": 0, "material_index": 1023}]


@pytest.mark.parametrize("condition", ["nonfinite_coordinate", "unreadable_normal", "unreadable_assignment"])
def test_unreadable_preflight_is_not_reported_as_a_mutation(host, condition):
    bpy, obj = host
    revision = revision_for(obj)
    if condition == "nonfinite_coordinate":
        obj.data.vertices[0].co = (float("nan"), 0.0, 0.0)
    elif condition == "unreadable_normal":
        del obj.data.vertices[0].normal
    else:
        obj.data.polygons[2].read_error = True
    before = host_snapshot(bpy, obj)
    result = assign_face_materials(obj.name, [{"face_index": 0, "material_index": 1}], revision)
    assert_preflight_failure(result, bpy, obj, before)


def test_maximum_assignment_batch_is_accepted(monkeypatch):
    bpy, obj = material_host(face_count=4096)
    monkeypatch.setitem(sys.modules, "bpy", bpy)
    revision = revision_for(obj)
    assignments = [{"face_index": index, "material_index": 1} for index in range(4096)]
    result = assign_face_materials(obj.name, assignments, revision)
    assert result["success"] is True, result
    assert result["context"]["affected_count"] == 4096
    assert result["context"]["assignments"] == assignments
    assert result["postcondition"]["verified"] is True
    assert assignments_of(obj) == [1] * 4096
    page = inspect_face_materials(obj.name, limit=256, expected_revision=revision)
    assert page["success"] is True
    assert len(page["context"]["assignments"]) == 256
    assert page["context"]["next_offset"] == 256


def test_failure_after_a_write_restores_exact_preoperation_assignments(host):
    bpy, obj = host
    revision = revision_for(obj)
    before = host_snapshot(bpy, obj)

    def fail_first_write(face, value):
        if len(face.writes) == 1:
            # A setter can mutate and then raise. Rollback must include this
            # face, not only those whose setters returned successfully.
            face._material_index = value
            raise RuntimeError("Injected failure after setter mutation")
        face._material_index = value

    obj.data.polygons[1].on_write = fail_first_write
    result = assign_face_materials(
        obj.name, [{"face_index": 0, "material_index": 2}, {"face_index": 1, "material_index": 2}], revision
    )
    assert result["success"] is False
    context = result["context"]
    assert context["error_code"] == "face_material_assignment_failed"
    assert context["rollback_attempted"] is True
    assert context["rollback_verified"] is True
    assert context["mutation_applied"] is False
    assert host_snapshot(bpy, obj) == before
    assert obj.data.polygons[2].writes == []
    assert obj.data.polygons[3].writes == []


def test_silent_write_failure_is_detected_and_rolled_back(host):
    _, obj = host
    revision = revision_for(obj)
    before = assignments_of(obj)
    obj.data.polygons[1].on_write = lambda face, value: None
    result = assign_face_materials(
        obj.name, [{"face_index": 0, "material_index": 2}, {"face_index": 1, "material_index": 2}], revision
    )
    assert result["success"] is False
    assert result["context"]["error_code"] == "face_material_assignment_failed"
    assert result["context"]["rollback_attempted"] is True
    assert result["context"]["rollback_verified"] is True
    assert result["context"]["mutation_applied"] is False
    assert assignments_of(obj) == before


def test_verification_detects_and_restores_unrequested_face_changes(host):
    _, obj = host
    revision = revision_for(obj)
    before = assignments_of(obj)

    def change_another_face(face, value):
        face._material_index = value
        if value == 2:
            obj.data.polygons[3]._material_index = 0

    obj.data.polygons[0].on_write = change_another_face
    result = assign_face_materials(obj.name, [{"face_index": 0, "material_index": 2}], revision)
    assert result["success"] is False
    assert result["context"]["error_code"] == "face_material_assignment_failed"
    assert result["context"]["rollback_verified"] is True
    assert result["context"]["mutation_applied"] is False
    assert assignments_of(obj) == before


def test_update_failure_rolls_back_polygon_indices(host):
    _, obj = host
    revision = revision_for(obj)
    before = assignments_of(obj)
    obj.data.update.side_effect = [RuntimeError("Injected update failure"), None]
    result = assign_face_materials(obj.name, [{"face_index": 0, "material_index": 2}], revision)
    assert result["success"] is False
    assert result["context"]["error_code"] == "face_material_assignment_failed"
    assert result["context"]["rollback_attempted"] is True
    assert result["context"]["rollback_verified"] is True
    assert result["context"]["mutation_applied"] is False
    assert assignments_of(obj) == before


def test_slot_change_during_assignment_cannot_be_hidden_by_index_rollback(host):
    _, obj = host
    revision = revision_for(obj)
    before = assignments_of(obj)

    def replace_effective_material(face, value):
        face._material_index = value
        if value == 2:
            obj.material_slots[2].material = SimpleNamespace(name="Replacement", library=None)

    obj.data.polygons[0].on_write = replace_effective_material
    result = assign_face_materials(obj.name, [{"face_index": 0, "material_index": 2}], revision)
    assert result["success"] is False
    assert result["context"]["error_code"] == "face_material_assignment_failed"
    assert result["context"]["rollback_attempted"] is True
    assert result["context"]["rollback_verified"] is False
    assert result["context"]["mutation_applied"] is True
    assert assignments_of(obj) == before
    assert revision_for(obj) != revision


@pytest.mark.parametrize("unreadable", [False, True])
def test_failed_rollback_never_claims_that_no_mutation_happened(host, unreadable):
    _, obj = host
    revision = revision_for(obj)

    def reject_restore(face, value):
        if value == 0:
            if unreadable:
                face.read_error = True
            raise RuntimeError("Injected rollback failure")
        face._material_index = value

    def reject_assignment(face, value):
        if value == 2:
            raise RuntimeError("Injected assignment failure")
        face._material_index = value

    obj.data.polygons[0].on_write = reject_restore
    obj.data.polygons[1].on_write = reject_assignment
    result = assign_face_materials(
        obj.name, [{"face_index": 0, "material_index": 2}, {"face_index": 1, "material_index": 2}], revision
    )
    assert result["success"] is False
    context = result["context"]
    assert context["error_code"] == "face_material_assignment_failed"
    assert context["rollback_attempted"] is True
    assert context["rollback_verified"] is False
    if unreadable:
        assert context["mutation_applied"] is None or context["mutation_applied"] is True
    else:
        assert context["mutation_applied"] is True
    assert assignments_of(obj) == [2, 1, 0, 2]
    assert obj.data.polygons[2].writes == []
    assert obj.data.polygons[3].writes == []


def test_public_skill_scripts_delegate_the_same_bounded_contract(host):
    bpy, obj = host
    inspected = load_and_call(INSPECT_SCRIPT, bpy, object_name=obj.name, limit=1)
    assert inspected["success"] is True
    assigned = load_and_call(
        ASSIGN_SCRIPT,
        bpy,
        object_name=obj.name,
        assignments=[{"face_index": 0, "material_index": 1}],
        expected_revision=inspected["context"]["revision"],
    )
    assert assigned["success"] is True
    assert assigned["postcondition"]["verified"] is True


@pytest.fixture
def tool_contracts():
    tools = yaml.safe_load((SKILLS_ROOT / "blender-materials/tools.yaml").read_text(encoding="utf-8"))["tools"]
    return {tool["name"]: tool for tool in tools}


@pytest.mark.parametrize("name", ["inspect_face_materials", "assign_face_materials"])
def test_public_schema_declares_main_thread_bounds_and_revision_contract(tool_contracts, name):
    tool = tool_contracts[name]
    schema = tool["input_schema"]
    assert tool["affinity"] == "main"
    assert tool["enforce_thread_affinity"] is True
    assert tool["idempotent"] is True
    assert tool["read_only"] is (name == "inspect_face_materials")
    assert schema["additionalProperties"] is False
    assert schema["properties"]["expected_revision"]["pattern"] == REVISION_PATTERN
    jsonschema.Draft202012Validator.check_schema(schema)
    if name == "inspect_face_materials":
        assert "expected_revision" not in schema["required"]
        assert schema["properties"]["offset"]["minimum"] == 0
        assert schema["properties"]["offset"]["maximum"] == 100_000
        assert schema["properties"]["limit"]["minimum"] == 1
        assert schema["properties"]["limit"]["maximum"] == 256
    else:
        assert "expected_revision" in schema["required"]
        assignments = schema["properties"]["assignments"]
        assert assignments["minItems"] == 1
        assert assignments["maxItems"] == 4096
        assert assignments["items"]["additionalProperties"] is False
        assert set(assignments["items"]["required"]) == {"face_index", "material_index"}
        for field in ("face_index", "material_index"):
            assert assignments["items"]["properties"][field]["type"] == "integer"
            assert assignments["items"]["properties"][field]["minimum"] == 0


@pytest.mark.parametrize(
    ("name", "arguments"),
    [
        ("inspect_face_materials", {"offset": True}),
        ("inspect_face_materials", {"offset": 100_001}),
        ("inspect_face_materials", {"limit": 0}),
        ("inspect_face_materials", {"limit": 257}),
        ("assign_face_materials", {"assignments": []}),
        ("assign_face_materials", {"assignments": [{"face_index": True, "material_index": 0}]}),
        ("assign_face_materials", {"assignments": [{"face_index": 0, "material_index": False}]}),
        ("assign_face_materials", {"assignments": [{"face_index": -1, "material_index": 0}]}),
        ("assign_face_materials", {"assignments": [{"face_index": 100_000, "material_index": 0}]}),
        ("assign_face_materials", {"assignments": [{"face_index": 0, "material_index": -1}]}),
        ("assign_face_materials", {"assignments": [{"face_index": 0, "material_index": 1024}]}),
        ("assign_face_materials", {"assignments": [{"face_index": 0, "material_index": 0, "extra": 1}]}),
        ("assign_face_materials", {"assignments": [{"face_index": 0, "material_index": 0}] * 4097}),
        ("assign_face_materials", {"expected_revision": "invalid"}),
    ],
)
def test_schema_rejects_unbounded_and_malformed_inputs(tool_contracts, name, arguments):
    payload = {"object_name": "Panel"}
    if name == "assign_face_materials":
        payload.update(
            expected_revision="face-materials-v1:" + "a" * 64,
            assignments=[{"face_index": 0, "material_index": 1}],
        )
    payload.update(arguments)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(payload, tool_contracts[name]["input_schema"])


def test_output_schemas_accept_actual_success_and_failure_envelopes(host, tool_contracts):
    _, obj = host
    inspected = inspect_face_materials(obj.name)
    assigned = assign_face_materials(
        obj.name, [{"face_index": 0, "material_index": 2}], inspected["context"]["revision"]
    )
    rejected = assign_face_materials(obj.name, [], inspected["context"]["revision"])
    for name, result in (
        ("inspect_face_materials", inspected),
        ("assign_face_materials", assigned),
        ("assign_face_materials", rejected),
    ):
        jsonschema.validate(result, tool_contracts[name]["output_schema"])
