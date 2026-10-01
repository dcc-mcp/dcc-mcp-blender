"""Contract tests for pose batches and bounded reads; these use a fake host."""

from __future__ import annotations

import copy
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import jsonschema
import pytest
import yaml

from dcc_mcp_blender import _armature_pose_ops as ops
from tests.conftest import load_and_call

IDENTITY = [[float(row == column) for column in range(4)] for row in range(4)]
SKILL = Path(__file__).resolve().parents[1] / "src/dcc_mcp_blender/skills/blender-rigging"


class NamedCollection(list):
    def get(self, name):
        return next((item for item in self if item.name == name), None)

    def __getitem__(self, index):
        return self.get(index) if isinstance(index, str) else super().__getitem__(index)


class PoseBone:
    def __init__(self, name):
        self.name = name
        self.location = [0.0, 0.0, 0.0]
        self.rotation_euler = [0.0, 0.0, 0.0]
        self.rotation_quaternion = [1.0, 0.0, 0.0, 0.0]
        self.rotation_axis_angle = [0.0, 0.0, 1.0, 0.0]
        self.rotation_mode = "XYZ"
        self.scale = [1.0, 1.0, 1.0]
        self.matrix_basis = copy.deepcopy(IDENTITY)
        self.matrix = copy.deepcopy(IDENTITY)
        self.constraints = NamedCollection()
        self.is_property_readonly = lambda field: False
        self.fail_next_scale = False
        self.fail_all_scales = False

    def __setattr__(self, name, value):
        if name == "scale" and getattr(self, "fail_next_scale", False):
            object.__setattr__(self, "fail_next_scale", False)
            raise RuntimeError("simulated native setter failure")
        if name == "scale" and getattr(self, "fail_all_scales", False):
            raise RuntimeError("simulated persistent setter failure")
        object.__setattr__(self, name, value)


@pytest.fixture
def rig(monkeypatch):
    bones = NamedCollection([PoseBone("root"), PoseBone("tip")])
    rest = NamedCollection(
        [
            SimpleNamespace(
                name=bone.name,
                parent=None,
                use_connect=False,
                use_deform=True,
                head_local=[0.0, 0.0, 0.0],
                tail_local=[0.0, 1.0, 0.0],
                matrix_local=copy.deepcopy(IDENTITY),
                length=1.0,
            )
            for bone in bones
        ]
    )
    rest["tip"].parent = rest["root"]
    armature = SimpleNamespace(
        name="Rig",
        type="ARMATURE",
        mode="OBJECT",
        data=SimpleNamespace(bones=rest),
        pose=SimpleNamespace(bones=bones),
        matrix_world=copy.deepcopy(IDENTITY),
    )
    armature.evaluated_get = lambda depsgraph: armature
    bpy = SimpleNamespace(
        data=SimpleNamespace(objects=NamedCollection([armature])),
        context=SimpleNamespace(
            scene=SimpleNamespace(frame_current=12),
            view_layer=SimpleNamespace(update=MagicMock()),
            evaluated_depsgraph_get=lambda: object(),
        ),
        ops=MagicMock(),
    )
    monkeypatch.setitem(sys.modules, "bpy", bpy)
    return armature, bpy


def snapshot(armature):
    return [ops._pose_channels(bone) for bone in armature.pose.bones]


@pytest.mark.parametrize(
    "invalid",
    [
        {"bone_name": "missing", "location": [0, 0, 0]},
        {"bone_name": "tip", "location": [float("nan"), 0, 0]},
        {"bone_name": "tip", "location": [float("inf"), 0, 0]},
        {"bone_name": "tip", "location": [True, 0, 0]},
        {"bone_name": "tip", "location": ["1", 0, 0]},
        {"bone_name": "tip", "location": [1e7, 0, 0]},
        {"bone_name": "tip", "location": [1, 2]},
        {"bone_name": "tip", "scale": [1, 0, 1]},
        {"bone_name": "tip", "rotation_quaternion": [0, 0, 0, 0]},
        {"bone_name": "tip", "rotation_quaternion": [2, 0, 0, 0]},
        {"bone_name": "tip", "rotation_quaternion": [1, 0, 0, 0], "rotation_mode": "XYZ"},
        {"bone_name": "tip", "rotation_euler": [0, 0, 0], "rotation_mode": "AXIS_ANGLE"},
        {"bone_name": "tip", "rotation_euler": [0, 0, 0], "rotation_mode": []},
        {"bone_name": "tip", "rotation_euler": [0, 0, 0], "rotation_quaternion": [1, 0, 0, 0]},
        {"bone_name": "tip", "rotation_mode": "XYZ"},
        {"bone_name": "tip", "location": [0, 0, 0], "matrix": IDENTITY},
        {"bone_name": "root", "location": [2, 0, 0]},
    ],
)
def test_entire_batch_is_validated_before_first_write(rig, invalid):
    armature, bpy = rig
    before = snapshot(armature)
    result = ops.set_pose_bone_transforms("Rig", [{"bone_name": "root", "location": [1, 0, 0]}, invalid])
    assert result["success"] is False
    assert snapshot(armature) == before
    bpy.context.view_layer.update.assert_not_called()
    assert bpy.ops.mock_calls == []


def test_bulk_updates_return_actual_channels_and_evaluated_matrix_without_editor_ops(rig):
    armature, bpy = rig
    armature.pose.bones["root"].matrix[0][3] = 4.0  # A constraint may change the evaluated result.
    result = load_and_call(
        "blender-rigging/scripts/set_pose_bone_transforms.py",
        bpy,
        armature_name="Rig",
        transforms=[
            {"bone_name": "root", "rotation_quaternion": [0.5, 0.5, 0.5, 0.5], "location": [0.1, 0, 0]},
            {"bone_name": "tip", "rotation_euler": [0, 0.2, 0], "rotation_mode": "ZYX", "scale": [-1, 2, 1]},
        ],
    )
    assert result["success"] is True
    data = result["context"]
    assert data["frame"] == 12 and data["quaternion_order"] == "wxyz"
    assert data["transforms"][0]["readback"]["matrix_armature_space"][0][3] == 4
    assert data["transforms"][0]["readback"]["rotation_mode"] == "QUATERNION"
    assert armature.pose.bones["tip"].rotation_mode == "ZYX"
    assert armature.pose.bones["tip"].location == [0, 0, 0]
    assert bpy.ops.mock_calls == []


def test_readonly_channel_rejected_before_other_bone_is_changed(rig):
    armature, _ = rig
    armature.pose.bones["tip"].is_property_readonly = lambda field: field == "location"
    before = snapshot(armature)
    result = ops.set_pose_bone_transforms(
        "Rig",
        [
            {"bone_name": "root", "location": [1, 0, 0]},
            {"bone_name": "tip", "location": [2, 0, 0]},
        ],
    )
    assert result["success"] is False and snapshot(armature) == before


def test_native_write_failure_restores_every_channel(rig):
    armature, _ = rig
    before = snapshot(armature)
    armature.pose.bones["tip"].fail_next_scale = True
    result = ops.set_pose_bone_transforms(
        "Rig",
        [
            {"bone_name": "root", "rotation_quaternion": [0, 1, 0, 0], "location": [1, 0, 0]},
            {"bone_name": "tip", "scale": [2, 2, 2]},
        ],
    )
    assert result["success"] is False and result["context"]["rolled_back"] is True
    assert snapshot(armature) == before


def test_rollback_failure_is_reported_honestly(rig):
    armature, _ = rig
    armature.pose.bones["tip"].fail_all_scales = True
    result = ops.set_pose_bone_transforms("Rig", [{"bone_name": "tip", "scale": [2, 2, 2]}])
    assert result["success"] is False and result["context"]["rolled_back"] is False
    assert result["context"]["rollback_errors"]


def test_driver_overwrite_fails_readback_and_restores_original(rig):
    armature, bpy = rig
    before = snapshot(armature)
    bone = armature.pose.bones["root"]
    bpy.context.view_layer.update.side_effect = lambda: setattr(bone, "location", [0, 0, 0])
    result = ops.set_pose_bone_transforms("Rig", [{"bone_name": "root", "location": [1, 0, 0]}])
    assert result["success"] is False and result["context"]["rolled_back"] is True
    assert snapshot(armature) == before


def test_small_driver_overwrite_cannot_hide_inside_a_tolerance(rig):
    armature, bpy = rig
    bone = armature.pose.bones["root"]
    before = snapshot(armature)

    def overwrite_requested_channel():
        if bone.location == [1, 0, 0]:
            bone.location = [1.00000001, 0, 0]

    bpy.context.view_layer.update.side_effect = overwrite_requested_channel
    result = ops.set_pose_bone_transforms("Rig", [{"bone_name": "root", "location": [1, 0, 0]}])
    assert result["success"] is False and result["context"]["rolled_back"] is True
    assert snapshot(armature) == before


def test_inspection_is_bounded_and_preserves_native_hierarchy(rig):
    armature, bpy = rig
    before = snapshot(armature)
    armature.pose.bones["tip"].constraints.extend(
        [
            SimpleNamespace(
                name=f"Copy{index}",
                type="COPY_ROTATION",
                influence=0.5,
                mute=False,
                target=SimpleNamespace(name="Target"),
                subtarget="root",
                owner_space="LOCAL",
                target_space="WORLD",
            )
            for index in range(3)
        ]
    )
    result = load_and_call(
        "blender-rigging/scripts/inspect_armature.py",
        bpy,
        armature_name="Rig",
        bone_names=["tip"],
        max_constraints_per_bone=1,
    )
    assert result["success"] is True
    data = result["context"]
    assert data["bone_count"] == 2 and data["returned_bone_count"] == 1 and data["truncated"]
    assert data["bones"][0]["parent"] == "root"
    assert data["bones"][0]["constraints"]["total_count"] == 3
    assert data["bones"][0]["constraints"]["truncated"]
    assert len(data["bones"][0]["constraints"]["items"]) == 1
    assert snapshot(armature) == before and bpy.ops.mock_calls == []


def test_weight_summary_marks_sample_coverage_and_uses_all_deform_bones(rig):
    armature, bpy = rig

    def memberships(*pairs):
        return [SimpleNamespace(group=group, weight=weight) for group, weight in pairs]

    mesh = SimpleNamespace(
        name="Body",
        type="MESH",
        mode="OBJECT",
        modifiers=[SimpleNamespace(type="ARMATURE", object=armature)],
        vertex_groups=[
            SimpleNamespace(index=0, name="root"),
            SimpleNamespace(index=1, name="tip"),
            SimpleNamespace(index=2, name="unrelated"),
        ],
        data=SimpleNamespace(
            vertices=[
                SimpleNamespace(groups=memberships((0, 0.25), (1, 0.75), (2, 1))),
                SimpleNamespace(groups=memberships((0, -0.1))),
                SimpleNamespace(groups=memberships((1, 1))),
            ]
        ),
    )
    bpy.data.objects.append(mesh)
    result = ops.inspect_armature("Rig", max_bones=1, mesh_names=["Body"], max_vertices_per_mesh=2)
    assert result["success"] is True
    weights = result["context"]["mesh_weight_summaries"][0]
    assert weights["scan_complete"] is False and weights["scanned_vertex_count"] == 2
    assert weights["matched_bone_group_count"] == 2 and weights["positive_assignment_count"] == 2
    assert weights["invalid_assignment_count"] == 1 and weights["maximum_influences"] == 2
    assert weights["weight_sum_min"] == 0 and weights["weight_sum_max"] == 1
    mesh.modifiers.clear()
    assert ops.inspect_armature("Rig", mesh_names=["Body"])["success"] is False


@pytest.mark.parametrize(
    "kwargs",
    [
        {"max_bones": 0},
        {"max_bones": True},
        {"max_bones": 1025},
        {"max_constraints_per_bone": 129},
        {"max_vertices_per_mesh": 100001},
        {"bone_names": ["missing"]},
        {"bone_names": ["root", "root"]},
        {"mesh_names": ["missing"]},
        {"include_constraints": "yes"},
    ],
)
def test_inspection_rejects_invalid_bounds_or_identity(rig, kwargs):
    _, bpy = rig
    assert ops.inspect_armature("Rig", **kwargs)["success"] is False
    bpy.context.view_layer.update.assert_not_called()


def test_edit_mode_is_rejected_and_empty_rig_is_inspectable(rig):
    armature, _ = rig
    armature.mode = "EDIT"
    assert ops.inspect_armature("Rig")["success"] is False
    assert ops.set_pose_bone_transforms("Rig", [{"bone_name": "root", "location": [1, 0, 0]}])["success"] is False
    armature.mode = "OBJECT"
    armature.data.bones.clear()
    armature.pose.bones.clear()
    assert ops.inspect_armature("Rig")["context"]["bone_count"] == 0


def test_published_examples_and_actual_envelopes_match_schemas(rig):
    _, bpy = rig
    manifest = yaml.safe_load((SKILL / "tools.yaml").read_text(encoding="utf-8"))
    tools = {tool["name"]: tool for tool in manifest["tools"]}
    for name, kwargs in [
        ("inspect_armature", {"armature_name": "Rig"}),
        (
            "set_pose_bone_transforms",
            {"armature_name": "Rig", "transforms": [{"bone_name": "tip", "location": [1, 0, 0]}]},
        ),
    ]:
        tool = tools[name]
        jsonschema.Draft7Validator.check_schema(tool["input_schema"])
        jsonschema.Draft7Validator.check_schema(tool["output_schema"])
        for example in tool["call_examples"]:
            jsonschema.validate(example["arguments"], tool["input_schema"])
        result = load_and_call(f"blender-rigging/scripts/{name}.py", bpy, **kwargs)
        assert result["success"] is True
        jsonschema.validate(result, tool["output_schema"])
    assert tools["inspect_armature"]["annotations"]["read_only_hint"] is True
    assert tools["set_pose_bone_transforms"]["annotations"]["destructive_hint"] is True
