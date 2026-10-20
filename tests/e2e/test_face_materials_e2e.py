"""Native Blender acceptance; fixtures use bpy, the operations under test are typed.

Transport acceptance is separate: initialize/load_skill/tools/call must also be
exercised against the official bootstrap, not inferred from these direct calls.
"""

from __future__ import annotations

import json
import struct

import pytest

bpy = pytest.importorskip("bpy", reason="Native Blender required")
pytestmark = pytest.mark.e2e

from dcc_mcp_blender._face_material_ops import assign_face_materials, inspect_face_materials  # noqa: E402


def _fixture():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    mesh = bpy.data.meshes.new("FaceFixtureMesh")
    vertices = []
    faces = []
    for index in range(4):
        x = index * 3
        vertices.extend([(x, 0, 0), (x + 1, 0, 0), (x, 1, 0)])
        faces.append((index * 3, index * 3 + 1, index * 3 + 2))
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new("FaceFixture", mesh)
    bpy.context.collection.objects.link(obj)
    for name in ("FaceRed", "FaceBlue", "FaceGold"):
        material = bpy.data.materials.new(name)
        material.use_nodes = True
        mesh.materials.append(material)
    return obj


def _inspect(obj, **kwargs):
    result = inspect_face_materials(obj.name, **kwargs)
    assert result["success"], result
    return result["context"]


def _indices(obj):
    return [polygon.material_index for polygon in obj.data.polygons]


def _groups(obj):
    return {
        round(
            sum(obj.data.vertices[index].co.x for index in polygon.vertices) / len(polygon.vertices), 3
        ): obj.material_slots[polygon.material_index].material.name
        for polygon in obj.data.polygons
    }


def test_native_assignment_preserves_context_and_unrequested_polygons():
    obj = _fixture()
    bpy.ops.object.empty_add()
    active = bpy.context.active_object
    selected = list(bpy.context.selected_objects)
    slots = [slot.material for slot in obj.material_slots]
    revision = _inspect(obj)["revision"]
    assignments = [{"face_index": 1, "material_index": 1}, {"face_index": 3, "material_index": 2}]
    result = assign_face_materials(obj.name, assignments, revision)
    assert result["success"], result
    assert result["context"]["assignments"] == assignments
    assert result["context"]["changed_count"] == 2
    assert _indices(obj) == [0, 1, 0, 2]
    assert [slot.material for slot in obj.material_slots] == slots
    assert bpy.context.active_object == active
    assert list(bpy.context.selected_objects) == selected
    assert obj.mode == "OBJECT"
    repeated = assign_face_materials(obj.name, assignments, revision)
    assert repeated["success"], repeated
    assert repeated["context"]["changed_count"] == 0
    assert repeated["context"]["mutation_applied"] is False
    page = _inspect(obj, limit=2, expected_revision=revision)
    assert page["next_offset"] == 2
    page2 = _inspect(obj, offset=page["next_offset"], limit=2, expected_revision=revision)
    assert page2["next_offset"] is None
    assert [item["material_index"] for item in page["assignments"] + page2["assignments"]] == [0, 1, 0, 2]


@pytest.mark.parametrize(
    "bad",
    [
        [{"face_index": 0, "material_index": 1}, {"face_index": 4, "material_index": 1}],
        [{"face_index": 0, "material_index": 1}, {"face_index": 1, "material_index": 3}],
        [{"face_index": 0, "material_index": 1}, {"face_index": 0, "material_index": 2}],
        [{"face_index": True, "material_index": 1}],
        [{"face_index": 0, "material_index": False}],
        [{"face_index": -1, "material_index": 1}],
        [{"face_index": 0, "material_index": -1}],
        [],
        [{"face_index": 0, "material_index": 1}] * 4097,
    ],
)
def test_native_invalid_batches_do_not_partially_apply(bad):
    obj = _fixture()
    before = _indices(obj)
    result = assign_face_materials(obj.name, bad, _inspect(obj)["revision"])
    assert not result["success"], result
    assert result["context"]["mutation_applied"] is False
    assert _indices(obj) == before


def test_native_empty_slots_empty_mesh_missing_object_and_nonmesh():
    obj = _fixture()
    bpy.data.materials.remove(obj.material_slots[1].material)
    result = assign_face_materials(obj.name, [{"face_index": 0, "material_index": 1}], _inspect(obj)["revision"])
    assert result["context"]["error_code"] == "empty_material_slot"
    assert _indices(obj) == [0, 0, 0, 0]
    empty = bpy.data.objects.new("EmptyMesh", bpy.data.meshes.new("EmptyMeshData"))
    bpy.context.collection.objects.link(empty)
    assert _inspect(empty)["assignments"] == []
    result = assign_face_materials(empty.name, [{"face_index": 0, "material_index": 0}], _inspect(empty)["revision"])
    assert result["context"]["error_code"] == "empty_mesh"
    assert inspect_face_materials("Missing")["context"]["error_code"] == "object_not_found"
    bpy.ops.object.empty_add()
    assert inspect_face_materials(bpy.context.active_object.name)["context"]["error_code"] == "mesh_required"


def test_native_shared_editmode_and_stale_slots_rejected():
    obj = _fixture()
    revision = _inspect(obj)["revision"]
    other = bpy.data.objects.new("Shared", obj.data)
    bpy.context.collection.objects.link(other)
    result = assign_face_materials(obj.name, [{"face_index": 0, "material_index": 1}], revision)
    assert result["context"]["error_code"] == "shared_mesh_data"
    assert _indices(other) == [0, 0, 0, 0]
    bpy.data.objects.remove(other, do_unlink=True)
    obj.material_slots[1].material = obj.material_slots[2].material
    result = assign_face_materials(obj.name, [{"face_index": 0, "material_index": 1}], revision)
    assert result["context"]["error_code"] == "stale_face_material_revision"
    revision = _inspect(obj)["revision"]
    obj.data.vertices[0].co.x += 0.25
    obj.data.update()
    result = assign_face_materials(obj.name, [{"face_index": 0, "material_index": 1}], revision)
    assert result["context"]["error_code"] == "stale_face_material_revision"
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    try:
        result = inspect_face_materials(obj.name)
        assert result["context"]["error_code"] == "mesh_revision_mode_required"
        assert obj.mode == "EDIT"
    finally:
        bpy.ops.object.mode_set(mode="OBJECT")


def test_native_save_reopen_and_glb_groups_roundtrip(tmp_path):
    obj = _fixture()
    revision = _inspect(obj)["revision"]
    result = assign_face_materials(
        obj.name, [{"face_index": 1, "material_index": 1}, {"face_index": 3, "material_index": 2}], revision
    )
    assert result["success"], result
    expected_groups = _groups(obj)
    blend_path = str(tmp_path / "face-materials.blend")
    bpy.ops.wm.save_as_mainfile(filepath=blend_path)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.wm.open_mainfile(filepath=blend_path)
    obj = bpy.data.objects["FaceFixture"]
    reopened = _inspect(obj)
    assert [entry["material_index"] for entry in reopened["assignments"]] == [0, 1, 0, 2]
    assert _groups(obj) == expected_groups
    stale = assign_face_materials(obj.name, [{"face_index": 0, "material_index": 0}], revision)
    assert stale["context"]["error_code"] == "stale_face_material_revision"
    glb = tmp_path / "face-materials.glb"
    bpy.ops.export_scene.gltf(filepath=str(glb), export_format="GLB", export_animations=False)
    binary = glb.read_bytes()
    size, kind = struct.unpack_from("<II", binary, 12)
    assert kind == 0x4E4F534A
    document = json.loads(binary[20 : 20 + size])
    primitive_materials = {primitive["material"] for mesh in document["meshes"] for primitive in mesh["primitives"]}
    assert {document["materials"][index]["name"] for index in primitive_materials} == {
        "FaceRed",
        "FaceBlue",
        "FaceGold",
    }
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(glb))
    meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    assert len(meshes) == 1
    obj = meshes[0]
    imported = _inspect(obj)
    assert imported["face_count"] == 4
    assert _groups(obj) == expected_groups
    counts = {}
    for record in imported["assignments"]:
        name = imported["material_slots"][record["material_index"]]["material_name"]
        counts[name] = counts.get(name, 0) + 1
    assert counts == {"FaceRed": 2, "FaceBlue": 1, "FaceGold": 1}
