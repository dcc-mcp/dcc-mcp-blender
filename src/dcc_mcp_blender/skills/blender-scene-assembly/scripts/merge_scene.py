"""Merge data from an external .blend file into the current scene."""

from __future__ import annotations

from dcc_mcp_core.skill import skill_entry

from dcc_mcp_blender._scene_assembly_ops import merge_scene


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`merge_scene`."""
    return merge_scene(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
