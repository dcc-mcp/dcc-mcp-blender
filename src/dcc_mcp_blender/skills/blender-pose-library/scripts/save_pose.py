"""Save the current pose of a Blender armature."""

from __future__ import annotations

from dcc_mcp_core.skill import skill_entry

from dcc_mcp_blender._pose_ops import save_pose


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`save_pose`."""
    return save_pose(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
