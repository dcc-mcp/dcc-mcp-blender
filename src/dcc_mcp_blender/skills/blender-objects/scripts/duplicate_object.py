"""Duplicate an existing Blender object."""

from __future__ import annotations

from typing import List, Optional

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success


def _get_active_object(bpy):
    return (
        getattr(bpy.context, "active_object", None)
        or getattr(bpy.context, "object", None)
        or getattr(getattr(getattr(bpy.context, "view_layer", None), "objects", None), "active", None)
    )


def duplicate_object(
    name: str,
    new_name: Optional[str] = None,
    location_offset: Optional[List[float]] = None,
) -> dict:
    """Duplicate an object in the scene.

    Args:
        name: Name of the object to duplicate.
        new_name: Optional name for the duplicated object.
        location_offset: [dx, dy, dz] offset to apply relative to original object.

    Returns:
        ActionResultModel dict with the new object's name.
    """
    try:
        import bpy

        source = bpy.data.objects.get(name)
        if source is None:
            return skill_error(f"Object not found: {name}", f"No object named '{name}' in the scene.")

        # Deselect all, then select source
        bpy.ops.object.select_all(action="DESELECT")
        source.select_set(True)
        bpy.context.view_layer.objects.active = source

        bpy.ops.object.duplicate(linked=False)
        new_obj = _get_active_object(bpy)
        if new_obj is None:
            return skill_error("Duplicate failed", "Blender did not report an active duplicated object.")

        if new_name:
            new_obj.name = new_name
            if new_obj.data:
                new_obj.data.name = new_name

        if location_offset:
            new_obj.location[0] += location_offset[0]
            new_obj.location[1] += location_offset[1]
            new_obj.location[2] += location_offset[2]

        return skill_success(
            f"Duplicated {name} -> {new_obj.name}",
            source_name=name,
            new_name=new_obj.name,
            location=list(new_obj.location),
            prompt="Object duplicated. Use move_object or other tools to adjust the duplicate.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to duplicate object: {name}")


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`duplicate_object`."""
    return duplicate_object(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
