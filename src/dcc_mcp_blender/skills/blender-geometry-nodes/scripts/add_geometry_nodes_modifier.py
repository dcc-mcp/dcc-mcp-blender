"""Add a Geometry Nodes modifier to a Blender mesh object."""

from __future__ import annotations

from typing import Optional

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success


def add_geometry_nodes_modifier(
    object_name: str,
    name: str = "Geometry Nodes",
    group_name: Optional[str] = None,
    create_node_group: bool = True,
) -> dict:
    """Add a Geometry Nodes modifier and optionally attach a node group."""
    try:
        import bpy

        obj = bpy.data.objects.get(object_name)
        if obj is None:
            return skill_error(f"Object not found: {object_name}", f"No object named '{object_name}'.")
        if obj.type != "MESH":
            return skill_error(
                f"{object_name} is not a mesh",
                f"Geometry Nodes modifiers are currently supported for MESH objects, got {obj.type}.",
            )

        bpy.context.view_layer.objects.active = obj
        modifier = obj.modifiers.new(name=name, type="NODES")

        node_group = None
        if create_node_group or group_name:
            wanted_group_name = group_name or f"{object_name} Geometry Nodes"
            node_group = bpy.data.node_groups.get(wanted_group_name)
            if node_group is None:
                node_group = bpy.data.node_groups.new(wanted_group_name, "GeometryNodeTree")
            modifier.node_group = node_group

        return skill_success(
            f"Added Geometry Nodes modifier to {object_name}",
            object_name=object_name,
            modifier_name=modifier.name,
            node_group=getattr(node_group, "name", None),
            prompt="Use list_geometry_nodes_modifiers to inspect procedural modifiers on this object.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to add Geometry Nodes modifier to {object_name}")


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`add_geometry_nodes_modifier`."""
    return add_geometry_nodes_modifier(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
