"""Toggle compositor nodes for a scene."""

from __future__ import annotations

from dcc_mcp_core.skill import skill_entry

from dcc_mcp_blender._compositor_ops import set_compositor_enabled


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`set_compositor_enabled`."""
    return set_compositor_enabled(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
