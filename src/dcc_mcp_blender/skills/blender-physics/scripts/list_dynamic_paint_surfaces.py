"""List Dynamic Paint canvas surfaces."""

from __future__ import annotations

from dcc_mcp_core.skill import skill_entry

from dcc_mcp_blender._physics_ops import list_dynamic_paint_surfaces


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`list_dynamic_paint_surfaces`."""
    return list_dynamic_paint_surfaces(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
