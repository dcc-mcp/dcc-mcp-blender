"""Set validated rest-relative local pose bone channels."""

from __future__ import annotations

from dcc_mcp_core.skill import skill_entry

from dcc_mcp_blender._armature_pose_ops import set_pose_bone_transforms


@skill_entry
def main(**kwargs) -> dict:
    return set_pose_bone_transforms(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
