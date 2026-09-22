"""List supported compositor node types."""

from __future__ import annotations

from dcc_mcp_core.skill import skill_entry

from dcc_mcp_blender._compositor_ops import list_compositor_node_types


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`list_compositor_node_types`."""
    return list_compositor_node_types(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
