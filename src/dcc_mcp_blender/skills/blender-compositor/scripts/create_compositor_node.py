"""Create a compositor node."""

from __future__ import annotations

from dcc_mcp_core.skill import skill_entry

from dcc_mcp_blender._compositor_ops import create_compositor_node


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`create_compositor_node`."""
    return create_compositor_node(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
