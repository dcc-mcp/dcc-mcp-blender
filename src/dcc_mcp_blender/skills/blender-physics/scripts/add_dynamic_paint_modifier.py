"""Add a Dynamic Paint canvas or brush modifier."""

from __future__ import annotations

from dcc_mcp_core.skill import skill_entry

from dcc_mcp_blender._physics_ops import add_dynamic_paint_modifier


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`add_dynamic_paint_modifier`."""
    return add_dynamic_paint_modifier(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
