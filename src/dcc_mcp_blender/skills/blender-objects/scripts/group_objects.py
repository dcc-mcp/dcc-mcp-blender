"""Group Blender objects into a collection."""

from __future__ import annotations

from dcc_mcp_core.skill import skill_entry

from dcc_mcp_blender._scene_ops import group_objects


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`group_objects`."""
    return group_objects(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
