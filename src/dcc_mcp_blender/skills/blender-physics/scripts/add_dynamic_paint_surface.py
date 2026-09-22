"""Add a surface to a Dynamic Paint canvas."""

from __future__ import annotations

from dcc_mcp_core.skill import skill_entry

from dcc_mcp_blender._physics_ops import add_dynamic_paint_surface


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`add_dynamic_paint_surface`."""
    return add_dynamic_paint_surface(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
