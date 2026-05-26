"""Get a Blender object's bounding box."""

from __future__ import annotations

from dcc_mcp_core.skill import skill_entry

from dcc_mcp_blender._scene_ops import get_bounding_box


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`get_bounding_box`."""
    return get_bounding_box(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
