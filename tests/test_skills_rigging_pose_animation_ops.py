"""Unit tests for Blender rigging, pose-library, and expanded animation tools."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import yaml

from tests.conftest import load_and_call, make_mock_bpy

SKILLS_ROOT = Path(__file__).parent.parent / "src" / "dcc_mcp_blender" / "skills"
RIGGING_DIR = SKILLS_ROOT / "blender-rigging"
POSE_DIR = SKILLS_ROOT / "blender-pose-library"
ANIMATION_DIR = SKILLS_ROOT / "blender-animation"

RIGGING_TOOLS = {
    "create_armature",
    "create_bone",
    "mirror_bones",
    "add_constraint",
    "set_constraint_properties",
    "bind_mesh_to_armature",
    "add_shape_key",
    "set_driver",
    "retarget_animation",
}

POSE_TOOLS = {"list_poses", "save_pose", "load_pose"}
NEW_ANIMATION_TOOLS = {"get_keyframes", "delete_keyframes", "bake_animation"}


class FakeObjects(list):
    def get(self, name):
        return next((obj for obj in self if obj.name == name), None)


class FakeBone:
    def __init__(self, name):
        self.name = name
        self.head = [0.0, 0.0, 0.0]
        self.tail = [0.0, 0.0, 1.0]
        self.roll = 0.0
        self.parent = None


class FakeBones(list):
    def get(self, name):
        return next((bone for bone in self if bone.name == name), None)

    def new(self, name):
        bone = FakeBone(name)
        self.append(bone)
        return bone


class FakePoseBone:
    def __init__(self, name):
        self.name = name
        self.location = [0.0, 0.0, 0.0]
        self.rotation_mode = "XYZ"
        self.rotation_euler = [0.0, 0.0, 0.0]
        self.rotation_quaternion = [1.0, 0.0, 0.0, 0.0]
        self.scale = [1.0, 1.0, 1.0]
        self.matrix_basis = MagicMock()


class FakePoseBones(list):
    def get(self, name):
        return next((bone for bone in self if bone.name == name), None)


class FakeArmature(dict):
    def __init__(self, name="Rig"):
        super().__init__()
        self.name = name
        self.type = "ARMATURE"
        self.data = MagicMock()
        self.data.name = name
        self.data.edit_bones = FakeBones([FakeBone("root.L")])
        self.data.bones = self.data.edit_bones
        self.pose = MagicMock()
        self.pose.bones = FakePoseBones([FakePoseBone("root.L"), FakePoseBone("root.R")])
        self.constraints = FakeConstraints()
        self.modifiers = FakeModifiers()
        self.animation_data = None
        self._selected = False

    def select_set(self, state):
        self._selected = bool(state)

    def animation_data_create(self):
        self.animation_data = MagicMock()
        return self.animation_data


class FakeMeshObject:
    def __init__(self, name="Mesh"):
        self.name = name
        self.type = "MESH"
        self.constraints = FakeConstraints()
        self.modifiers = FakeModifiers()
        self.data = MagicMock()
        self.data.shape_keys = MagicMock()
        self.data.shape_keys.key_blocks = []
        self.keyframe_insert = MagicMock()
        self._selected = False

    def select_set(self, state):
        self._selected = bool(state)

    def shape_key_add(self, name, from_mix=False):
        key = MagicMock()
        key.name = name
        self.data.shape_keys.key_blocks.append(key)
        return key

    def driver_add(self, data_path):
        fcurve = FakeFcurve(data_path, 0, [])
        fcurve.driver = FakeDriver()
        return fcurve


class FakeConstraint:
    def __init__(self, type):
        self.type = type
        self.name = type.title()
        self.influence = 1.0
        self.target = None


class FakeConstraints(list):
    def get(self, name):
        return next((constraint for constraint in self if constraint.name == name), None)

    def new(self, type):
        constraint = FakeConstraint(type)
        self.append(constraint)
        return constraint


class FakeModifier:
    def __init__(self, name, type):
        self.name = name
        self.type = type
        self.object = None


class FakeModifiers(list):
    def new(self, name, type):
        modifier = FakeModifier(name, type)
        self.append(modifier)
        return modifier


class FakeDriverTarget:
    def __init__(self):
        self.id = None
        self.data_path = ""


class FakeDriverVariable:
    def __init__(self):
        self.name = "var"
        self.type = "SINGLE_PROP"
        self.targets = [FakeDriverTarget()]


class FakeDriverVariables(list):
    def new(self):
        variable = FakeDriverVariable()
        self.append(variable)
        return variable


class FakeDriver:
    def __init__(self):
        self.expression = ""
        self.variables = FakeDriverVariables()


class FakeKeyframe:
    def __init__(self, frame):
        self.co = [float(frame), 0.0]


class FakeKeyframes(list):
    def remove(self, point, fast=False):
        super().remove(point)


class FakeFcurve:
    def __init__(self, data_path, array_index, frames):
        self.data_path = data_path
        self.array_index = array_index
        self.keyframe_points = FakeKeyframes(FakeKeyframe(frame) for frame in frames)
        self.update = MagicMock()


class FakeAction:
    def __init__(self):
        self.name = "Action"
        self.fcurves = [FakeFcurve("location", 0, [1, 10]), FakeFcurve("scale", 0, [5])]

    def copy(self):
        return FakeAction()


def _bpy_with_objects(objects):
    bpy = make_mock_bpy()
    bpy.data.objects = FakeObjects(objects)
    return bpy


def test_rigging_pose_and_animation_tools_yaml_declares_modern_contracts():
    for skill_dir, expected in (
        (RIGGING_DIR, RIGGING_TOOLS),
        (POSE_DIR, POSE_TOOLS),
    ):
        doc = yaml.safe_load((skill_dir / "tools.yaml").read_text(encoding="utf-8"))
        tools = {tool["name"]: tool for tool in doc["tools"]}
        assert set(tools) == expected
        for name, tool in tools.items():
            assert (skill_dir / tool["source_file"]).exists(), name
            assert tool["execution"] == "sync"
            assert tool["affinity"] == "main"
            assert isinstance(tool["timeout_hint_secs"], int)
            assert tool["input_schema"]["type"] == "object"
            assert tool["output_schema"]["properties"]["success"]["type"] == "boolean"
            assert "annotations" in tool

    animation = yaml.safe_load((ANIMATION_DIR / "tools.yaml").read_text(encoding="utf-8"))
    animation_tools = {tool["name"]: tool for tool in animation["tools"]}
    assert NEW_ANIMATION_TOOLS <= set(animation_tools)
    for name in NEW_ANIMATION_TOOLS:
        tool = animation_tools[name]
        assert (ANIMATION_DIR / tool["source_file"]).exists(), name
        assert tool["input_schema"]["type"] == "object"
        assert "annotations" in tool


def test_create_armature_create_bone_and_mirror_bones():
    armature = FakeArmature("Rig")
    bpy = _bpy_with_objects([armature])
    bpy.context.active_object = armature

    created = load_and_call("blender-rigging/scripts/create_armature.py", bpy, name="AgentRig")
    assert created["success"] is True
    assert armature.name == "AgentRig"

    bone = load_and_call(
        "blender-rigging/scripts/create_bone.py",
        bpy,
        armature_name="AgentRig",
        bone_name="spine",
        head=[0, 0, 0],
        tail=[0, 0, 2],
        parent="root.L",
    )
    assert bone["success"] is True
    assert armature.data.edit_bones.get("spine").parent.name == "root.L"

    mirrored = load_and_call("blender-rigging/scripts/mirror_bones.py", bpy, armature_name="AgentRig")
    assert mirrored["success"] is True
    assert "root.R" in mirrored["context"]["created_bones"] or "root.R" in mirrored["context"]["skipped_bones"]

    invalid = load_and_call(
        "blender-rigging/scripts/create_bone.py",
        bpy,
        armature_name="AgentRig",
        bone_name="bad",
        head=[0, 0, 0],
        tail=[0, 0, 0],
    )
    assert invalid["success"] is False


def test_constraints_binding_shape_key_driver_and_error_paths():
    mesh = FakeMeshObject("Mesh")
    target = FakeMeshObject("Target")
    armature = FakeArmature("Rig")
    bpy = _bpy_with_objects([mesh, target, armature])

    constraint = load_and_call(
        "blender-rigging/scripts/add_constraint.py",
        bpy,
        object_name="Mesh",
        constraint_type="copy_location",
        target="Target",
    )
    assert constraint["success"] is True
    assert mesh.constraints[0].target is target

    updated = load_and_call(
        "blender-rigging/scripts/set_constraint_properties.py",
        bpy,
        object_name="Mesh",
        constraint_name=mesh.constraints[0].name,
        properties={"influence": 0.5, "missing_prop": True},
    )
    assert updated["success"] is True
    assert updated["context"]["applied"] == {"influence": 0.5}
    assert updated["context"]["ignored"] == ["missing_prop"]

    bound = load_and_call(
        "blender-rigging/scripts/bind_mesh_to_armature.py",
        bpy,
        mesh_name="Mesh",
        armature_name="Rig",
    )
    assert bound["success"] is True
    assert mesh.modifiers[0].object is armature

    shape_key = load_and_call("blender-rigging/scripts/add_shape_key.py", bpy, object_name="Mesh", name="Smile")
    assert shape_key["success"] is True
    assert mesh.data.shape_keys.key_blocks[0].name == "Smile"

    driver = load_and_call(
        "blender-rigging/scripts/set_driver.py",
        bpy,
        object_name="Mesh",
        data_path="location",
        expression="frame / 10",
    )
    assert driver["success"] is True

    missing_constraint = load_and_call(
        "blender-rigging/scripts/set_constraint_properties.py",
        bpy,
        object_name="Mesh",
        constraint_name="Ghost",
        properties={"influence": 1},
    )
    assert missing_constraint["success"] is False

    non_armature = load_and_call(
        "blender-rigging/scripts/bind_mesh_to_armature.py",
        bpy,
        mesh_name="Mesh",
        armature_name="Target",
    )
    assert non_armature["success"] is False


def test_pose_library_save_list_load_and_missing_pose():
    armature = FakeArmature("Rig")
    bpy = _bpy_with_objects([armature])
    armature.pose.bones.get("root.L").location = [1.0, 0.0, 0.0]

    saved = load_and_call("blender-pose-library/scripts/save_pose.py", bpy, armature_name="Rig", pose_name="Reach")
    assert saved["success"] is True
    assert saved["context"]["bone_count"] == 2

    listed = load_and_call("blender-pose-library/scripts/list_poses.py", bpy, armature_name="Rig")
    assert listed["success"] is True
    assert listed["context"]["poses"][0]["pose_name"] == "Reach"

    armature.pose.bones.get("root.L").location = [0.0, 0.0, 0.0]
    loaded = load_and_call("blender-pose-library/scripts/load_pose.py", bpy, armature_name="Rig", pose_name="Reach")
    assert loaded["success"] is True
    assert armature.pose.bones.get("root.L").location == [1.0, 0.0, 0.0]

    missing = load_and_call("blender-pose-library/scripts/load_pose.py", bpy, armature_name="Rig", pose_name="Missing")
    assert missing["success"] is False


def test_retarget_animation_copies_pose_and_action():
    source = FakeArmature("SourceRig")
    target = FakeArmature("TargetRig")
    source.animation_data = MagicMock()
    source.animation_data.action = FakeAction()
    source.pose.bones.get("root.L").location = [3.0, 0.0, 0.0]
    bpy = _bpy_with_objects([source, target])

    result = load_and_call(
        "blender-rigging/scripts/retarget_animation.py",
        bpy,
        source_armature="SourceRig",
        target_armature="TargetRig",
        mapping={"root.L": "root.R"},
    )
    assert result["success"] is True
    assert target.pose.bones.get("root.R").location == [3.0, 0.0, 0.0]
    assert target.animation_data.action is not None


def test_get_delete_and_bake_animation_keyframes():
    obj = FakeMeshObject("Cube")
    obj.animation_data = MagicMock()
    obj.animation_data.action = FakeAction()
    bpy = _bpy_with_objects([obj])

    keys = load_and_call("blender-animation/scripts/get_keyframes.py", bpy, object_name="Cube", data_path="location")
    assert keys["success"] is True
    assert keys["context"]["keyframe_count"] == 2

    deleted = load_and_call(
        "blender-animation/scripts/delete_keyframes.py",
        bpy,
        object_name="Cube",
        frame_range=[1, 1],
        data_path="location",
    )
    assert deleted["success"] is True
    assert deleted["context"]["deleted_count"] == 1

    invalid = load_and_call(
        "blender-animation/scripts/delete_keyframes.py",
        bpy,
        object_name="Cube",
        frame_range=[10, 1],
    )
    assert invalid["success"] is False

    baked = load_and_call(
        "blender-animation/scripts/bake_animation.py",
        bpy,
        object_names=["Cube"],
        frame_start=1,
        frame_end=3,
        step=2,
        data_paths=["location"],
    )
    assert baked["success"] is True
    assert baked["context"]["inserted_count"] == 2
    assert obj.keyframe_insert.call_count == 2
