"""Find Blender objects by name pattern."""

from __future__ import annotations

from dcc_mcp_core.skill import skill_entry

from dcc_mcp_blender._scene_ops import find_by_pattern


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`find_by_pattern`."""
    return find_by_pattern(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
