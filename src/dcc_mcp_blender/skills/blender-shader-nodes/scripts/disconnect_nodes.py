"""Disconnect Blender node links."""

from __future__ import annotations

from dcc_mcp_core.skill import skill_entry

from dcc_mcp_blender._node_graph_ops import disconnect_nodes


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`disconnect_nodes`."""
    return disconnect_nodes(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
