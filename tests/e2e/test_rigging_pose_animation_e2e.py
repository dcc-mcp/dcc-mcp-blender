"""E2E tests for Blender rigging, pose-library, and expanded animation skills.

Requires a real Blender Python interpreter.
"""

from __future__ import annotations

import pytest

bpy = pytest.importorskip("bpy", reason="bpy not available - run inside Blender Python interpreter")

pytestmark = pytest.mark.e2e

from tests.e2e.conftest import load_skill  # noqa: E402


def _new_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)


class TestRiggingPoseAnimationE2E:
    def setup_method(self):
        _new_scene()

    def test_armature_pose_and_keyframe_workflow(self):
        create_armature_mod = load_skill("blender-rigging", "create_armature")
        armature = create_armature_mod.create_armature(name="AgentRig", location=[0, 0, 0])
        assert armature["success"] is True

        create_bone_mod = load_skill("blender-rigging", "create_bone")
        bone = create_bone_mod.create_bone(
            armature_name="AgentRig",
            bone_name="spine",
            head=[0, 0, 0],
            tail=[0, 0, 2],
        )
        assert bone["success"] is True

        pose_bone = bpy.data.objects["AgentRig"].pose.bones["spine"]
        pose_bone.location = [0.25, 0.0, 0.0]

        save_pose_mod = load_skill("blender-pose-library", "save_pose")
        saved = save_pose_mod.save_pose(armature_name="AgentRig", pose_name="Reach")
        assert saved["success"] is True

        pose_bone.location = [0.0, 0.0, 0.0]
        load_pose_mod = load_skill("blender-pose-library", "load_pose")
        loaded = load_pose_mod.load_pose(armature_name="AgentRig", pose_name="Reach")
        assert loaded["success"] is True
        assert list(pose_bone.location) == [0.25, 0.0, 0.0]

        bake_mod = load_skill("blender-animation", "bake_animation")
        baked = bake_mod.bake_animation(
            object_names=["AgentRig"],
            frame_start=1,
            frame_end=3,
            step=2,
            data_paths=["location"],
        )
        assert baked["success"] is True
        assert baked["context"]["inserted_count"] == 2

        get_keys_mod = load_skill("blender-animation", "get_keyframes")
        keys = get_keys_mod.get_keyframes(object_name="AgentRig", data_path="location")
        assert keys["success"] is True
        assert keys["context"]["keyframe_count"] == 6

        delete_keys_mod = load_skill("blender-animation", "delete_keyframes")
        deleted = delete_keys_mod.delete_keyframes(object_name="AgentRig", frame_range=[1, 1], data_path="location")
        assert deleted["success"] is True
        assert deleted["context"]["deleted_count"] == 3
