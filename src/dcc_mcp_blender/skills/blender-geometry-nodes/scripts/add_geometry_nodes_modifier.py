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
    template: str = "pass_through",
) -> dict:
    """Add a Geometry Nodes modifier and optionally attach a node group.

    A group created here defaults to the ``pass_through`` template, so it owns a
    Geometry input, a Geometry output and a linked Group Input -> Group Output
    pair; an empty group cannot be wired by downstream tools.
    """
    wanted_group_name = group_name or f"{object_name} Geometry Nodes"
    if create_node_group or group_name:
        created = create_geometry_node_group(wanted_group_name, template=template)
        if not created.get("success"):
            return created
        group_context = created.get("context") or {}
    else:
        group_context = {}
    assigned = assign_geometry_node_group(object_name=object_name, group_name=wanted_group_name, modifier_name=name)
    context = assigned.get("context")
    if assigned.get("success") and isinstance(context, dict):
        context.setdefault("group_template", group_context.get("template", template))
        context.setdefault("group_created", bool(group_context.get("created", False)))
        context.setdefault("group_template_applied", bool(group_context.get("template_applied", False)))
    return assigned


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`add_geometry_nodes_modifier`."""
    return add_geometry_nodes_modifier(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
