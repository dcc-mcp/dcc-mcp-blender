"""Inspect bounded armature rest, pose, constraints, and skin summaries."""

from __future__ import annotations

from dcc_mcp_core.skill import skill_entry

from dcc_mcp_blender._armature_pose_ops import inspect_armature


@skill_entry
def main(**kwargs) -> dict:
    return inspect_armature(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
