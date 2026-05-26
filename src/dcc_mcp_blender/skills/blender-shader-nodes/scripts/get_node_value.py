"""Read Blender node socket values."""

from __future__ import annotations

from dcc_mcp_core.skill import skill_entry

from dcc_mcp_blender._node_graph_ops import get_node_value


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`get_node_value`."""
    return get_node_value(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
