"""Set the Blender object selection."""

from __future__ import annotations

from dcc_mcp_core.skill import skill_entry

from dcc_mcp_blender._scene_ops import set_selection


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`set_selection`."""
    return set_selection(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
