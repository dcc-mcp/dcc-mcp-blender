"""Delete a node from a Blender node tree."""

from __future__ import annotations

from dcc_mcp_core.skill import skill_entry

from dcc_mcp_blender._node_graph_ops import delete_node


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`delete_node`."""
    return delete_node(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
