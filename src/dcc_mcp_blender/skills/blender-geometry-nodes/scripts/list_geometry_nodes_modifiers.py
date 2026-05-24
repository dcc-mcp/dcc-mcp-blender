"""List Geometry Nodes modifiers on a Blender object."""

from __future__ import annotations

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success


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
            node_group = getattr(modifier, "node_group", None)
            modifiers.append(
                {
                    "name": modifier.name,
                    "type": modifier.type,
                    "node_group": getattr(node_group, "name", None),
                    "show_viewport": modifier.show_viewport,
                    "show_render": modifier.show_render,
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
