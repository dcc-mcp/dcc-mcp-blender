"""Get detailed information about a Blender object."""

from __future__ import annotations

import math
from typing import Optional

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success


def get_object_info(object_name: Optional[str] = None, name: Optional[str] = None) -> dict:
    """Return detailed information about a specific object.

    Args:
        object_name: Preferred MCP-facing name of the object to inspect.
        name: Backwards-compatible alias for older callers.

    Returns:
        ActionResultModel dict with object details.
    """
    resolved_name = object_name or name
    if not resolved_name:
        return skill_error("Object name is required", "Pass object_name or the legacy name alias.")
    try:
        import bpy

        obj = bpy.data.objects.get(resolved_name)
        if obj is None:
            return skill_error(
                f"Object not found: {resolved_name}",
                f"No object named '{resolved_name}' in the scene.",
            )

        info = {
            "name": obj.name,
            "type": obj.type,
            "location": list(obj.location),
            "rotation_euler_degrees": [math.degrees(r) for r in obj.rotation_euler],
            "scale": list(obj.scale),
            "visible_viewport": not obj.hide_viewport,
            "visible_render": not obj.hide_render,
            "parent": obj.parent.name if obj.parent else None,
            "children": [c.name for c in obj.children],
            "collections": [c.name for c in obj.users_collection],
        }

        if obj.type == "MESH" and obj.data:
            info["vertex_count"] = len(obj.data.vertices)
            info["edge_count"] = len(obj.data.edges)
            info["face_count"] = len(obj.data.polygons)
            info["material_slots"] = [slot.material.name if slot.material else None for slot in obj.material_slots]

        return skill_success(
            f"Object info: {resolved_name}",
            **info,
            prompt="Use move_object, rotate_object, scale_object or blender-materials to modify this object.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to get info for: {resolved_name}")


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`get_object_info`."""
    return get_object_info(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
