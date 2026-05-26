"""Parent or unparent a Blender object."""

from __future__ import annotations

from dcc_mcp_core.skill import skill_entry

from dcc_mcp_blender._scene_ops import parent_object


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`parent_object`."""
    return parent_object(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
