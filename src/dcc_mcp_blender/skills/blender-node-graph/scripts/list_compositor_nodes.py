"""List nodes in the compositor node tree."""

from __future__ import annotations

from dcc_mcp_core.skill import skill_entry

from dcc_mcp_blender._node_graph_ops import get_compositor_node_tree


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`get_compositor_node_tree`."""
    return get_compositor_node_tree(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
