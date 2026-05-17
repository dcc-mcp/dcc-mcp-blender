"""Create a new Blender object."""

from __future__ import annotations

import math
from typing import List, Optional

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success

PRIMITIVE_TYPES = {
    "cube": "bpy.ops.mesh.primitive_cube_add",
    "sphere": "bpy.ops.mesh.primitive_uv_sphere_add",
    "ico_sphere": "bpy.ops.mesh.primitive_ico_sphere_add",
    "cylinder": "bpy.ops.mesh.primitive_cylinder_add",
    "cone": "bpy.ops.mesh.primitive_cone_add",
    "torus": "bpy.ops.mesh.primitive_torus_add",
    "plane": "bpy.ops.mesh.primitive_plane_add",
    "circle": "bpy.ops.mesh.primitive_circle_add",
    "empty": "bpy.ops.object.empty_add",
}


def _get_active_object(bpy):
    return (
        getattr(bpy.context, "active_object", None)
        or getattr(bpy.context, "object", None)
        or getattr(getattr(getattr(bpy.context, "view_layer", None), "objects", None), "active", None)
    )


def create_object(
    object_type: str = "cube",
    name: Optional[str] = None,
    location: Optional[List[float]] = None,
    rotation: Optional[List[float]] = None,
    scale: Optional[List[float]] = None,
    size: float = 1.0,
) -> dict:
    """Create a new primitive object in the Blender scene.

    Args:
        object_type: Type of object to create. One of: cube, sphere, ico_sphere,
            cylinder, cone, torus, plane, circle, empty. Default: cube.
        name: Optional name for the new object. If None, Blender assigns a default.
        location: [x, y, z] position. Defaults to [0, 0, 0].
        rotation: [rx, ry, rz] rotation in degrees. Defaults to [0, 0, 0].
        scale: [sx, sy, sz] scale factors. Defaults to [1, 1, 1].
        size: Overall size multiplier (for primitives that support it).

    Returns:
        ActionResultModel dict with the created object's name and info.
    """
    try:
        import bpy

        object_type = object_type.lower()
        if object_type not in PRIMITIVE_TYPES:
            return skill_error(
                f"Unknown object type: {object_type}",
                f"Valid types: {', '.join(PRIMITIVE_TYPES.keys())}",
            )

        loc = location or [0.0, 0.0, 0.0]
        rot_deg = rotation or [0.0, 0.0, 0.0]
        rot_rad = [math.radians(r) for r in rot_deg]

        kwargs = {
            "location": loc,
            "rotation": rot_rad,
        }
        if object_type == "empty":
            bpy.ops.object.empty_add(**kwargs)
        elif object_type == "cube":
            bpy.ops.mesh.primitive_cube_add(size=size, **kwargs)
        elif object_type == "sphere":
            bpy.ops.mesh.primitive_uv_sphere_add(radius=size / 2, **kwargs)
        elif object_type == "ico_sphere":
            bpy.ops.mesh.primitive_ico_sphere_add(radius=size / 2, **kwargs)
        elif object_type == "cylinder":
            bpy.ops.mesh.primitive_cylinder_add(radius=size / 2, depth=size, **kwargs)
        elif object_type == "cone":
            bpy.ops.mesh.primitive_cone_add(radius1=size / 2, depth=size, **kwargs)
        elif object_type == "torus":
            bpy.ops.mesh.primitive_torus_add(**kwargs)
        elif object_type == "plane":
            bpy.ops.mesh.primitive_plane_add(size=size, **kwargs)
        elif object_type == "circle":
            bpy.ops.mesh.primitive_circle_add(radius=size / 2, **kwargs)

        obj = _get_active_object(bpy)
        if obj and name:
            obj.name = name
            if obj.data:
                obj.data.name = name

        if scale and obj:
            obj.scale = scale

        obj_name = obj.name if obj else "unknown"
        return skill_success(
            f"Created {object_type}: {obj_name}",
            object_name=obj_name,
            object_type=object_type,
            location=loc,
            prompt="Object created. Use move_object, rotate_object or scale_object to adjust it.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to create {object_type}")


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`create_object`."""
    return create_object(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
