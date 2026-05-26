"""Set a Blender node input socket value."""

from __future__ import annotations

from dcc_mcp_core.skill import skill_entry

from dcc_mcp_blender._node_graph_ops import set_node_input


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`set_node_input`."""
    return set_node_input(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
