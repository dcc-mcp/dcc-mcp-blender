"""Create a UV sphere in Blender."""

from __future__ import annotations

import threading
from typing import List, Optional

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success


def _get_active_object(bpy):
    return (
        getattr(bpy.context, "active_object", None)
        or getattr(bpy.context, "object", None)
        or getattr(getattr(getattr(bpy.context, "view_layer", None), "objects", None), "active", None)
    )


def create_sphere(
    radius: float = 1.0,
    name: Optional[str] = None,
    location: Optional[List[float]] = None,
) -> dict:
    """Create a UV sphere using ``bpy.ops.mesh.primitive_uv_sphere_add``."""
    try:
        import bpy

        loc = location or [0.0, 0.0, 0.0]
        bpy.ops.mesh.primitive_uv_sphere_add(radius=radius, location=loc)
        obj = _get_active_object(bpy)
        if obj is not None and name:
            obj.name = name
            if getattr(obj, "data", None) is not None:
                obj.data.name = name

        object_name = getattr(obj, "name", name or "Sphere")
        return skill_success(
            f"Created sphere: {object_name}",
            object_name=object_name,
            radius=radius,
            location=loc,
            thread_ident=threading.get_ident(),
            prompt="Sphere created.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message="Failed to create sphere")


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`create_sphere`."""
    return create_sphere(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
