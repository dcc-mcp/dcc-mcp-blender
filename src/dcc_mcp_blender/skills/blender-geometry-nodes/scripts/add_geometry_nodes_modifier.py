"""Add a Geometry Nodes modifier to a Blender mesh object."""

from __future__ import annotations

from typing import Optional

from dcc_mcp_core.skill import skill_entry

from dcc_mcp_blender._node_graph_ops import assign_geometry_node_group, create_geometry_node_group


def add_geometry_nodes_modifier(
    object_name: str,
    name: str = "Geometry Nodes",
    group_name: Optional[str] = None,
    create_node_group: bool = True,
) -> dict:
    """Add a Geometry Nodes modifier and optionally attach a node group."""
    wanted_group_name = group_name or f"{object_name} Geometry Nodes"
    if create_node_group or group_name:
        created = create_geometry_node_group(wanted_group_name)
        if not created.get("success"):
            return created
    return assign_geometry_node_group(object_name=object_name, group_name=wanted_group_name, modifier_name=name)


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`add_geometry_nodes_modifier`."""
    return add_geometry_nodes_modifier(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
