"""List all node graphs (material, geometry, compositor) in the scene."""

from __future__ import annotations

from dcc_mcp_core.skill import skill_entry

from dcc_mcp_blender._node_graph_ops import list_all_node_graphs


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`list_all_node_graphs`."""
    return list_all_node_graphs(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
