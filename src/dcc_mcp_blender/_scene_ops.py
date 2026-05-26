"""Shared implementations for Blender object and scene operation tools."""

from __future__ import annotations

import fnmatch
from typing import Any, Iterable, Sequence

from dcc_mcp_core.skill import skill_error, skill_exception, skill_success

_SELECTION_MODES = {"replace", "add", "remove", "toggle"}
_ORIGIN_MODES = {
    "geometry": ("ORIGIN_GEOMETRY", "MEDIAN"),
    "bounds": ("ORIGIN_GEOMETRY", "BOUNDS"),
    "cursor": ("ORIGIN_CURSOR", "MEDIAN"),
    "center_of_mass": ("ORIGIN_CENTER_OF_MASS", "MEDIAN"),
    "volume": ("ORIGIN_CENTER_OF_VOLUME", "MEDIAN"),
}


def _object_by_name(bpy: Any, object_name: str) -> tuple[Any | None, dict | None]:
    obj = bpy.data.objects.get(object_name)
    if obj is None:
        return None, skill_error(f"Object not found: {object_name}", f"No object named '{object_name}'.")
    return obj, None


def _objects_by_name(bpy: Any, object_names: Sequence[str]) -> tuple[list[Any], list[str]]:
    objects = []
    missing = []
    for name in object_names:
        obj = bpy.data.objects.get(name)
        if obj is None:
            missing.append(name)
        else:
            objects.append(obj)
    return objects, missing


def _validate_object_names(object_names: Sequence[str]) -> dict | None:
    if not isinstance(object_names, Sequence) or isinstance(object_names, str) or not object_names:
        return skill_error("Invalid object_names", "object_names must be a non-empty list of object names.")
    if any(not isinstance(name, str) or not name.strip() for name in object_names):
        return skill_error("Invalid object_names", "Every object name must be a non-empty string.")
    return None


def _selected_objects(bpy: Any) -> list[Any]:
    selected = getattr(bpy.context, "selected_objects", None)
    if selected is not None:
        return list(selected)
    return [obj for obj in bpy.data.objects if getattr(obj, "select_get", lambda: False)()]


def _active_object_name(bpy: Any) -> str | None:
    active = (
        getattr(bpy.context, "active_object", None)
        or getattr(bpy.context, "object", None)
        or getattr(getattr(getattr(bpy.context, "view_layer", None), "objects", None), "active", None)
    )
    return getattr(active, "name", None)


def _set_active(bpy: Any, obj: Any) -> None:
    bpy.context.view_layer.objects.active = obj
    try:
        bpy.context.active_object = obj
    except Exception:
        pass


def _clear_selection(bpy: Any) -> None:
    ops = getattr(bpy, "ops", None)
    op = getattr(getattr(ops, "object", None), "select_all", None)
    if callable(op):
        try:
            op(action="DESELECT")
            return
        except Exception:
            pass
    for obj in bpy.data.objects:
        select_set = getattr(obj, "select_set", None)
        if callable(select_set):
            select_set(False)


def _select(obj: Any, state: bool) -> None:
    select_set = getattr(obj, "select_set", None)
    if callable(select_set):
        select_set(state)


def _select_get(obj: Any) -> bool:
    select_get = getattr(obj, "select_get", None)
    if callable(select_get):
        return bool(select_get())
    return False


def get_selection() -> dict:
    """Return the current object selection."""
    try:
        import bpy

        selected = _selected_objects(bpy)
        return skill_success(
            f"Selected objects: {len(selected)}",
            selected=[obj.name for obj in selected],
            active_object=_active_object_name(bpy),
            count=len(selected),
            prompt="Use set_selection, select_by_type, or find_by_pattern to change the selection.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message="Failed to get Blender selection")


def set_selection(object_names: Sequence[str], mode: str = "replace") -> dict:
    """Set or adjust the selected object set."""
    names_error = _validate_object_names(object_names)
    if names_error:
        return names_error
    mode_key = mode.lower()
    if mode_key not in _SELECTION_MODES:
        return skill_error("Invalid selection mode", f"Use one of: {', '.join(sorted(_SELECTION_MODES))}.")

    try:
        import bpy

        objects, missing = _objects_by_name(bpy, object_names)
        if missing:
            return skill_error("Object not found", f"Missing object(s): {', '.join(missing)}")
        if mode_key == "replace":
            _clear_selection(bpy)
        for obj in objects:
            if mode_key in {"replace", "add"}:
                _select(obj, True)
            elif mode_key == "remove":
                _select(obj, False)
            else:
                _select(obj, not _select_get(obj))
        if objects:
            _set_active(bpy, objects[-1])

        selected = _selected_objects(bpy)
        return skill_success(
            f"Selection updated: {len(selected)} object(s)",
            mode=mode_key,
            requested=list(object_names),
            selected=[obj.name for obj in selected],
            active_object=_active_object_name(bpy),
            count=len(selected),
            prompt="Use get_selection to inspect or object tools to act on the selection.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message="Failed to set Blender selection")


def select_by_type(type: str) -> dict:  # noqa: A002
    """Select objects matching a Blender object type."""
    type_key = type.upper()
    try:
        import bpy

        matches = [obj for obj in bpy.data.objects if getattr(obj, "type", "").upper() == type_key]
        _clear_selection(bpy)
        for obj in matches:
            _select(obj, True)
        if matches:
            _set_active(bpy, matches[0])
        return skill_success(
            f"Selected {len(matches)} object(s) of type {type_key}",
            type=type_key,
            selected=[obj.name for obj in matches],
            count=len(matches),
            active_object=_active_object_name(bpy),
            prompt="Use get_selection to inspect the selected objects.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to select objects by type {type}")


def find_by_pattern(pattern: str, type: str | None = None) -> dict:  # noqa: A002
    """Find objects by shell-style name pattern and optional type."""
    if not pattern:
        return skill_error("Invalid pattern", "pattern must be a non-empty string.")
    type_key = type.upper() if type else None
    try:
        import bpy

        matches = [
            obj
            for obj in bpy.data.objects
            if fnmatch.fnmatchcase(obj.name, pattern)
            and (type_key is None or getattr(obj, "type", "").upper() == type_key)
        ]
        return skill_success(
            f"Found {len(matches)} object(s) matching {pattern}",
            pattern=pattern,
            type=type_key,
            objects=[{"name": obj.name, "type": getattr(obj, "type", "")} for obj in matches],
            count=len(matches),
            prompt="Use set_selection with the returned names to select matches.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to find objects by pattern {pattern}")


def rename_object(object_name: str, new_name: str) -> dict:
    """Rename a Blender object."""
    if not new_name or not new_name.strip():
        return skill_error("Invalid new_name", "new_name must be a non-empty string.")
    try:
        import bpy

        obj, error = _object_by_name(bpy, object_name)
        if error:
            return error
        old_name = obj.name
        obj.name = new_name
        if getattr(obj, "data", None) is not None and getattr(obj.data, "name", None) == old_name:
            obj.data.name = new_name
        return skill_success(
            f"Renamed {old_name} to {obj.name}",
            old_name=old_name,
            new_name=obj.name,
            data_name=getattr(getattr(obj, "data", None), "name", None),
            prompt="Use get_object_info or find_by_pattern to inspect the renamed object.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to rename {object_name}")


def parent_object(child_name: str, parent_name: str | None = None) -> dict:
    """Parent or unparent an object while preserving its world transform."""
    try:
        import bpy

        child, error = _object_by_name(bpy, child_name)
        if error:
            return error
        parent = None
        if parent_name:
            parent, error = _object_by_name(bpy, parent_name)
            if error:
                return error
            if parent is child:
                return skill_error("Invalid parent", "An object cannot be parented to itself.")

        matrix_world = getattr(child, "matrix_world", None)
        child.parent = parent
        if matrix_world is not None:
            try:
                child.matrix_world = matrix_world
            except Exception:
                pass
        return skill_success(
            f"Parent updated for {child.name}",
            child_name=child.name,
            parent_name=getattr(parent, "name", None),
            prompt="Use get_bounding_box or get_object_info to verify the resulting transform.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to parent {child_name}")


def group_objects(object_names: Sequence[str], collection_name: str | None = None) -> dict:
    """Link objects into a collection."""
    names_error = _validate_object_names(object_names)
    if names_error:
        return names_error
    try:
        import bpy

        objects, missing = _objects_by_name(bpy, object_names)
        if missing:
            return skill_error("Object not found", f"Missing object(s): {', '.join(missing)}")
        target_name = collection_name or "Group"
        collection = bpy.data.collections.get(target_name)
        created = False
        if collection is None:
            collection = bpy.data.collections.new(target_name)
            created = True
        try:
            bpy.context.scene.collection.children.link(collection)
        except Exception:
            pass
        linked = []
        for obj in objects:
            try:
                collection.objects.link(obj)
            except Exception:
                pass
            linked.append(obj.name)
        return skill_success(
            f"Grouped {len(linked)} object(s) into {collection.name}",
            collection_name=collection.name,
            created_collection=created,
            object_names=linked,
            count=len(linked),
            prompt="Use blender-collection list tools to inspect collection membership.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message="Failed to group objects")


def set_visibility(
    object_name: str,
    visible: bool,
    viewport: bool = True,
    render: bool = True,
) -> dict:
    """Set viewport and/or render visibility for an object."""
    try:
        import bpy

        obj, error = _object_by_name(bpy, object_name)
        if error:
            return error
        if viewport:
            obj.hide_viewport = not visible
            hide_set = getattr(obj, "hide_set", None)
            if callable(hide_set):
                hide_set(not visible)
        if render:
            obj.hide_render = not visible
        return skill_success(
            f"Visibility updated for {obj.name}",
            object_name=obj.name,
            visible=bool(visible),
            viewport=bool(viewport),
            render=bool(render),
            hide_viewport=getattr(obj, "hide_viewport", None),
            hide_render=getattr(obj, "hide_render", None),
            prompt="Use get_object_info or render tools to confirm the visibility state.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to set visibility for {object_name}")


def get_bounding_box(object_name: str, world_space: bool = True) -> dict:
    """Return an object's bounding box."""
    try:
        import bpy

        obj, error = _object_by_name(bpy, object_name)
        if error:
            return error
        corners = [_corner_to_world(obj, corner) if world_space else _coords(corner) for corner in obj.bound_box]
        mins = [min(corner[index] for corner in corners) for index in range(3)]
        maxs = [max(corner[index] for corner in corners) for index in range(3)]
        size = [maxs[index] - mins[index] for index in range(3)]
        center = [(mins[index] + maxs[index]) / 2 for index in range(3)]
        return skill_success(
            f"Bounding box for {obj.name}",
            object_name=obj.name,
            world_space=bool(world_space),
            min=mins,
            max=maxs,
            size=size,
            center=center,
            corners=corners,
            prompt="Use center_origin or transform tools if the bounds need adjustment.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to get bounding box for {object_name}")


def center_origin(object_name: str, mode: str = "geometry") -> dict:
    """Center or move an object's origin through Blender's origin operator."""
    mode_key = mode.lower()
    if mode_key not in _ORIGIN_MODES:
        return skill_error("Invalid origin mode", f"Use one of: {', '.join(sorted(_ORIGIN_MODES))}.")
    try:
        import bpy

        obj, error = _object_by_name(bpy, object_name)
        if error:
            return error
        _clear_selection(bpy)
        _select(obj, True)
        _set_active(bpy, obj)
        origin_type, center = _ORIGIN_MODES[mode_key]
        bpy.ops.object.origin_set(type=origin_type, center=center)
        return skill_success(
            f"Centered origin for {obj.name}",
            object_name=obj.name,
            mode=mode_key,
            prompt="Use get_bounding_box or get_object_info to verify the origin change.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to center origin for {object_name}")


def freeze_transforms(
    object_name: str,
    location: bool = False,
    rotation: bool = True,
    scale: bool = True,
) -> dict:
    """Apply object transforms into object data."""
    try:
        import bpy

        obj, error = _object_by_name(bpy, object_name)
        if error:
            return error
        _clear_selection(bpy)
        _select(obj, True)
        _set_active(bpy, obj)
        bpy.ops.object.transform_apply(location=bool(location), rotation=bool(rotation), scale=bool(scale))
        return skill_success(
            f"Froze transforms for {obj.name}",
            object_name=obj.name,
            applied={"location": bool(location), "rotation": bool(rotation), "scale": bool(scale)},
            prompt="Use get_object_info to inspect the applied transform.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to freeze transforms for {object_name}")


def _coords(value: Iterable[Any]) -> list[float]:
    return [float(coord) for coord in value]


def _corner_to_world(obj: Any, corner: Iterable[Any]) -> list[float]:
    coords = _coords(corner)
    matrix = getattr(obj, "matrix_world", None)
    if matrix is None:
        return coords
    try:
        result = matrix @ coords
    except Exception:
        try:
            from mathutils import Vector

            result = matrix @ Vector(coords)
        except Exception:
            return coords
    return _coords(result)
