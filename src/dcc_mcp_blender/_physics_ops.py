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


def _unapplied_note(not_applied: Iterable[str], version: Any = None) -> str:
    """Describe settings that were requested but did not take effect.

    Reporting these only in the context would keep the response looking like a
    clean success while nothing happened, which is how a wrong property name
    went unnoticed for a whole release. The caller sees them in the message.
    """
    names = sorted(set(not_applied))
    if not names:
        return ""
    host = f" by Blender {version}" if version else " by this Blender build"
    return f". Not applied (unsupported{host}): {', '.join(names)}"


def _modifier_settings(modifier: Any) -> Any:
    return getattr(modifier, "settings", modifier)


def _modifier_point_cache(modifier: Any) -> Any:
    settings = getattr(modifier, "settings", None)
    particle_system = getattr(modifier, "particle_system", None)
    return (
        getattr(modifier, "point_cache", None)
        or getattr(particle_system, "point_cache", None)
        or getattr(settings, "point_cache", None)
    )


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
    scene_objects = bpy.context.scene.objects
    if object_name is not None:
        obj = scene_objects.get(object_name)
        if obj is None:
            return [], skill_error("Object not in current scene", "Choose an object in the active scene.")
        objects = [obj]
    else:
        objects = list(scene_objects)
    targets: List[Tuple[Any, Any]] = []
    for obj in objects:
        for modifier in _simulation_modifiers_for_object(obj, modifier_name):
            targets.append((obj, modifier))
    if modifier_name and not targets:
        return [], skill_error(
            f"Simulation modifier not found: {modifier_name}", "No matching simulation modifier exists."
        )
    return targets, None


def _simulation_cache_operation(
    operation: str,
    object_name: Optional[str],
    modifier_name: Optional[str],
    dry_run: bool,
    frame_start: Optional[int] = None,
    frame_end: Optional[int] = None,
) -> dict:
    """Preflight all targets, then operate only on explicitly scoped point caches."""
    for label, name in (("object_name", object_name), ("modifier_name", modifier_name)):
        if name is not None and (not isinstance(name, str) or not name.strip() or len(name) > 256):
            return skill_error(
                "Invalid simulation target", f"{label} must be a nonempty name of at most 256 characters."
            )
    if type(dry_run) is not bool:
        return skill_error("Invalid dry_run", "dry_run must be a boolean.")
    for value in (frame_start, frame_end):
        if value is not None and (type(value) is not int or not 1 <= value <= 1048574):
            return skill_error("Invalid cache frame", "Cache frames must be integers between 1 and 1048574.")

    records = []
    mutation_started = False
    try:
        import bpy

        targets, error = _target_simulation_modifiers(bpy, object_name, modifier_name)
        if error:
            return error
        if not targets:
            return skill_error("No simulation modifiers found", "No matching simulation caches were found.")

        entries = []
        for obj, modifier in targets:
            cache = _modifier_point_cache(modifier)
            if modifier.type not in {"CLOTH", "SOFT_BODY", "PARTICLE_SYSTEM"} or cache is None:
                return skill_error(
                    "Unsupported simulation cache",
                    "Scoped point-cache operations support cloth, soft-body and particle caches only; no global fallback.",
                    object_name=obj.name,
                    modifier_name=modifier.name,
                    modifier_type=modifier.type,
                    mutation_state="none",
                )
            before = _cache_context(cache)
            start = frame_start if frame_start is not None else before["frame_start"]
            end = frame_end if frame_end is not None else before["frame_end"]
            if operation == "bake" and (
                type(start) is not int or type(end) is not int or not 1 <= start <= end <= 1048574
            ):
                return skill_error(
                    "Invalid cache range",
                    "Each target needs frame_start <= frame_end within valid cache bounds.",
                    mutation_state="none",
                )
            if operation == "bake" and before["is_baked"]:
                return skill_error(
                    "Cache already baked",
                    "Clear the exact target cache before changing or rebaking it.",
                    object_name=obj.name,
                    modifier_name=modifier.name,
                    mutation_state="none",
                )
            planned = {
                key: value
                for key, value in (("frame_start", frame_start), ("frame_end", frame_end))
                if value is not None
            }
            record = {
                "object_name": obj.name,
                "modifier": _modifier_context(modifier),
                "before": before,
                "planned": planned,
                "applied": {},
                "status": "planned",
            }
            records.append(record)
            entries.append((obj, cache, record))

        if dry_run:
            return skill_success(
                "Simulation cache operation prepared",
                dry_run=True,
                targets=records,
                count=len(records),
                mutation_state="none",
            )

        override = getattr(bpy.context, "temp_override", None)
        operator = getattr(bpy.ops.ptcache, "bake" if operation == "bake" else "free_bake", None)
        if not callable(override) or not callable(operator) or not callable(getattr(operator, "poll", None)):
            return skill_error(
                "Scoped cache context unavailable",
                "This runtime must support context.temp_override and the per-cache operator; no global fallback.",
                targets=records,
                mutation_state="none",
            )

        # Poll every target before changing any frame range or invoking a bake.
        for obj, cache, _record in entries:
            with override(scene=bpy.context.scene, object=obj, active_object=obj, point_cache=cache):
                if not operator.poll():
                    return skill_error(
                        "Scoped cache operator unavailable",
                        "The per-cache operator cannot run in this target's context.",
                        object_name=obj.name,
                        targets=records,
                        mutation_state="none",
                    )

        for obj, cache, record in entries:
            mutation_started = True
            record["status"] = "attempted"
            try:
                planned = record["planned"]
                # Blender may clamp range assignments; set the upper bound first
                # when moving the entire range above its previous end.
                keys = ["frame_start", "frame_end"]
                if planned.get("frame_start", cache.frame_start) > cache.frame_end:
                    keys.reverse()
                for key in keys:
                    if key in planned:
                        setattr(cache, key, planned[key])
                        record["applied"][key] = getattr(cache, key)
                if record["applied"] != planned:
                    raise ValueError("The target cache did not retain the requested frame range.")
                with override(scene=bpy.context.scene, object=obj, active_object=obj, point_cache=cache):
                    result = operator(bake=True) if operation == "bake" else operator()
                record["operator_result"] = sorted(result)
                if result != {"FINISHED"}:
                    raise ValueError("The scoped cache operator did not finish.")
                if bool(cache.is_baked) != (operation == "bake"):
                    raise ValueError("The target cache did not satisfy the baked-state postcondition.")
                record["status"] = "completed"
            finally:
                record["after"] = _cache_context(cache)
        return skill_success(
            "Baked simulation caches" if operation == "bake" else "Cleared simulation caches",
            dry_run=False,
            targets=records,
            count=len(records),
            mutation_state="completed",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(
            exc,
            message="Simulation cache operation failed",
            targets=records,
            completed_count=sum(record["status"] == "completed" for record in records),
            mutation_state="partial_or_unknown" if mutation_started else "none",
            prompt="Inspect get_simulation_status for these targets before deciding whether to retry; no global fallback was used.",
        )


def bake_simulation(
    object_name: Optional[str] = None,
    modifier_name: Optional[str] = None,
    frame_start: Optional[int] = None,
    frame_end: Optional[int] = None,
    dry_run: bool = False,
) -> dict:
    """Bake only matching point caches without changing scene range or selection."""
    return _simulation_cache_operation("bake", object_name, modifier_name, dry_run, frame_start, frame_end)


def clear_simulation_cache(
    object_name: Optional[str] = None,
    modifier_name: Optional[str] = None,
    dry_run: bool = False,
) -> dict:
    """Clear only matching point caches; never invoke a scene-wide cache operator."""
    return _simulation_cache_operation("clear", object_name, modifier_name, dry_run)


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
            return skill_error(f"No constraint on {object_name}", f"{object_name} has no rigid_body_constraint.")
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
}


def _resolve_particle_instance_object(bpy: Any, instance_object_name: Optional[str]) -> Tuple[Any, Optional[dict]]:
    if instance_object_name is None:
        return None, None
    instance_object = _object_named(bpy, instance_object_name)
    if instance_object is None:
        return None, skill_error(
            f"Object not found: {instance_object_name}",
            f"No particle instance object named '{instance_object_name}'.",
        )
    return instance_object, None


def _apply_particle_render_options(
    obj: Any,
    psettings: Any,
    instance_object_name: Optional[str],
    instance_object: Any,
    show_emitter: Optional[bool],
) -> Tuple[Dict[str, Any], List[str]]:
    applied: Dict[str, Any] = {}
    skipped: List[str] = []
    if instance_object_name is not None:
        if not hasattr(psettings, "instance_object"):
            skipped.append("instance_object_name")
        else:
            psettings.instance_object = instance_object
            applied["instance_object_name"] = instance_object_name
            if hasattr(psettings, "render_type"):
                psettings.render_type = "OBJECT"
                applied["render_type"] = "OBJECT"

    if show_emitter is not None:
        visible = bool(show_emitter)
        supported = False
        if hasattr(psettings, "use_render_emitter"):
            psettings.use_render_emitter = visible
            supported = True
        if hasattr(obj, "show_instancer_for_render"):
            obj.show_instancer_for_render = visible
            supported = True
        if supported:
            applied["show_emitter"] = visible
        else:
            skipped.append("show_emitter")
    return applied, skipped


def add_particle_system(
    object_name: str,
    name: str = "ParticleSystem",
    count: Optional[int] = None,
    frame_start: Optional[int] = None,
    frame_end: Optional[int] = None,
    lifetime: Optional[float] = None,
    instance_object_name: Optional[str] = None,
    show_emitter: Optional[bool] = None,
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
    instance_object_name:
        Optional scene object rendered for each particle. This also selects
        Blender's ``OBJECT`` particle render type.
    show_emitter:
        Whether the source mesh is visible in renders.
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
        instance_object, error = _resolve_particle_instance_object(bpy, instance_object_name)
        if error:
            return error

        _activate_object(bpy, obj)
        modifier = obj.modifiers.new(name, "PARTICLE_SYSTEM")
        ps = getattr(modifier, "particle_system", None)
        psettings = getattr(ps, "settings", None) if ps else None

        applied: Dict[str, Any] = {}
        skipped: List[str] = []
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
                settings_applied, settings_skipped = _apply_settings(psettings, settings, PARTICLE_SYSTEM_NUMERIC)
                applied.update(settings_applied)
                skipped.extend(settings_skipped)
            render_applied, render_skipped = _apply_particle_render_options(
                obj, psettings, instance_object_name, instance_object, show_emitter
            )
            applied.update(render_applied)
            skipped.extend(render_skipped)

        return skill_success(
            f"Added particle system '{name}' to {object_name}",
            object_name=object_name,
            modifier_name=getattr(modifier, "name", name),
            count=getattr(psettings, "count", None) if psettings else None,
            frame_start=getattr(psettings, "frame_start", None) if psettings else None,
            frame_end=getattr(psettings, "frame_end", None) if psettings else None,
            lifetime=getattr(psettings, "lifetime", None) if psettings else None,
            applied=applied,
            skipped=skipped,
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to add particle system to {object_name}")


def set_particle_system_settings(
    object_name: str,
    modifier_name: Optional[str] = None,
    instance_object_name: Optional[str] = None,
    show_emitter: Optional[bool] = None,
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
        instance_object, error = _resolve_particle_instance_object(bpy, instance_object_name)
        if error:
            return error

        applied, skipped = _apply_settings(psettings, settings, PARTICLE_SYSTEM_NUMERIC)
        render_applied, render_skipped = _apply_particle_render_options(
            obj, psettings, instance_object_name, instance_object, show_emitter
        )
        applied.update(render_applied)
        skipped.extend(render_skipped)
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


# ---------------------------------------------------------------------------
# Mantaflow fluid and Dynamic Paint
# ---------------------------------------------------------------------------

# Blender's FluidModifier.fluid_type enum: NONE is omitted because it selects
# no simulation at all. Mantaflow models inlets, outlets, and obstacles through
# nested settings on FLOW and EFFECTOR modifiers, not through fluid_type, so
# the legacy names are rejected with a pointer to the modern equivalent.
FLUID_TYPES = ("DOMAIN", "FLOW", "EFFECTOR")
FLUID_TYPE_ALIASES = {
    "INFLOW": ("FLOW", "modifier.flow_settings.flow_behavior = 'INFLOW'"),
    "OUTFLOW": ("FLOW", "modifier.flow_settings.flow_behavior = 'OUTFLOW'"),
    "OBSTACLE": ("EFFECTOR", "modifier.effector_settings.effector_type = 'COLLISION'"),
    "LIQUID": ("FLOW", "modifier.flow_settings.flow_type = 'LIQUID'"),
    "SMOKE": ("FLOW", "modifier.flow_settings.flow_type = 'SMOKE'"),
    "FIRE": ("FLOW", "modifier.flow_settings.flow_type = 'FIRE'"),
}
DYNAMIC_PAINT_TYPES = ("CANVAS", "BRUSH")
DYNAMIC_PAINT_SURFACE_TYPES = ("PAINT", "DISPLACE", "WEIGHT", "WAVE")

FLUID_NUMERIC_SETTINGS = {
    # Verified against live RNA on Blender 3.6.5, 4.5.13 and 5.2.1. The domain
    # resolution is `resolution_max`; `resolution_divisions` was removed in
    # 2.82 and the CFL property is not exposed as `cfl` on any of them.
    "resolution_max",
    "domain_resolution",
    "viscosity_base",
    "viscosity_exponent",
    "domain_size",
    "time_scale",
    "timesteps_max",
    "timesteps_min",
    "burning_rate",
    "flame_smoke",
    "flame_vorticity",
    "flame_ignition",
    "flame_max_temp",
    "noise_scale",
    "noise_strength",
    "noise_pos_scale",
    "noise_time_anim",
    "mesh_scale",
    "mesh_particle_radius",
    "particle_radius",
    "particle_max",
    "particle_number",
    "particle_min",
    "gridlevels",
    "compression_threshold",
    "surface_tension",
    "vorticity",
    "dissolve_speed",
}

DYNAMIC_PAINT_NUMERIC_SETTINGS = {
    "paint_wetness",
    "paint_dry_speed",
    "paint_depth",
    "paint_ramp",
    "disp_scale",
    "wave_damping",
    "wave_speed",
    "wave_timescale",
    "wave_spring",
    "wave_smoothness",
    "brush_absolute_alpha",
    "brush_alpha",
    "brush_radius",
    "brush_smudge_strength",
    "brush_ramp",
}

PARTICLE_HAIR_NUMERIC_SETTINGS = {
    "hair_length",
    "hair_step",
    "hair_radius",
    "hair_tip_length",
    "hair_bend",
    "child_nbr",
    "child_radius",
    "child_roundness",
    "child_length",
    "child_length_threshold",
    "child_clump_factor",
    "child_clump_noise",
    "child_roughness_endpoint",
    "child_roughness_end_shape",
    "child_twist",
    "rendered_child_count",
    "virtual_parents",
    "kink_amplitude",
    "kink_frequency",
    "kink_shape",
    "roughness_1",
    "roughness_2",
    "roughness_end_shape",
    "roughness_braid",
    "roughness_threshold",
    "braid_roughness",
    "clump_noise_size",
    "distribution_jitter",
    "display_step",
    "draw_step",
}


def add_fluid_modifier(
    object_name: str,
    fluid_type: str = "DOMAIN",
    name: Optional[str] = None,
    settings: Optional[Dict[str, Any]] = None,
) -> dict:
    """Add a Mantaflow fluid modifier to a mesh object.

    Args:
        object_name: Mesh object that receives the modifier.
        fluid_type: ``DOMAIN``, ``FLOW``, or ``EFFECTOR``. Mantaflow has no
            ``OBSTACLE``, ``INFLOW``, or ``OUTFLOW`` fluid type; those are
            ``FLOW`` or ``EFFECTOR`` modifiers configured through their nested
            settings, and passing one returns the exact property to set.
        name: Modifier name; defaults to the fluid type.
        settings: Extra modifier-level properties to apply.
    """
    wanted = str(fluid_type or "").upper()
    if wanted in FLUID_TYPE_ALIASES:
        modern, detail = FLUID_TYPE_ALIASES[wanted]
        return skill_error(
            f"Unsupported fluid type: {fluid_type}",
            f"{wanted} is not a Mantaflow fluid_type. Use {modern} and set {detail}.",
        )
    if wanted not in FLUID_TYPES:
        return skill_error(
            f"Unsupported fluid type: {fluid_type}",
            f"Supported fluid types: {', '.join(FLUID_TYPES)}.",
        )
    try:
        import bpy

        obj = _object_named(bpy, object_name)
        if obj is None:
            return skill_error(f"Object not found: {object_name}", f"No object named '{object_name}'.")
        if getattr(obj, "type", None) != "MESH":
            return skill_error(f"{object_name} is not a mesh", "Fluid modifiers require a mesh object.")

        # Blender allows exactly one FLUID modifier per object and returns None
        # from modifiers.new() when the type is already present, so the existing
        # one has to be reported instead of dereferencing None.
        existing = _find_modifier(obj, None, "FLUID")
        if existing is not None:
            return skill_error(
                "Object already has a fluid modifier",
                f"{object_name} already has fluid modifier '{getattr(existing, 'name', '?')}' "
                f"(fluid_type={getattr(existing, 'fluid_type', '?')}). Blender allows one per object; "
                "use set_fluid_settings to change it, or remove it first.",
            )

        modifier_name = name or f"Fluid {wanted.title()}"
        _activate_object(bpy, obj)
        modifier = obj.modifiers.new(modifier_name, "FLUID")
        if modifier is None:
            return skill_error(
                "Fluid modifier could not be created",
                f"Blender refused a FLUID modifier on {object_name}; the object may already "
                "have one or lack mesh data. No modifier was added.",
            )
        modifier.fluid_type = wanted

        applied, skipped = _apply_settings(modifier, settings, FLUID_NUMERIC_SETTINGS)
        context = _modifier_context(modifier)
        context["fluid_type"] = wanted
        return skill_success(
            f"Added {wanted} fluid modifier on {object_name}"
            + _unapplied_note(skipped, getattr(bpy.app, "version_string", None)),
            object_name=object_name,
            modifier=context,
            fluid_type=wanted,
            applied=applied,
            not_applied=list(skipped),
            skipped=list(skipped),
            prompt="Use set_fluid_settings to tune domain options, then bake_simulation.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to add fluid modifier to {object_name}")


def set_fluid_settings(
    object_name: str,
    modifier_name: Optional[str] = None,
    settings: Optional[Dict[str, Any]] = None,
    domain_settings: Optional[Dict[str, Any]] = None,
) -> dict:
    """Update Mantaflow fluid settings.

    Args:
        object_name: Mesh object owning the fluid modifier.
        modifier_name: Fluid modifier name; defaults to the first one.
        settings: Properties on the FLUID modifier itself. A FluidModifier only
            exposes ``fluid_type`` and the three settings blocks, so the usual
            Mantaflow knobs (resolution, viscosity, noise, time scale) are not
            valid here; pass them in ``domain_settings``. Asking for one here
            fails with that hint instead of being skipped.
        domain_settings: Properties applied to ``modifier.domain_settings``,
            where Mantaflow keeps resolution, viscosity, noise, and mesh options.
    """
    if not settings and not domain_settings:
        return skill_error(
            "No fluid settings supplied",
            "Provide settings and/or domain_settings; use list_simulation_modifiers to inspect modifiers.",
        )
    try:
        import bpy

        obj = _object_named(bpy, object_name)
        if obj is None:
            return skill_error(f"Object not found: {object_name}", f"No object named '{object_name}'.")
        modifier = _find_modifier(obj, modifier_name, "FLUID")
        if modifier is None:
            label = modifier_name or "FLUID"
            return skill_error(f"Fluid modifier not found: {label}", f"{object_name} has no matching fluid modifier.")

        # Preflight both targets before writing: applying `settings` first and
        # then rejecting `domain_settings` would leave a half-applied modifier.
        domain = getattr(modifier, "domain_settings", None)
        if domain_settings and domain is None:
            return skill_error(
                "Fluid domain settings unavailable",
                "domain_settings are only exposed on a DOMAIN fluid modifier. Nothing was changed.",
            )

        applied, skipped = _apply_settings(modifier, settings, FLUID_NUMERIC_SETTINGS)
        # Domain-only names sent to `settings` would be skipped and still
        # reported as a success, which is how a wrong route went unnoticed.
        # Point the caller at the argument that can serve them. This is a hint,
        # not an allowlist: anything else unknown still skips.
        misrouted = [
            key for key in skipped if domain is not None and hasattr(domain, key) and not hasattr(modifier, key)
        ]
        if misrouted:
            return skill_error(
                "Fluid settings belong on the domain block",
                f"{', '.join(sorted(misrouted))} not found on the FLUID modifier but present on "
                "modifier.domain_settings; pass them in domain_settings instead. Nothing was changed.",
            )

        domain_applied: Dict[str, Any] = {}
        if domain_settings:
            domain_applied, domain_skipped = _apply_settings(domain, domain_settings, FLUID_NUMERIC_SETTINGS)
            skipped = [*skipped, *domain_skipped]

        context = _modifier_context(modifier)
        context["fluid_type"] = getattr(modifier, "fluid_type", None)
        return skill_success(
            f"Updated fluid settings on {object_name}"
            + _unapplied_note(skipped, getattr(bpy.app, "version_string", None)),
            object_name=object_name,
            modifier=context,
            applied=applied,
            domain_applied=domain_applied,
            not_applied=list(skipped),
            skipped=list(skipped),
            prompt="Use bake_simulation to cache the result.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to update fluid settings on {object_name}")


def _dynamic_paint_target(modifier: Any, ui_type: str) -> Any:
    """Return the canvas or brush settings block for a Dynamic Paint modifier."""
    if ui_type == "BRUSH":
        return getattr(modifier, "brush_settings", None)
    return getattr(modifier, "canvas_settings", None)


def _dynamic_paint_canvas(modifier: Any) -> Any:
    return getattr(modifier, "canvas_settings", None)


def _dynamic_paint_surface_context(surface: Any) -> Dict[str, Any]:
    return {
        "name": getattr(surface, "name", ""),
        "surface_type": getattr(surface, "surface_type", None),
        "is_active": bool(getattr(surface, "is_active", True)),
        "use_dry_log": bool(getattr(surface, "use_dry_log", False)),
        "use_wet_log": bool(getattr(surface, "use_wet_log", False)),
    }


def add_dynamic_paint_modifier(
    object_name: str,
    paint_type: str = "CANVAS",
    name: Optional[str] = None,
    settings: Optional[Dict[str, Any]] = None,
) -> dict:
    """Add a Dynamic Paint modifier configured as a canvas or a brush.

    Args:
        object_name: Mesh object that receives the modifier.
        paint_type: ``CANVAS`` (receives paint) or ``BRUSH`` (emits paint).
        name: Modifier name; defaults to the paint type.
        settings: Modifier-level properties.
    """
    wanted = str(paint_type or "").upper()
    if wanted not in DYNAMIC_PAINT_TYPES:
        return skill_error(
            f"Unsupported dynamic paint type: {paint_type}",
            f"Supported types: {', '.join(DYNAMIC_PAINT_TYPES)}.",
        )
    try:
        import bpy

        obj = _object_named(bpy, object_name)
        if obj is None:
            return skill_error(f"Object not found: {object_name}", f"No object named '{object_name}'.")
        if getattr(obj, "type", None) != "MESH":
            return skill_error(f"{object_name} is not a mesh", "Dynamic Paint modifiers require a mesh object.")

        modifier_name = name or f"Dynamic Paint {wanted.title()}"
        _activate_object(bpy, obj)
        modifier = obj.modifiers.new(modifier_name, "DYNAMIC_PAINT")
        modifier.ui_type = wanted

        applied, skipped = _apply_settings(
            _dynamic_paint_target(modifier, wanted), settings, DYNAMIC_PAINT_NUMERIC_SETTINGS
        )
        context = _modifier_context(modifier)
        context["ui_type"] = wanted
        return skill_success(
            f"Added Dynamic Paint {wanted} modifier on {object_name}"
            + _unapplied_note(skipped, getattr(bpy.app, "version_string", None)),
            object_name=object_name,
            modifier=context,
            paint_type=wanted,
            applied=applied,
            not_applied=list(skipped),
            skipped=list(skipped),
            prompt=(
                "Use add_dynamic_paint_surface to add a canvas surface."
                if wanted == "CANVAS"
                else "Tune the brush alpha and radius, then run bake_simulation on the canvas."
            ),
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to add Dynamic Paint modifier to {object_name}")


def set_dynamic_paint_settings(
    object_name: str,
    modifier_name: Optional[str] = None,
    settings: Optional[Dict[str, Any]] = None,
) -> dict:
    """Update canvas or brush settings on a Dynamic Paint modifier.

    Args:
        object_name: Mesh object owning the modifier.
        modifier_name: Dynamic Paint modifier name; defaults to the first one.
        settings: Properties applied to the canvas or brush settings block.
    """
    if not settings:
        return skill_error(
            "No dynamic paint settings supplied",
            "Provide settings; use list_simulation_modifiers to inspect modifiers.",
        )
    try:
        import bpy

        obj = _object_named(bpy, object_name)
        if obj is None:
            return skill_error(f"Object not found: {object_name}", f"No object named '{object_name}'.")
        modifier = _find_modifier(obj, modifier_name, "DYNAMIC_PAINT")
        if modifier is None:
            label = modifier_name or "DYNAMIC_PAINT"
            return skill_error(
                f"Dynamic Paint modifier not found: {label}",
                f"{object_name} has no matching Dynamic Paint modifier.",
            )

        ui_type = str(getattr(modifier, "ui_type", "") or "").upper()
        target = _dynamic_paint_target(modifier, ui_type)
        if target is None:
            return skill_error(
                "Dynamic Paint settings unavailable",
                f"The modifier exposes no {ui_type or 'canvas/brush'} settings block.",
            )
        applied, skipped = _apply_settings(target, settings, DYNAMIC_PAINT_NUMERIC_SETTINGS)
        context = _modifier_context(modifier)
        context["ui_type"] = ui_type
        return skill_success(
            f"Updated Dynamic Paint settings on {object_name}"
            + _unapplied_note(skipped, getattr(bpy.app, "version_string", None)),
            object_name=object_name,
            modifier=context,
            paint_type=ui_type,
            applied=applied,
            not_applied=list(skipped),
            skipped=list(skipped),
            prompt="Use bake_simulation to cache the result.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to update Dynamic Paint settings on {object_name}")


def add_dynamic_paint_surface(
    object_name: str,
    surface_type: str = "PAINT",
    name: Optional[str] = None,
    modifier_name: Optional[str] = None,
    settings: Optional[Dict[str, Any]] = None,
) -> dict:
    """Add a surface to a Dynamic Paint canvas modifier.

    Args:
        object_name: Mesh object owning the canvas modifier.
        surface_type: ``PAINT``, ``DISPLACE``, ``WEIGHT``, or ``WAVE``.
        name: Surface name; defaults to the surface type.
        modifier_name: Canvas modifier name; defaults to the first one.
        settings: Surface properties, for example ``use_dry_log``.
    """
    wanted = str(surface_type or "").upper()
    if wanted not in DYNAMIC_PAINT_SURFACE_TYPES:
        return skill_error(
            f"Unsupported dynamic paint surface: {surface_type}",
            f"Supported surfaces: {', '.join(DYNAMIC_PAINT_SURFACE_TYPES)}.",
        )
    try:
        import bpy

        obj = _object_named(bpy, object_name)
        if obj is None:
            return skill_error(f"Object not found: {object_name}", f"No object named '{object_name}'.")
        label = modifier_name or "DYNAMIC_PAINT"
        modifier = _find_modifier(obj, modifier_name, "DYNAMIC_PAINT")
        if modifier is None:
            return skill_error(
                f"Dynamic Paint modifier not found: {label}",
                f"{object_name} has no matching Dynamic Paint modifier.",
            )
        ui_type = str(getattr(modifier, "ui_type", "") or "").upper()
        if ui_type and ui_type != "CANVAS":
            return skill_error(
                "Modifier is not a Dynamic Paint canvas",
                f"Modifier {getattr(modifier, 'name', label)} has ui_type {ui_type}; surfaces require a CANVAS.",
            )
        canvas = _dynamic_paint_canvas(modifier)
        surfaces = getattr(canvas, "canvas_surfaces", None)
        if surfaces is None or not callable(getattr(surfaces, "new", None)):
            # Blender documents bpy.ops.dpaint.surface_slot_add() for adding a
            # surface; the RNA collection may or may not expose .new() depending
            # on the build. Say which path failed so the caller can report it
            # accurately instead of guessing.
            return skill_error(
                "Dynamic Paint surfaces unavailable",
                "canvas_settings.canvas_surfaces.new() is not exposed by this Blender build, "
                "so surfaces cannot be added from Python here. Add the surface in the UI or "
                "through bpy.ops.dpaint.surface_slot_add(), then use set_dynamic_paint_settings "
                "and list_dynamic_paint_surfaces.",
            )

        surface_name = name or f"{wanted.title()} Surface"
        getter = getattr(surfaces, "get", None)
        existing = getter(surface_name) if callable(getter) else None
        created = False
        if existing is None:
            try:
                existing = surfaces.new()
            except TypeError:
                existing = surfaces.new(surface_name)
            created = True
        try:
            existing.name = surface_name
        except Exception:  # pragma: no cover - read-only name in exotic builds
            pass
        try:
            existing.surface_type = wanted
        except Exception:  # pragma: no cover - surface_type unsupported in this build
            pass

        applied, skipped = _apply_settings(existing, settings, DYNAMIC_PAINT_NUMERIC_SETTINGS)
        return skill_success(
            f"{'Added' if created else 'Updated'} Dynamic Paint {wanted} surface on {object_name}"
            + _unapplied_note(skipped, getattr(bpy.app, "version_string", None)),
            object_name=object_name,
            modifier_name=getattr(modifier, "name", None),
            surface=_dynamic_paint_surface_context(existing),
            created=created,
            applied=applied,
            not_applied=list(skipped),
            skipped=list(skipped),
            prompt="Use list_dynamic_paint_surfaces to review the canvas, then bake_simulation.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to add Dynamic Paint surface to {object_name}")


def list_dynamic_paint_surfaces(object_name: str, modifier_name: Optional[str] = None) -> dict:
    """List the surfaces configured on Dynamic Paint canvas modifiers."""
    try:
        import bpy

        obj = _object_named(bpy, object_name)
        if obj is None:
            return skill_error(f"Object not found: {object_name}", f"No object named '{object_name}'.")

        entries: List[Dict[str, Any]] = []
        for modifier in getattr(obj, "modifiers", []) or []:
            if getattr(modifier, "type", None) != "DYNAMIC_PAINT":
                continue
            if modifier_name and getattr(modifier, "name", None) != modifier_name:
                continue
            if str(getattr(modifier, "ui_type", "") or "").upper() != "CANVAS":
                continue
            canvas = _dynamic_paint_canvas(modifier)
            for surface in getattr(canvas, "canvas_surfaces", []) or []:
                item = _dynamic_paint_surface_context(surface)
                item["modifier_name"] = getattr(modifier, "name", "")
                entries.append(item)
        return skill_success(
            f"Found {len(entries)} Dynamic Paint surface(s) on {object_name}",
            object_name=object_name,
            count=len(entries),
            surfaces=entries,
            prompt="Use add_dynamic_paint_surface or set_dynamic_paint_settings to adjust the canvas.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to list Dynamic Paint surfaces on {object_name}")


# ---------------------------------------------------------------------------
# Particle hair, children, instancing, and baking
# ---------------------------------------------------------------------------

PARTICLE_TYPES = ("EMITTER", "HAIR")
# ParticleSettings.child_type enum; FACES is a render/child distribution option
# in the UI, not a child_type value.
CHILD_TYPES = ("NONE", "SIMPLE", "INTERPOLATED")


def _find_particle_system(obj: Any, system_name: Optional[str]) -> Tuple[Any, Optional[dict]]:
    """Resolve the first (or named) particle system modifier on an object."""
    for modifier in getattr(obj, "modifiers", []) or []:
        if getattr(modifier, "type", None) != "PARTICLE_SYSTEM":
            continue
        system = getattr(modifier, "particle_system", None)
        names = {getattr(system, "name", None), getattr(modifier, "name", None)}
        if system_name and system_name not in names:
            continue
        return modifier, None
    label = system_name or "PARTICLE_SYSTEM"
    return None, skill_error(
        f"Particle system not found: {label}", f"{getattr(obj, 'name', '')} has no matching particle system."
    )


def set_particle_hair(
    object_name: str,
    system_name: Optional[str] = None,
    enabled: bool = True,
    settings: Optional[Dict[str, Any]] = None,
) -> dict:
    """Switch a particle system between emitter and hair mode.

    Args:
        object_name: Mesh object owning the particle system.
        system_name: Particle system name; defaults to the first one.
        enabled: ``True`` selects hair mode, ``False`` restores emitter mode.
        settings: Hair properties such as ``hair_length`` or ``hair_step``.
    """
    try:
        import bpy

        obj = _object_named(bpy, object_name)
        if obj is None:
            return skill_error(f"Object not found: {object_name}", f"No object named '{object_name}'.")
        modifier, error = _find_particle_system(obj, system_name)
        if error:
            return error
        psettings = getattr(getattr(modifier, "particle_system", None), "settings", None)
        if psettings is None:
            return skill_error("Particle settings unavailable", "The modifier exposes no particle settings.")
        if not hasattr(psettings, "type"):
            return skill_error(
                "Particle type unavailable",
                "particle settings expose no 'type' property in this Blender build.",
            )

        wanted = "HAIR" if enabled else "EMITTER"
        psettings.type = wanted
        applied, skipped = _apply_settings(psettings, settings, PARTICLE_HAIR_NUMERIC_SETTINGS)
        return skill_success(
            f"Set particle system to {wanted} on {object_name}"
            + _unapplied_note(skipped, getattr(bpy.app, "version_string", None)),
            object_name=object_name,
            system_name=getattr(getattr(modifier, "particle_system", None), "name", None),
            type=wanted,
            applied=applied,
            not_applied=list(skipped),
            skipped=list(skipped),
            prompt="Use set_particle_children for child strands, then bake_particle_system.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to set particle hair mode on {object_name}")


def set_particle_children(
    object_name: str,
    system_name: Optional[str] = None,
    child_type: Optional[str] = None,
    child_nbr: Optional[int] = None,
    rendered_child_count: Optional[int] = None,
    settings: Optional[Dict[str, Any]] = None,
) -> dict:
    """Configure child particles (interpolated strands) on a particle system.

    Args:
        object_name: Mesh object owning the particle system.
        system_name: Particle system name; defaults to the first one.
        child_type: ``NONE``, ``SIMPLE``, or ``INTERPOLATED``. ``FACES`` is a
            child distribution option in the UI, not a ``child_type`` member.
        child_nbr: Display amount of children per parent. Only present on
            Blender 3.x; 4.x removed it. Caps at 10000 where available.
        rendered_child_count: Amount of children actually rendered. This is the
            property to use: live RNA confirms it on every version from 3.6.5
            to 5.2.1. It is not the same knob as ``child_nbr`` (display vs
            render), so the two are never substituted for one another.
        settings: Extra child properties such as ``child_length``.
    """
    if child_type is not None and str(child_type).upper() not in CHILD_TYPES:
        return skill_error(
            f"Unsupported child type: {child_type}",
            f"Supported child types: {', '.join(CHILD_TYPES)}.",
        )
    if child_nbr is not None and not 0 <= int(child_nbr) <= 10000:
        return skill_error("Invalid child count", "child_nbr must be between 0 and 10000.")
    if rendered_child_count is not None and int(rendered_child_count) < 0:
        return skill_error("Invalid rendered child count", "rendered_child_count must not be negative.")
    if child_type is None and child_nbr is None and rendered_child_count is None and not settings:
        return skill_error(
            "No child settings supplied",
            "Provide child_type, child_nbr, rendered_child_count, and/or settings.",
        )
    try:
        import bpy

        obj = _object_named(bpy, object_name)
        if obj is None:
            return skill_error(f"Object not found: {object_name}", f"No object named '{object_name}'.")
        modifier, error = _find_particle_system(obj, system_name)
        if error:
            return error
        psettings = getattr(getattr(modifier, "particle_system", None), "settings", None)
        if psettings is None:
            return skill_error("Particle settings unavailable", "The modifier exposes no particle settings.")

        applied: Dict[str, Any] = {}
        skipped: List[str] = []
        for key, value in (
            ("child_type", str(child_type).upper() if child_type is not None else None),
            ("rendered_child_count", int(rendered_child_count) if rendered_child_count is not None else None),
        ):
            if value is None:
                continue
            if not hasattr(psettings, key):
                skipped.append(key)
                continue
            setattr(psettings, key, value)
            applied[key] = value

        # child_nbr is the display amount and only exists on Blender 3.x. It is
        # deliberately not mapped onto rendered_child_count: they are different
        # knobs, and silently writing one for the other is how this batch got
        # here. Say so instead.
        if child_nbr is not None:
            if hasattr(psettings, "child_nbr"):
                psettings.child_nbr = int(child_nbr)
                applied["child_nbr"] = int(child_nbr)
            else:
                return skill_error(
                    "child_nbr is not available in this Blender version",
                    "Blender 4.x removed ParticleSettings.child_nbr (display amount). "
                    "Use rendered_child_count, which controls the rendered amount and "
                    "exists on every supported version. Nothing was changed.",
                )

        extra_applied, extra_skipped = _apply_settings(psettings, settings, PARTICLE_HAIR_NUMERIC_SETTINGS)
        applied.update(extra_applied)
        skipped.extend(extra_skipped)
        return skill_success(
            f"Updated children on {object_name}" + _unapplied_note(skipped, getattr(bpy.app, "version_string", None)),
            object_name=object_name,
            system_name=getattr(getattr(modifier, "particle_system", None), "name", None),
            applied=applied,
            not_applied=list(skipped),
            skipped=list(skipped),
            prompt="Use bake_particle_system to cache the strands.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to set particle children on {object_name}")


def set_particle_instance(
    object_name: str,
    system_name: Optional[str] = None,
    instance_object_name: Optional[str] = None,
    show_emitter: Optional[bool] = None,
    render_type: Optional[str] = None,
    particle_size: Optional[float] = None,
) -> dict:
    """Render an object for every particle.

    Args:
        object_name: Mesh object owning the particle system.
        system_name: Particle system name; defaults to the first one.
        instance_object_name: Object to instance; omit to keep the current one.
        show_emitter: Whether the source mesh renders alongside the instances.
        render_type: Blender render type, for example ``OBJECT`` or ``HALO``.
        particle_size: Size of each rendered particle.
    """
    if instance_object_name is None and show_emitter is None and render_type is None and particle_size is None:
        return skill_error(
            "No instance settings supplied",
            "Provide at least one of instance_object_name, show_emitter, render_type, particle_size.",
        )
    try:
        import bpy

        obj = _object_named(bpy, object_name)
        if obj is None:
            return skill_error(f"Object not found: {object_name}", f"No object named '{object_name}'.")
        instance_object, error = _resolve_particle_instance_object(bpy, instance_object_name)
        if error:
            return error
        modifier, error = _find_particle_system(obj, system_name)
        if error:
            return error
        psettings = getattr(getattr(modifier, "particle_system", None), "settings", None)
        if psettings is None:
            return skill_error("Particle settings unavailable", "The modifier exposes no particle settings.")

        applied, skipped = _apply_particle_render_options(
            obj, psettings, instance_object_name, instance_object, show_emitter
        )
        if render_type is not None:
            if hasattr(psettings, "render_type"):
                psettings.render_type = str(render_type).upper()
                applied["render_type"] = psettings.render_type
            else:
                skipped.append("render_type")
        if particle_size is not None:
            if hasattr(psettings, "particle_size"):
                psettings.particle_size = float(particle_size)
                applied["particle_size"] = psettings.particle_size
            else:
                skipped.append("particle_size")

        return skill_success(
            f"Updated instance rendering on {object_name}",
            object_name=object_name,
            system_name=getattr(getattr(modifier, "particle_system", None), "name", None),
            applied=applied,
            skipped=skipped,
            prompt="Use set_particle_children to add more instances, then bake_particle_system.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to set particle instancing on {object_name}")


def bake_particle_system(
    object_name: str,
    system_name: Optional[str] = None,
    frame_start: Optional[int] = None,
    frame_end: Optional[int] = None,
    free: bool = False,
) -> dict:
    """Bake or free the point cache of one particle system.

    Args:
        object_name: Mesh object owning the particle system.
        system_name: Particle system name; defaults to the first one.
        frame_start: First cached frame; defaults to the current cache start.
        frame_end: Last cached frame; defaults to the current cache end.
        free: ``True`` frees the cache instead of baking.
    """
    try:
        import bpy

        obj = _object_named(bpy, object_name)
        if obj is None:
            return skill_error(f"Object not found: {object_name}", f"No object named '{object_name}'.")
        modifier, error = _find_particle_system(obj, system_name)
        if error:
            return error
        cache = _modifier_point_cache(modifier)
        if cache is None:
            return skill_error(
                "Particle cache unavailable",
                "The particle system exposes no point cache in this Blender build.",
            )

        # The ptcache operator bakes the scene range, not the cache range, so
        # both have to move; setting only the cache silently bakes the whole
        # scene. Mirrors bake_simulation and bake_rigid_body_simulation.
        cache_changes = _set_cache_frames(cache, frame_start, frame_end)
        scene_changes = _set_scene_frames(bpy.context.scene, frame_start, frame_end)
        _activate_object(bpy, obj)
        try:
            override = {"scene": bpy.context.scene, "active_object": obj, "object": obj, "point_cache": cache}
            with bpy.context.temp_override(**override):
                result = bpy.ops.ptcache.free_bake() if free else bpy.ops.ptcache.bake(bake=True)
        except Exception as exc:
            return skill_exception(
                exc,
                message=f"Failed to {'free' if free else 'bake'} the particle cache",
                cache_changes=cache_changes,
                scene_changes=scene_changes,
                cache=_cache_context(cache),
            )

        # Blender operators report cancellation through their return set, not by
        # raising, so a CANCELLED bake has to be surfaced as a failure.
        operator_result = sorted(result) if result else []
        if set(result or ()) != {"FINISHED"}:
            return skill_error(
                f"Particle cache {'free' if free else 'bake'} did not finish",
                f"The Blender operator returned {operator_result or 'nothing'}; "
                f"{'free' if free else 'bake'} was cancelled or unsupported for this cache.",
                cache_changes=cache_changes,
                scene_changes=scene_changes,
                cache=_cache_context(cache),
            )

        return skill_success(
            f"{'Freed' if free else 'Baked'} particle cache on {object_name}",
            object_name=object_name,
            system_name=getattr(getattr(modifier, "particle_system", None), "name", None),
            freed=bool(free),
            operator_result=operator_result,
            cache=_cache_context(cache),
            cache_changes=cache_changes,
            scene_changes=scene_changes,
            prompt="Use get_simulation_status to confirm cache state.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to bake the particle cache on {object_name}")
