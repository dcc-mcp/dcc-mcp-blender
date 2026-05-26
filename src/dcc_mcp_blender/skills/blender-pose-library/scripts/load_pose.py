"""Load a saved pose onto a Blender armature."""

from __future__ import annotations

from dcc_mcp_core.skill import skill_entry

from dcc_mcp_blender._pose_ops import load_pose


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`load_pose`."""
    return load_pose(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
