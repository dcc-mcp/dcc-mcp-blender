"""Remove rigid body physics from a Blender object."""

from __future__ import annotations

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success


def _activate_object(bpy, obj) -> None:
    try:
        bpy.ops.object.select_all(action="DESELECT")
    except Exception:
        pass
    try:
        obj.select_set(True)
    except Exception:
        pass
    bpy.context.view_layer.objects.active = obj


def remove_rigid_body(object_name: str) -> dict:
    """Remove rigid body physics from an object."""
    try:
        import bpy

        obj = bpy.data.objects.get(object_name)
        if obj is None:
            return skill_error(f"Object not found: {object_name}", f"No object named '{object_name}'.")
        if getattr(obj, "rigid_body", None) is None:
            return skill_error(f"{object_name} has no rigid body", "Nothing to remove.")

        _activate_object(bpy, obj)
        bpy.ops.rigidbody.object_remove()

        return skill_success(
            f"Removed rigid body from {object_name}",
            object_name=object_name,
            prompt="Use add_rigid_body to set up a new simulation body.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to remove rigid body from {object_name}")


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`remove_rigid_body`."""
    return remove_rigid_body(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
