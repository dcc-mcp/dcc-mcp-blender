"""Add rigid body physics to a Blender object."""

from __future__ import annotations

from typing import Any, Dict, Optional

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success

SUPPORTED_BODY_TYPES = {"ACTIVE", "PASSIVE"}
NUMERIC_PROPERTIES = {"mass", "friction", "restitution"}


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


def _apply_properties(rigid_body, properties: Dict[str, Any]) -> None:
    for key, value in properties.items():
        if value is not None and hasattr(rigid_body, key):
            if key in NUMERIC_PROPERTIES:
                value = float(value)
            setattr(rigid_body, key, value)


def add_rigid_body(
    object_name: str,
    body_type: str = "ACTIVE",
    mass: float = 1.0,
    friction: float = 0.5,
    restitution: float = 0.0,
    collision_shape: str = "CONVEX_HULL",
    properties: Optional[Dict[str, Any]] = None,
) -> dict:
    """Add rigid body physics to an object."""
    try:
        import bpy

        obj = bpy.data.objects.get(object_name)
        if obj is None:
            return skill_error(f"Object not found: {object_name}", f"No object named '{object_name}'.")

        normalized_type = body_type.upper()
        if normalized_type not in SUPPORTED_BODY_TYPES:
            return skill_error(
                f"Unsupported rigid body type: {body_type}",
                f"Expected one of {sorted(SUPPORTED_BODY_TYPES)}.",
            )

        _activate_object(bpy, obj)
        if getattr(obj, "rigid_body", None) is None:
            bpy.ops.rigidbody.object_add(type=normalized_type)

        rigid_body = getattr(obj, "rigid_body", None)
        if rigid_body is None:
            return skill_error(f"Rigid body was not created for {object_name}", "Blender did not attach a rigid body.")

        updates = {
            "type": normalized_type,
            "mass": mass,
            "friction": friction,
            "restitution": restitution,
            "collision_shape": collision_shape,
        }
        if properties:
            updates.update(properties)
        _apply_properties(rigid_body, updates)

        return skill_success(
            f"Added {normalized_type} rigid body to {object_name}",
            object_name=object_name,
            body_type=getattr(rigid_body, "type", normalized_type),
            mass=getattr(rigid_body, "mass", mass),
            collision_shape=getattr(rigid_body, "collision_shape", collision_shape),
            prompt="Use set_rigid_body_properties to tune simulation behavior.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to add rigid body to {object_name}")


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`add_rigid_body`."""
    return add_rigid_body(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
