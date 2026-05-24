"""Update rigid body physics properties on a Blender object."""

from __future__ import annotations

from typing import Any, Dict, Optional

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success

NUMERIC_PROPERTIES = {"mass", "friction", "restitution", "linear_damping", "angular_damping"}


def set_rigid_body_properties(
    object_name: str,
    body_type: Optional[str] = None,
    mass: Optional[float] = None,
    friction: Optional[float] = None,
    restitution: Optional[float] = None,
    linear_damping: Optional[float] = None,
    angular_damping: Optional[float] = None,
    collision_shape: Optional[str] = None,
    properties: Optional[Dict[str, Any]] = None,
) -> dict:
    """Update rigid body settings on an object."""
    try:
        import bpy

        obj = bpy.data.objects.get(object_name)
        if obj is None:
            return skill_error(f"Object not found: {object_name}", f"No object named '{object_name}'.")

        rigid_body = getattr(obj, "rigid_body", None)
        if rigid_body is None:
            return skill_error(f"{object_name} has no rigid body", "Call add_rigid_body first.")

        updates = {
            "type": body_type.upper() if isinstance(body_type, str) else body_type,
            "mass": mass,
            "friction": friction,
            "restitution": restitution,
            "linear_damping": linear_damping,
            "angular_damping": angular_damping,
            "collision_shape": collision_shape,
        }
        if properties:
            updates.update(properties)

        applied = {}
        for key, value in updates.items():
            if value is None:
                continue
            if not hasattr(rigid_body, key):
                continue
            if key in NUMERIC_PROPERTIES:
                value = float(value)
            setattr(rigid_body, key, value)
            applied[key] = value

        return skill_success(
            f"Updated rigid body on {object_name}",
            object_name=object_name,
            applied=applied,
            prompt="Use Blender playback or render tools to inspect the simulation setup.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to update rigid body on {object_name}")


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`set_rigid_body_properties`."""
    return set_rigid_body_properties(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
