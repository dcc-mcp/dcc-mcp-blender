"""Report render output configuration for a scene."""

from __future__ import annotations

from dcc_mcp_core.skill import skill_entry

from dcc_mcp_blender._render_ops import get_render_output


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`get_render_output`."""
    return get_render_output(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
