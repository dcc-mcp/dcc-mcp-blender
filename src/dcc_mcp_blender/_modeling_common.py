"""Shared validation, selection, and readback helpers for typed modeling verbs."""

from __future__ import annotations

import math
from typing import Any, List, Optional, Sequence, Tuple

from dcc_mcp_core.skill import skill_error, skill_success

AXIS_INDEX = {"x": 0, "y": 1, "z": 2}


def vector(
    value: Sequence[float], label: str, *, positive: bool = False
) -> Tuple[Optional[List[float]], Optional[dict]]:
    if isinstance(value, (str, bytes)) or len(value) != 3:
        return None, skill_error(f"Invalid {label}", f"{label} must contain exactly three numbers.")
    try:
        result = [float(component) for component in value]
    except (TypeError, ValueError):
        return None, skill_error(f"Invalid {label}", f"{label} must contain exactly three numbers.")
    if any(not math.isfinite(component) or abs(component) > 1_000_000 for component in result):
        return None, skill_error(f"Invalid {label}", f"{label} components must be finite and within +/-1000000.")
    if positive and any(component <= 0 for component in result):
        return None, skill_error(f"Invalid {label}", f"{label} components must be greater than zero.")
    return result, None


def coords(value: Any) -> List[float]:
    return [float(component) for component in value]


def close(left: Sequence[float], right: Sequence[float], tolerance: float = 1e-5) -> bool:
    return len(left) == len(right) and all(abs(float(a) - float(b)) <= tolerance for a, b in zip(left, right))


def active_object(bpy: Any) -> Any:
    return (
        getattr(bpy.context, "active_object", None)
        or getattr(bpy.context, "object", None)
        or getattr(getattr(getattr(bpy.context, "view_layer", None), "objects", None), "active", None)
    )


def mesh_object(bpy: Any, object_name: str) -> Tuple[Optional[Any], Optional[dict]]:
    obj = bpy.data.objects.get(object_name)
    if obj is None:
        return None, skill_error(f"Object not found: {object_name}", f"No object named '{object_name}'.")
    if getattr(obj, "type", None) != "MESH":
        return None, skill_error(f"{object_name} is not a mesh", "Modeling verbs require a MESH object.")
    return obj, None


def mesh_counts(obj: Any) -> dict:
    mesh = obj.data
    return {
        "vertex_count": len(getattr(mesh, "vertices", [])),
        "edge_count": len(getattr(mesh, "edges", [])),
        "face_count": len(getattr(mesh, "polygons", [])),
    }


def bounded_indices(values: Sequence[int], label: str, available: int) -> Tuple[Optional[List[int]], Optional[dict]]:
    if isinstance(values, (str, bytes)) or not values or len(values) > 4096:
        return None, skill_error(f"Invalid {label}", f"Provide between 1 and 4096 {label}.")
    if any(not isinstance(value, int) or isinstance(value, bool) or value < 0 for value in values):
        return None, skill_error(f"Invalid {label}", f"Every {label.rstrip('s')} must be a non-negative integer.")
    selected = sorted(set(int(value) for value in values))
    invalid = [value for value in selected if value >= available]
    if invalid:
        return None, skill_error(f"Invalid {label}", f"Out-of-range indices: {invalid}")
    return selected, None


def object_mode(bpy: Any) -> None:
    try:
        bpy.ops.object.mode_set(mode="OBJECT")
    except Exception:
        pass


def select_object(bpy: Any, obj: Any) -> None:
    object_mode(bpy)
    try:
        bpy.ops.object.select_all(action="DESELECT")
    except Exception:
        pass
    select_set = getattr(obj, "select_set", None)
    if callable(select_set):
        select_set(True)
    bpy.context.view_layer.objects.active = obj


def select_components(bpy: Any, obj: Any, component: str, indices: Sequence[int]) -> None:
    select_object(bpy, obj)
    for item in getattr(obj.data, "vertices", []):
        item.select = False
    for item in getattr(obj.data, "edges", []):
        item.select = False
    for item in getattr(obj.data, "polygons", []):
        item.select = False
    elements = getattr(obj.data, component)
    selected = set(indices)
    for fallback, item in enumerate(elements):
        item.select = int(getattr(item, "index", fallback)) in selected
    bpy.ops.object.mode_set(mode="EDIT")
    select_mode = getattr(bpy.ops.mesh, "select_mode", None)
    if callable(select_mode):
        select_mode(type={"edges": "EDGE", "polygons": "FACE"}[component])


def topology_result(
    operation: str,
    obj: Any,
    parameters: dict,
    before: dict,
    after: dict,
    changed_key: str,
) -> dict:
    if after[changed_key] <= before[changed_key]:
        return skill_error(
            f"{operation} had no verifiable effect on {obj.name}",
            f"Blender reported no increase in {changed_key.replace('_', ' ')}.",
        )
    return skill_success(
        f"{operation} completed on {obj.name}",
        object_name=obj.name,
        parameters=parameters,
        readback={"verified": True, "before": before, "after": after},
        prompt="Use get_poly_count to inspect the updated topology.",
    )


def duplicate_mesh(bpy: Any, source: Any, name: str) -> Any:
    duplicate = source.copy()
    duplicate.data = source.data.copy()
    duplicate.name = name
    duplicate.data.name = name
    clear_animation = getattr(duplicate, "animation_data_clear", None)
    if callable(clear_animation):
        clear_animation()
    bpy.context.collection.objects.link(duplicate)
    return duplicate


def remove_object(bpy: Any, obj: Any) -> None:
    try:
        bpy.data.objects.remove(obj, do_unlink=True)
    except Exception:
        pass


def object_mode_if_available() -> None:
    try:
        import bpy

        object_mode(bpy)
    except Exception:
        pass
