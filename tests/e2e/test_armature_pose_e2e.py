"""Native pose capability gates; run only in a disposable Blender process."""

from __future__ import annotations

import math

import pytest

bpy = pytest.importorskip("bpy", reason="requires a native Blender interpreter")
pytestmark = pytest.mark.e2e

from tests.e2e.conftest import load_skill  # noqa: E402


@pytest.fixture
def rig():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    data = bpy.data.armatures.new("TypedRigData")
    obj = bpy.data.objects.new("TypedRig", data)
    bpy.context.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    root = data.edit_bones.new("root")
    root.head, root.tail = (0, 0, 0), (0, 1, 0)
    tip = data.edit_bones.new("tip")
    tip.head, tip.tail = (0, 1, 0), (0, 2, 0)
    tip.parent, tip.use_connect = root, True
    bpy.ops.object.mode_set(mode="OBJECT")
    return obj


def test_native_bulk_pose_inspection_and_reopen(rig, tmp_path):
    update = load_skill("blender-rigging", "set_pose_bone_transforms").set_pose_bone_transforms
    inspect = load_skill("blender-rigging", "inspect_armature").inspect_armature
    before_frame = bpy.context.scene.frame_current
    before_selection = [obj.name for obj in bpy.context.selected_objects]
    result = update(
        armature_name=rig.name,
        transforms=[
            {"bone_name": "root", "rotation_euler": [0, 0, 0.3]},
            {"bone_name": "tip", "rotation_quaternion": [math.cos(0.2), math.sin(0.2), 0, 0]},
        ],
    )
    assert result["success"] is True
    assert result["context"]["transforms"][0]["readback"]["rotation_euler"][2] == pytest.approx(0.3)
    assert bpy.context.scene.frame_current == before_frame
    assert [obj.name for obj in bpy.context.selected_objects] == before_selection
    assert rig.mode == "OBJECT" and rig.animation_data is None
    data = inspect(armature_name=rig.name)["context"]
    assert data["bone_count"] == 2
    assert data["bones"][1]["parent"] == "root" and data["bones"][1]["connected"]
    assert data["bones"][0]["pose"]["matrix_armature_space"] != data["bones"][0]["rest"]["matrix_armature_space"]
    path = str(tmp_path / "typed-pose.blend")
    bpy.ops.wm.save_as_mainfile(filepath=path)
    bpy.ops.wm.open_mainfile(filepath=path, load_ui=False)
    reopened = inspect(armature_name="TypedRig")
    assert reopened["success"] is True
    assert reopened["context"]["bones"][0]["pose"]["rotation_euler"][2] == pytest.approx(0.3)


def test_native_invalid_later_bone_does_not_change_first(rig):
    update = load_skill("blender-rigging", "set_pose_bone_transforms").set_pose_bone_transforms
    before = tuple(rig.pose.bones["root"].location)
    result = update(
        armature_name=rig.name,
        transforms=[
            {"bone_name": "root", "location": [1, 0, 0]},
            {"bone_name": "missing", "location": [0, 0, 0]},
        ],
    )
    assert result["success"] is False
    assert tuple(rig.pose.bones["root"].location) == before


def test_native_weight_summary_and_constraint_evaluation(rig):
    mesh_data = bpy.data.meshes.new("SkinData")
    mesh_data.from_pydata([(0, 0, 0), (0, 1, 0), (1, 0, 0)], [], [(0, 1, 2)])
    mesh = bpy.data.objects.new("Skin", mesh_data)
    bpy.context.collection.objects.link(mesh)
    mesh.modifiers.new("Skin", "ARMATURE").object = rig
    mesh.vertex_groups.new(name="root").add([0, 1, 2], 1.0, "REPLACE")
    target = bpy.data.objects.new("Target", None)
    bpy.context.collection.objects.link(target)
    target.location = (2, 0, 0)
    constraint = rig.pose.bones["root"].constraints.new("COPY_LOCATION")
    constraint.target = target
    inspect = load_skill("blender-rigging", "inspect_armature").inspect_armature
    result = inspect(armature_name=rig.name, mesh_names=[mesh.name], max_vertices_per_mesh=2)
    assert result["success"] is True
    data = result["context"]
    assert data["bones"][0]["constraints"]["items"][0]["target"] == "Target"
    assert data["bones"][0]["pose"]["matrix_armature_space"][0][3] == pytest.approx(2)
    weights = data["mesh_weight_summaries"][0]
    assert weights["scanned_vertex_count"] == 2 and weights["scan_complete"] is False
    assert weights["weight_sum_min"] == pytest.approx(1)
