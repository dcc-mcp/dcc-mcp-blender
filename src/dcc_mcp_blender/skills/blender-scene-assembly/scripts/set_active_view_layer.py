"""Set the active view layer."""

from __future__ import annotations

from dcc_mcp_core.skill import skill_entry

from dcc_mcp_blender._scene_assembly_ops import set_active_view_layer


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`set_active_view_layer`."""
    return set_active_view_layer(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
