"""Connect two compositor node sockets."""

from __future__ import annotations

from dcc_mcp_core.skill import skill_entry

from dcc_mcp_blender._compositor_ops import connect_compositor_nodes


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`connect_compositor_nodes`."""
    return connect_compositor_nodes(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
