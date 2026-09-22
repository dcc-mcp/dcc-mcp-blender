"""Update Dynamic Paint canvas or brush settings."""

from __future__ import annotations

from dcc_mcp_core.skill import skill_entry

from dcc_mcp_blender._physics_ops import set_dynamic_paint_settings


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`set_dynamic_paint_settings`."""
    return set_dynamic_paint_settings(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
