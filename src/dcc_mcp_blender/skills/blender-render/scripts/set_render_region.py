"""Enable and configure border rendering."""

from __future__ import annotations

from dcc_mcp_core.skill import skill_entry

from dcc_mcp_blender._render_ops import set_render_region


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`set_render_region`."""
    return set_render_region(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
