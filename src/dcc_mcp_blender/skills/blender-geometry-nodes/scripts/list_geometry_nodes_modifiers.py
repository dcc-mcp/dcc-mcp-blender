"""List Geometry Nodes modifiers on a Blender object."""

from __future__ import annotations

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success

from dcc_mcp_blender._node_graph_ops import evaluate_geometry_nodes_info


def list_geometry_nodes_modifiers(object_name: str) -> dict:
    """Return Geometry Nodes modifiers attached to an object."""
    try:
        import bpy

        obj = bpy.data.objects.get(object_name)
        if obj is None:
            return skill_error(f"Object not found: {object_name}", f"No object named '{object_name}'.")

        modifiers = []
        for modifier in obj.modifiers:
            if modifier.type != "NODES":
                continue
            info = evaluate_geometry_nodes_info(object_name=object_name, modifier_name=modifier.name)
            context = info.get("context", {}) if info.get("success") else {}
            modifiers.append(
                {
                    "name": modifier.name,
                    "type": modifier.type,
                    "node_group": context.get("group_name")
                    or getattr(getattr(modifier, "node_group", None), "name", None),
                    "show_viewport": modifier.show_viewport,
                    "show_render": modifier.show_render,
                    "node_count": context.get("node_count"),
                    "link_count": context.get("link_count"),
                    "inputs": context.get("inputs", []),
                }
            )

        return skill_success(
            f"Found {len(modifiers)} Geometry Nodes modifiers on {object_name}",
            object_name=object_name,
            modifiers=modifiers,
            count=len(modifiers),
            prompt="Use blender-shader-nodes or blender-mesh tools to continue procedural scene work.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to list Geometry Nodes modifiers on {object_name}")


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`list_geometry_nodes_modifiers`."""
    return list_geometry_nodes_modifiers(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
