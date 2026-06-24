"""Shared Blender physics and simulation helpers."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Tuple

from dcc_mcp_core.skill import skill_error, skill_exception, skill_success

SIMULATION_MODIFIER_TYPES = {
    "CLOTH",
    "COLLISION",
    "SOFT_BODY",
    "FLUID",
    "DYNAMIC_PAINT",
    "PARTICLE_SYSTEM",
}

RIGID_BODY_WORLD_NUMERIC = {
    "time_scale",
    "substeps_per_frame",
    "solver_iterations",
}

CLOTH_NUMERIC_SETTINGS = {
    "quality",
    "mass",
    "tension_stiffness",
    "compression_stiffness",
    "shear_stiffness",
    "bending_stiffness",
    "air_damping",
}

COLLISION_NUMERIC_SETTINGS = {
    "absorption",
    "damping",
    "damping_factor",
    "friction",
    "permeability",
    "stickiness",
    "thickness_inner",
    "thickness_outer",
}


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
    bpy.context.active_object = obj


def _objects(bpy) -> Iterable[Any]:
    return list(getattr(bpy.data, "objects", []) or [])


def _object_named(bpy, object_name: str) -> Any:
    return bpy.data.objects.get(object_name)


def _bool_from_string(value: str) -> Optional[bool]:
    normalized = value.strip().lower()
    if normalized in {"true", "1", "yes", "on"}:
        return True
    if normalized in {"false", "0", "no", "off"}:
        return False
    return None


def _coerce_setting(target: Any, key: str, value: Any, numeric_keys: Iterable[str]) -> Any:
    if value is None:
        return None
    numeric = set(numeric_keys)
    current = getattr(target, key, None)
    if isinstance(current, bool):
        if isinstance(value, str):
            parsed = _bool_from_string(value)
            if parsed is not None:
                return parsed
        return bool(value)
    if isinstance(current, int) and not isinstance(current, bool):
        return int(value)
    if key in numeric or isinstance(current, float):
        return float(value)
    return value


def _apply_settings(
    target: Any, settings: Optional[Dict[str, Any]], numeric_keys: Iterable[str]
) -> Tuple[Dict[str, Any], List[str]]:
    applied: Dict[str, Any] = {}
    skipped: List[str] = []
    if not settings:
        return applied, skipped
    for key, value in settings.items():
        if not hasattr(target, key):
            skipped.append(key)
            continue
        coerced = _coerce_setting(target, key, value, numeric_keys)
        if coerced is None:
            continue
        setattr(target, key, coerced)
        applied[key] = coerced
    return applied, skipped


def _modifier_settings(modifier: Any) -> Any:
    return getattr(modifier, "settings", modifier)


def _modifier_point_cache(modifier: Any) -> Any:
    settings = getattr(modifier, "settings", None)
    return getattr(modifier, "point_cache", None) or getattr(settings, "point_cache", None)


def _modifier_context(modifier: Any) -> Dict[str, Any]:
    cache = _modifier_point_cache(modifier)
    context = {
        "name": getattr(modifier, "name", ""),
        "type": getattr(modifier, "type", ""),
    }
    if cache is not None:
        context["cache"] = _cache_context(cache)
    return context


def _cache_context(cache: Any) -> Dict[str, Any]:
    return {
        "frame_start": getattr(cache, "frame_start", None),
        "frame_end": getattr(cache, "frame_end", None),
        "is_baked": bool(getattr(cache, "is_baked", False)),
        "use_disk_cache": bool(getattr(cache, "use_disk_cache", False)),
    }


def _find_modifier(obj: Any, modifier_name: Optional[str], expected_type: Optional[str] = None) -> Any:
    modifiers = getattr(obj, "modifiers", [])
    if modifier_name:
        get = getattr(modifiers, "get", None)
        modifier = get(modifier_name) if callable(get) else None
        if modifier is None:
            for candidate in modifiers:
                if getattr(candidate, "name", None) == modifier_name:
                    modifier = candidate
                    break
        if modifier is None:
            return None
        if expected_type and getattr(modifier, "type", None) != expected_type:
            return None
        return modifier

    for modifier in modifiers:
        if expected_type is None or getattr(modifier, "type", None) == expected_type:
            return modifier
    return None


def _simulation_modifiers_for_object(obj: Any, modifier_name: Optional[str] = None) -> List[Any]:
    modifiers = []
    for modifier in getattr(obj, "modifiers", []) or []:
        if modifier_name and getattr(modifier, "name", None) != modifier_name:
            continue
        if getattr(modifier, "type", None) in SIMULATION_MODIFIER_TYPES:
            modifiers.append(modifier)
    return modifiers


def _matching_objects(bpy, object_name: Optional[str]) -> Tuple[List[Any], Optional[dict]]:
    if object_name:
        obj = _object_named(bpy, object_name)
        if obj is None:
            return [], skill_error(f"Object not found: {object_name}", f"No object named '{object_name}'.")
        return [obj], None
    return list(_objects(bpy)), None


def _ensure_rigid_body_world(bpy) -> Any:
    scene = bpy.context.scene
    world = getattr(scene, "rigidbody_world", None)
    if world is None:
        bpy.ops.rigidbody.world_add()
        world = getattr(scene, "rigidbody_world", None)
    return world


def _set_cache_frames(cache: Any, frame_start: Optional[int], frame_end: Optional[int]) -> Dict[str, Any]:
    applied: Dict[str, Any] = {}
    if cache is None:
        return applied
    if frame_start is not None and hasattr(cache, "frame_start"):
        cache.frame_start = int(frame_start)
        applied["frame_start"] = int(frame_start)
    if frame_end is not None and hasattr(cache, "frame_end"):
        cache.frame_end = int(frame_end)
        applied["frame_end"] = int(frame_end)
    return applied


def _set_scene_frames(scene: Any, frame_start: Optional[int], frame_end: Optional[int]) -> Dict[str, Any]:
    applied: Dict[str, Any] = {}
    if frame_start is not None:
        scene.frame_start = int(frame_start)
        applied["frame_start"] = int(frame_start)
    if frame_end is not None:
        scene.frame_end = int(frame_end)
        applied["frame_end"] = int(frame_end)
    return applied


def list_rigid_bodies(object_name: Optional[str] = None) -> dict:
    """List rigid bodies in the current scene."""
    try:
        import bpy

        objects, error = _matching_objects(bpy, object_name)
        if error:
            return error

        rigid_bodies = []
        for obj in objects:
            rigid_body = getattr(obj, "rigid_body", None)
            if rigid_body is None:
                continue
            rigid_bodies.append(
                {
                    "object_name": getattr(obj, "name", ""),
                    "body_type": getattr(rigid_body, "type", None),
                    "mass": getattr(rigid_body, "mass", None),
                    "collision_shape": getattr(rigid_body, "collision_shape", None),
                    "friction": getattr(rigid_body, "friction", None),
                    "restitution": getattr(rigid_body, "restitution", None),
                }
            )
        return skill_success(
            f"Found {len(rigid_bodies)} rigid bodies",
            count=len(rigid_bodies),
            rigid_bodies=rigid_bodies,
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message="Failed to list rigid bodies")


def set_rigid_body_world_settings(
    settings: Optional[Dict[str, Any]] = None,
    frame_start: Optional[int] = None,
    frame_end: Optional[int] = None,
    time_scale: Optional[float] = None,
    substeps_per_frame: Optional[int] = None,
    solver_iterations: Optional[int] = None,
) -> dict:
    """Create/update scene-level rigid-body world settings."""
    try:
        import bpy

        world = _ensure_rigid_body_world(bpy)
        if world is None:
            return skill_error("Rigid body world unavailable", "Blender did not create scene.rigidbody_world.")

        updates = {
            "time_scale": time_scale,
            "substeps_per_frame": substeps_per_frame,
            "solver_iterations": solver_iterations,
        }
        if settings:
            updates.update(settings)
        applied, skipped = _apply_settings(world, updates, RIGID_BODY_WORLD_NUMERIC)
        cache_applied = _set_cache_frames(getattr(world, "point_cache", None), frame_start, frame_end)
        scene_applied = _set_scene_frames(bpy.context.scene, frame_start, frame_end)
        return skill_success(
            "Updated rigid body world settings",
            applied=applied,
            skipped=skipped,
            cache=cache_applied,
            scene=scene_applied,
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message="Failed to update rigid body world settings")


def bake_rigid_body_simulation(
    frame_start: Optional[int] = None,
    frame_end: Optional[int] = None,
    dry_run: bool = False,
) -> dict:
    """Bake rigid-body simulation caches for the scene."""
    try:
        import bpy

        world = _ensure_rigid_body_world(bpy)
        if world is None:
            return skill_error("Rigid body world unavailable", "Blender did not create scene.rigidbody_world.")

        cache = getattr(world, "point_cache", None)
        cache_applied = _set_cache_frames(cache, frame_start, frame_end)
        scene_applied = _set_scene_frames(bpy.context.scene, frame_start, frame_end)
        if not dry_run:
            bpy.ops.ptcache.bake_all(bake=True)
        return skill_success(
            "Rigid body simulation bake prepared" if dry_run else "Baked rigid body simulation",
            dry_run=bool(dry_run),
            cache=cache_applied,
            scene=scene_applied,
            status=_cache_context(cache) if cache is not None else {},
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message="Failed to bake rigid body simulation")


def clear_rigid_body_bake() -> dict:
    """Clear rigid-body and point-cache bakes in the current scene."""
    try:
        import bpy

        bpy.ops.ptcache.free_bake_all()
        world = getattr(bpy.context.scene, "rigidbody_world", None)
        cache = getattr(world, "point_cache", None) if world is not None else None
        return skill_success(
            "Cleared rigid body simulation bake",
            status=_cache_context(cache) if cache is not None else {},
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message="Failed to clear rigid body bake")


def add_simulation_modifier(
    object_name: str,
    modifier_type: str,
    name: Optional[str] = None,
    settings: Optional[Dict[str, Any]] = None,
) -> dict:
    """Add a Blender simulation modifier to a mesh object."""
    try:
        import bpy

        obj = _object_named(bpy, object_name)
        if obj is None:
            return skill_error(f"Object not found: {object_name}", f"No object named '{object_name}'.")
        if getattr(obj, "type", None) != "MESH":
            return skill_error(f"{object_name} is not a mesh", "Simulation modifiers require a mesh object.")

        modifier_name = name or modifier_type.title().replace("_", " ")
        existing = _find_modifier(obj, modifier_name, modifier_type)
        created = False
        if existing is None:
            existing = obj.modifiers.new(modifier_name, modifier_type)
            created = True

        target = _modifier_settings(existing)
        numeric_keys = CLOTH_NUMERIC_SETTINGS if modifier_type == "CLOTH" else COLLISION_NUMERIC_SETTINGS
        applied, skipped = _apply_settings(target, settings, numeric_keys)
        return skill_success(
            f"{'Added' if created else 'Updated'} {modifier_type} modifier on {object_name}",
            object_name=object_name,
            modifier=_modifier_context(existing),
            created=created,
            applied=applied,
            skipped=skipped,
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to add {modifier_type} modifier to {object_name}")


def set_simulation_modifier_settings(
    object_name: str,
    modifier_type: str,
    modifier_name: Optional[str] = None,
    settings: Optional[Dict[str, Any]] = None,
) -> dict:
    """Update settings on an existing simulation modifier."""
    try:
        import bpy

        obj = _object_named(bpy, object_name)
        if obj is None:
            return skill_error(f"Object not found: {object_name}", f"No object named '{object_name}'.")
        modifier = _find_modifier(obj, modifier_name, modifier_type)
        if modifier is None:
            label = modifier_name or modifier_type
            return skill_error(f"Simulation modifier not found: {label}", f"{object_name} has no matching modifier.")

        numeric_keys = CLOTH_NUMERIC_SETTINGS if modifier_type == "CLOTH" else COLLISION_NUMERIC_SETTINGS
        applied, skipped = _apply_settings(_modifier_settings(modifier), settings, numeric_keys)
        return skill_success(
            f"Updated {modifier_type} settings on {object_name}",
            object_name=object_name,
            modifier=_modifier_context(modifier),
            applied=applied,
            skipped=skipped,
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to update {modifier_type} settings on {object_name}")


def add_cloth_modifier(
    object_name: str,
    name: str = "Cloth",
    settings: Optional[Dict[str, Any]] = None,
) -> dict:
    """Add or update a cloth modifier."""
    return add_simulation_modifier(object_name, "CLOTH", name=name, settings=settings)


def set_cloth_settings(
    object_name: str,
    modifier_name: Optional[str] = None,
    settings: Optional[Dict[str, Any]] = None,
) -> dict:
    """Update an existing cloth modifier."""
    return set_simulation_modifier_settings(object_name, "CLOTH", modifier_name=modifier_name, settings=settings)


def add_collision_modifier(
    object_name: str,
    name: str = "Collision",
    settings: Optional[Dict[str, Any]] = None,
) -> dict:
    """Add or update a collision modifier."""
    return add_simulation_modifier(object_name, "COLLISION", name=name, settings=settings)


def set_collision_settings(
    object_name: str,
    modifier_name: Optional[str] = None,
    settings: Optional[Dict[str, Any]] = None,
) -> dict:
    """Update an existing collision modifier."""
    return set_simulation_modifier_settings(object_name, "COLLISION", modifier_name=modifier_name, settings=settings)


def list_simulation_modifiers(object_name: Optional[str] = None) -> dict:
    """List cloth, collision, soft-body, fluid, paint, and particle modifiers."""
    try:
        import bpy

        objects, error = _matching_objects(bpy, object_name)
        if error:
            return error

        entries = []
        for obj in objects:
            for modifier in _simulation_modifiers_for_object(obj):
                item = _modifier_context(modifier)
                item["object_name"] = getattr(obj, "name", "")
                entries.append(item)
        return skill_success(
            f"Found {len(entries)} simulation modifiers",
            count=len(entries),
            modifiers=entries,
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message="Failed to list simulation modifiers")


def _target_simulation_modifiers(
    bpy, object_name: Optional[str], modifier_name: Optional[str]
) -> Tuple[List[Tuple[Any, Any]], Optional[dict]]:
    objects, error = _matching_objects(bpy, object_name)
    if error:
        return [], error
    targets: List[Tuple[Any, Any]] = []
    for obj in objects:
        for modifier in _simulation_modifiers_for_object(obj, modifier_name):
            targets.append((obj, modifier))
    if modifier_name and not targets:
        return [], skill_error(
            f"Simulation modifier not found: {modifier_name}", "No matching simulation modifier exists."
        )
    return targets, None


def bake_simulation(
    object_name: Optional[str] = None,
    modifier_name: Optional[str] = None,
    frame_start: Optional[int] = None,
    frame_end: Optional[int] = None,
    dry_run: bool = False,
) -> dict:
    """Bake simulation caches for matching modifiers."""
    try:
        import bpy

        targets, error = _target_simulation_modifiers(bpy, object_name, modifier_name)
        if error:
            return error
        if not targets:
            return skill_error(
                "No simulation modifiers found", "Add cloth, collision, soft-body, fluid, or particle modifiers first."
            )

        cache_updates = []
        for obj, modifier in targets:
            cache = _modifier_point_cache(modifier)
            cache_updates.append(
                {
                    "object_name": getattr(obj, "name", ""),
                    "modifier": _modifier_context(modifier),
                    "applied": _set_cache_frames(cache, frame_start, frame_end),
                }
            )
        _set_scene_frames(bpy.context.scene, frame_start, frame_end)
        if not dry_run:
            first_obj = targets[0][0]
            _activate_object(bpy, first_obj)
            bpy.ops.ptcache.bake_all(bake=True)
        return skill_success(
            "Simulation bake prepared" if dry_run else "Baked simulation caches",
            dry_run=bool(dry_run),
            targets=cache_updates,
            count=len(cache_updates),
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message="Failed to bake simulation")


def clear_simulation_cache(
    object_name: Optional[str] = None,
    modifier_name: Optional[str] = None,
    dry_run: bool = False,
) -> dict:
    """Clear simulation caches for matching modifiers."""
    try:
        import bpy

        targets, error = _target_simulation_modifiers(bpy, object_name, modifier_name)
        if error:
            return error
        if not targets:
            return skill_error("No simulation modifiers found", "No matching simulation caches were found.")

        cleared = []
        for obj, modifier in targets:
            cleared.append(
                {
                    "object_name": getattr(obj, "name", ""),
                    "modifier": _modifier_context(modifier),
                }
            )
        if not dry_run:
            _activate_object(bpy, targets[0][0])
            bpy.ops.ptcache.free_bake_all()
        return skill_success(
            "Simulation cache clear prepared" if dry_run else "Cleared simulation caches",
            dry_run=bool(dry_run),
            targets=cleared,
            count=len(cleared),
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message="Failed to clear simulation cache")


# ---------------------------------------------------------------------------
# Soft body
# ---------------------------------------------------------------------------

SOFT_BODY_NUMERIC_SETTINGS = {
    "mass",
    "friction",
    "speed",
    "goal_spring",
    "goal_friction",
    "pull",
    "push",
    "damping",
    "bend",
    "shear",
}


def add_soft_body_modifier(
    object_name: str,
    name: str = "Softbody",
    settings: Optional[Dict[str, Any]] = None,
) -> dict:
    """Add or update a soft-body modifier on a mesh object."""
    return add_simulation_modifier(object_name, "SOFT_BODY", name=name, settings=settings)


def set_soft_body_settings(
    object_name: str,
    modifier_name: Optional[str] = None,
    settings: Optional[Dict[str, Any]] = None,
) -> dict:
    """Update settings on an existing soft-body modifier."""
    try:
        import bpy

        obj = _object_named(bpy, object_name)
        if obj is None:
            return skill_error(f"Object not found: {object_name}", f"No object named '{object_name}'.")
        modifier = _find_modifier(obj, modifier_name, "SOFT_BODY")
        if modifier is None:
            label = modifier_name or "SOFT_BODY"
            return skill_error(f"Soft-body modifier not found: {label}", f"{object_name} has no soft-body modifier.")

        # Soft body settings live on modifier.settings
        target = _modifier_settings(modifier)
        applied, skipped = _apply_settings(target, settings, SOFT_BODY_NUMERIC_SETTINGS)
        return skill_success(
            f"Updated SOFT_BODY settings on {object_name}",
            object_name=object_name,
            modifier=_modifier_context(modifier),
            applied=applied,
            skipped=skipped,
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to update soft-body settings on {object_name}")


# ---------------------------------------------------------------------------
# Rigid body constraints
# ---------------------------------------------------------------------------

RIGID_BODY_CONSTRAINT_TYPES = {
    "FIXED",
    "POINT",
    "HINGE",
    "SLIDER",
    "PISTON",
    "GENERIC",
    "GENERIC_SPRING",
    "MOTOR",
}

RIGID_BODY_CONSTRAINT_NUMERIC = {
    "breaking_threshold",
    "limit_lin_x_lower",
    "limit_lin_x_upper",
    "limit_lin_y_lower",
    "limit_lin_y_upper",
    "limit_lin_z_lower",
    "limit_lin_z_upper",
    "limit_ang_x_lower",
    "limit_ang_x_upper",
    "limit_ang_y_lower",
    "limit_ang_y_upper",
    "limit_ang_z_lower",
    "limit_ang_z_upper",
}


def add_rigid_body_constraint(
    object_name: str,
    constraint_type: str = "FIXED",
    object1: Optional[str] = None,
    object2: Optional[str] = None,
    settings: Optional[Dict[str, Any]] = None,
) -> dict:
    """Add a rigid-body constraint to *object_name*.

    The constraint is stored on the object's ``rigid_body_constraint``
    property; Blender requires the object to be of type EMPTY or MESH.

    Parameters
    ----------
    object_name:
        Name of the empty/mesh that holds the constraint.
    constraint_type:
        One of FIXED, POINT, HINGE, SLIDER, PISTON, GENERIC, GENERIC_SPRING, MOTOR.
    object1, object2:
        Names of the two rigid body objects to connect (optional).
    settings:
        Additional constraint properties to set (e.g. breaking_threshold).
    """
    try:
        import bpy

        obj = _object_named(bpy, object_name)
        if obj is None:
            return skill_error(f"Object not found: {object_name}", f"No object named '{object_name}'.")

        normalized = constraint_type.upper()
        if normalized not in RIGID_BODY_CONSTRAINT_TYPES:
            return skill_error(
                f"Unsupported constraint type: {constraint_type}",
                f"Expected one of {sorted(RIGID_BODY_CONSTRAINT_TYPES)}.",
            )

        _activate_object(bpy, obj)
        if getattr(obj, "rigid_body_constraint", None) is None:
            bpy.ops.rigidbody.constraint_add(type=normalized)

        rbc = getattr(obj, "rigid_body_constraint", None)
        if rbc is None:
            return skill_error("Constraint creation failed", "Blender did not attach a rigid body constraint.")

        rbc.type = normalized

        if object1:
            tgt1 = _object_named(bpy, object1)
            if tgt1 is not None:
                rbc.object1 = tgt1
        if object2:
            tgt2 = _object_named(bpy, object2)
            if tgt2 is not None:
                rbc.object2 = tgt2

        if settings:
            _apply_settings(rbc, settings, RIGID_BODY_CONSTRAINT_NUMERIC)

        return skill_success(
            f"Added {normalized} rigid body constraint to {object_name}",
            object_name=object_name,
            constraint_type=getattr(rbc, "type", normalized),
            object1=getattr(getattr(rbc, "object1", None), "name", None),
            object2=getattr(getattr(rbc, "object2", None), "name", None),
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to add rigid body constraint to {object_name}")


def remove_rigid_body_constraint(object_name: str) -> dict:
    """Remove the rigid-body constraint from *object_name*."""
    try:
        import bpy

        obj = _object_named(bpy, object_name)
        if obj is None:
            return skill_error(f"Object not found: {object_name}", f"No object named '{object_name}'.")
        if getattr(obj, "rigid_body_constraint", None) is None:
            return skill_error(
                f"No constraint on {object_name}", f"{object_name} has no rigid_body_constraint."
            )
        _activate_object(bpy, obj)
        bpy.ops.rigidbody.constraint_remove()
        return skill_success(
            f"Removed rigid body constraint from {object_name}",
            object_name=object_name,
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to remove rigid body constraint from {object_name}")


def list_rigid_body_constraints(object_name: Optional[str] = None) -> dict:
    """List rigid-body constraints in the scene or on a single object."""
    try:
        import bpy

        objects, error = _matching_objects(bpy, object_name)
        if error:
            return error

        constraints = []
        for obj in objects:
            rbc = getattr(obj, "rigid_body_constraint", None)
            if rbc is None:
                continue
            constraints.append(
                {
                    "object_name": getattr(obj, "name", ""),
                    "constraint_type": getattr(rbc, "type", None),
                    "enabled": bool(getattr(rbc, "enabled", True)),
                    "disable_collisions": bool(getattr(rbc, "disable_collisions", False)),
                    "object1": getattr(getattr(rbc, "object1", None), "name", None),
                    "object2": getattr(getattr(rbc, "object2", None), "name", None),
                }
            )
        return skill_success(
            f"Found {len(constraints)} rigid body constraints",
            count=len(constraints),
            constraints=constraints,
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message="Failed to list rigid body constraints")


# ---------------------------------------------------------------------------
# Force fields
# ---------------------------------------------------------------------------

FORCE_FIELD_TYPES = {
    "FORCE",
    "WIND",
    "VORTEX",
    "MAGNET",
    "HARMONIC",
    "CHARGE",
    "LENNARDJ",
    "TEXTURE",
    "GUIDE",
    "BOID",
    "TURBULENCE",
    "DRAG",
    "SMOKE",
}

FORCE_FIELD_NUMERIC = {
    "strength",
    "falloff_power",
    "distance_min",
    "distance_max",
    "noise",
    "flow",
}


def add_force_field(
    object_name: str,
    field_type: str = "FORCE",
    strength: float = 1.0,
    settings: Optional[Dict[str, Any]] = None,
) -> dict:
    """Add a force-field physics property to *object_name*.

    Parameters
    ----------
    object_name:
        Name of the Blender object that emits the force.
    field_type:
        Type of force field (FORCE, WIND, VORTEX, etc.).
    strength:
        Initial strength value.
    settings:
        Additional force field properties to set.
    """
    try:
        import bpy

        obj = _object_named(bpy, object_name)
        if obj is None:
            return skill_error(f"Object not found: {object_name}", f"No object named '{object_name}'.")

        normalized = field_type.upper()
        if normalized not in FORCE_FIELD_TYPES:
            return skill_error(
                f"Unsupported force field type: {field_type}",
                f"Expected one of {sorted(FORCE_FIELD_TYPES)}.",
            )

        _activate_object(bpy, obj)
        # Set the field type on the object's physics
        if not hasattr(obj, "field") or obj.field is None:
            # Blender creates the field property when we set the type
            pass

        field = getattr(obj, "field", None)
        if field is not None:
            field.type = normalized
            field.strength = float(strength)
        else:
            # Fallback: use bpy.ops if available
            try:
                bpy.ops.object.forcefield_toggle()
                field = getattr(obj, "field", None)
                if field is not None:
                    field.type = normalized
                    field.strength = float(strength)
            except Exception:
                pass

        field = getattr(obj, "field", None)
        if field is None or getattr(field, "type", "NONE") == "NONE":
            return skill_error("Force field creation failed", "Could not set force field on object.")

        if settings:
            _apply_settings(field, settings, FORCE_FIELD_NUMERIC)

        return skill_success(
            f"Added {normalized} force field to {object_name}",
            object_name=object_name,
            field_type=getattr(field, "type", normalized),
            strength=getattr(field, "strength", strength),
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to add force field to {object_name}")


def remove_force_field(object_name: str) -> dict:
    """Remove the force-field physics property from *object_name*."""
    try:
        import bpy

        obj = _object_named(bpy, object_name)
        if obj is None:
            return skill_error(f"Object not found: {object_name}", f"No object named '{object_name}'.")

        field = getattr(obj, "field", None)
        if field is None or getattr(field, "type", "NONE") == "NONE":
            return skill_error(f"No force field on {object_name}", f"{object_name} has no active force field.")

        _activate_object(bpy, obj)
        try:
            bpy.ops.object.forcefield_toggle()
        except Exception:
            field.type = "NONE"

        return skill_success(
            f"Removed force field from {object_name}",
            object_name=object_name,
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to remove force field from {object_name}")


def list_force_fields(object_name: Optional[str] = None) -> dict:
    """List objects that have an active force field."""
    try:
        import bpy

        objects, error = _matching_objects(bpy, object_name)
        if error:
            return error

        fields = []
        for obj in objects:
            field = getattr(obj, "field", None)
            if field is None or getattr(field, "type", "NONE") == "NONE":
                continue
            fields.append(
                {
                    "object_name": getattr(obj, "name", ""),
                    "field_type": getattr(field, "type", None),
                    "strength": getattr(field, "strength", None),
                    "falloff_power": getattr(field, "falloff_power", None),
                }
            )
        return skill_success(
            f"Found {len(fields)} force fields",
            count=len(fields),
            force_fields=fields,
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message="Failed to list force fields")


# ---------------------------------------------------------------------------
# Particle systems
# ---------------------------------------------------------------------------

PARTICLE_SYSTEM_NUMERIC = {
    "count",
    "frame_start",
    "frame_end",
    "lifetime",
    "emit_from",
}


def add_particle_system(
    object_name: str,
    name: str = "ParticleSystem",
    count: Optional[int] = None,
    frame_start: Optional[int] = None,
    frame_end: Optional[int] = None,
    lifetime: Optional[float] = None,
    settings: Optional[Dict[str, Any]] = None,
) -> dict:
    """Add a particle system modifier to a mesh object.

    Parameters
    ----------
    object_name:
        Mesh object to receive the particle system.
    name:
        Name for the new particle system (and its modifier).
    count:
        Number of particles.
    frame_start, frame_end:
        Emission frame range.
    lifetime:
        Particle lifetime in frames.
    settings:
        Additional particle settings properties.
    """
    try:
        import bpy

        obj = _object_named(bpy, object_name)
        if obj is None:
            return skill_error(f"Object not found: {object_name}", f"No object named '{object_name}'.")
        if getattr(obj, "type", None) != "MESH":
            return skill_error(f"{object_name} is not a mesh", "Particle systems require a mesh object.")

        _activate_object(bpy, obj)
        modifier = obj.modifiers.new(name, "PARTICLE_SYSTEM")
        ps = getattr(modifier, "particle_system", None)
        psettings = getattr(ps, "settings", None) if ps else None

        if psettings is not None:
            if count is not None:
                psettings.count = int(count)
            if frame_start is not None:
                psettings.frame_start = float(frame_start)
            if frame_end is not None:
                psettings.frame_end = float(frame_end)
            if lifetime is not None:
                psettings.lifetime = float(lifetime)
            if settings:
                _apply_settings(psettings, settings, PARTICLE_SYSTEM_NUMERIC)

        return skill_success(
            f"Added particle system '{name}' to {object_name}",
            object_name=object_name,
            modifier_name=getattr(modifier, "name", name),
            count=getattr(psettings, "count", None) if psettings else None,
            frame_start=getattr(psettings, "frame_start", None) if psettings else None,
            frame_end=getattr(psettings, "frame_end", None) if psettings else None,
            lifetime=getattr(psettings, "lifetime", None) if psettings else None,
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to add particle system to {object_name}")


def set_particle_system_settings(
    object_name: str,
    modifier_name: Optional[str] = None,
    settings: Optional[Dict[str, Any]] = None,
) -> dict:
    """Update particle settings on an existing particle system modifier."""
    try:
        import bpy

        obj = _object_named(bpy, object_name)
        if obj is None:
            return skill_error(f"Object not found: {object_name}", f"No object named '{object_name}'.")
        modifier = _find_modifier(obj, modifier_name, "PARTICLE_SYSTEM")
        if modifier is None:
            label = modifier_name or "PARTICLE_SYSTEM"
            return skill_error(
                f"Particle system not found: {label}", f"{object_name} has no matching particle system modifier."
            )

        ps = getattr(modifier, "particle_system", None)
        psettings = getattr(ps, "settings", None) if ps else None
        if psettings is None:
            return skill_error("Particle settings unavailable", "Could not access particle system settings.")

        applied, skipped = _apply_settings(psettings, settings, PARTICLE_SYSTEM_NUMERIC)
        return skill_success(
            f"Updated particle system settings on {object_name}",
            object_name=object_name,
            modifier=_modifier_context(modifier),
            applied=applied,
            skipped=skipped,
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to update particle system settings on {object_name}")


def list_particle_systems(object_name: Optional[str] = None) -> dict:
    """List particle system modifiers in the scene."""
    try:
        import bpy

        objects, error = _matching_objects(bpy, object_name)
        if error:
            return error

        entries = []
        for obj in objects:
            for modifier in getattr(obj, "modifiers", []):
                if getattr(modifier, "type", None) != "PARTICLE_SYSTEM":
                    continue
                ps = getattr(modifier, "particle_system", None)
                psettings = getattr(ps, "settings", None) if ps else None
                entries.append(
                    {
                        "object_name": getattr(obj, "name", ""),
                        "modifier_name": getattr(modifier, "name", ""),
                        "particle_system_name": getattr(ps, "name", "") if ps else "",
                        "count": getattr(psettings, "count", None) if psettings else None,
                        "frame_start": getattr(psettings, "frame_start", None) if psettings else None,
                        "frame_end": getattr(psettings, "frame_end", None) if psettings else None,
                        "lifetime": getattr(psettings, "lifetime", None) if psettings else None,
                        "physics_type": getattr(psettings, "physics_type", None) if psettings else None,
                    }
                )
        return skill_success(
            f"Found {len(entries)} particle systems",
            count=len(entries),
            particle_systems=entries,
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message="Failed to list particle systems")


def get_simulation_status(object_name: Optional[str] = None) -> dict:
    """Return rigid-body world and modifier cache status."""
    try:
        import bpy

        objects, error = _matching_objects(bpy, object_name)
        if error:
            return error
        world = getattr(bpy.context.scene, "rigidbody_world", None)
        world_cache = getattr(world, "point_cache", None) if world is not None else None
        modifiers = []
        for obj in objects:
            for modifier in _simulation_modifiers_for_object(obj):
                item = _modifier_context(modifier)
                item["object_name"] = getattr(obj, "name", "")
                modifiers.append(item)
        return skill_success(
            "Simulation status retrieved",
            rigid_body_world={
                "exists": world is not None,
                "cache": _cache_context(world_cache) if world_cache is not None else {},
            },
            modifiers=modifiers,
            modifier_count=len(modifiers),
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message="Failed to get simulation status")
