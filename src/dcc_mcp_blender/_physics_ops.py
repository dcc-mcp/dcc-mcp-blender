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
