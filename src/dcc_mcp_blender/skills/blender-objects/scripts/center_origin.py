"""Center or move a Blender object's origin."""

from __future__ import annotations

from dcc_mcp_core.skill import skill_entry

from dcc_mcp_blender._scene_ops import center_origin


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`center_origin`."""
    return center_origin(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
