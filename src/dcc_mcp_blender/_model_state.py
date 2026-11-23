"""Normalized Blender modeling state for cross-DCC verification."""

from __future__ import annotations

import math
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from dcc_mcp_core.skill import skill_error, skill_exception, skill_success

from ._asset_pipeline_ops import _object_name, _objects, _objects_for_names

SCHEMA_NAME = "dcc-mcp/model-state"
SCHEMA_VERSION = 1
CHECK_NAMES = ("parts", "hierarchy", "materials", "uv_coverage", "non_manifold", "euler")


def _number(value: Any) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("value must be finite")
    return result


def _vector(value: Any, *, degrees: bool = False) -> List[float]:
    values = [_number(component) for component in value]
    if degrees:
        values = [math.degrees(component) for component in values]
    return values


def _hierarchy_path(obj: Any) -> str:
    names: List[str] = []
    visited: Set[int] = set()
    current = obj
    while current is not None:
        identity = id(current)
        if identity in visited:
            raise ValueError("object hierarchy contains a cycle")
        visited.add(identity)
        names.append(_object_name(current))
        current = getattr(current, "parent", None)
    return "/".join(reversed([name for name in names if name]))


def _bounds(obj: Any) -> Optional[Dict[str, Any]]:
    corners = getattr(obj, "bound_box", None)
    if not corners:
        return None
    matrix = getattr(obj, "matrix_world", None)
    points: List[List[float]] = []
    for corner in corners:
        point = corner
        if matrix is not None:
            try:
                from mathutils import Vector

                point = matrix @ Vector(corner)
            except (ImportError, TypeError, ValueError):
                point = corner
        points.append(_vector(point))
    return {
        "min": [min(point[index] for point in points) for index in range(3)],
        "max": [max(point[index] for point in points) for index in range(3)],
        "space": "world",
    }


def _material_names(obj: Any) -> List[str]:
    names: List[str] = []
    for slot in getattr(obj, "material_slots", []):
        material = getattr(slot, "material", None)
        name = str(getattr(material, "name", "")) if material is not None else ""
        if name:
            names.append(name)
    if names:
        return names
    for material in getattr(getattr(obj, "data", None), "materials", []):
        name = str(getattr(material, "name", ""))
        if name:
            names.append(name)
    return names


def _is_non_manifold(obj: Any) -> bool:
    import bmesh

    mesh = bmesh.new()
    try:
        mesh.from_mesh(obj.data)
        return any(not bool(edge.is_manifold) for edge in mesh.edges)
    finally:
        mesh.free()


def _mesh_state(obj: Any, unavailable: Set[str]) -> Tuple[Dict[str, Any], bool]:
    data = getattr(obj, "data", None)
    state: Dict[str, Any] = {
        "name": _object_name(obj),
        "uv_sets": 0,
        "material": None,
        "is_non_manifold": False,
        "vertex_count": 0,
    }
    partial = False

    try:
        state["uv_sets"] = len(getattr(data, "uv_layers", []))
    except Exception:
        unavailable.add("uv_coverage")
        partial = True
    try:
        materials = _material_names(obj)
        state["material"] = materials[0] if materials else None
        if len(materials) > 1:
            state["materials"] = materials
    except Exception:
        unavailable.add("materials")
        partial = True
    try:
        state["is_non_manifold"] = _is_non_manifold(obj)
    except Exception:
        unavailable.add("non_manifold")
        partial = True
    try:
        state["vertex_count"] = len(getattr(data, "vertices", []))
    except Exception:
        partial = True

    try:
        mesh_bounds = _bounds(obj)
    except Exception:
        mesh_bounds = None
        partial = True
    if mesh_bounds is not None:
        state["bounds"] = mesh_bounds
    return state, partial


def _object_state(obj: Any, unavailable: Set[str]) -> Tuple[Dict[str, Any], bool]:
    state: Dict[str, Any] = {"name": _object_name(obj), "transform": {}}
    partial = False
    try:
        state["transform"] = {
            "location": _vector(getattr(obj, "location", (0.0, 0.0, 0.0))),
            "rotation": _vector(getattr(obj, "rotation_euler", (0.0, 0.0, 0.0)), degrees=True),
            "scale": _vector(getattr(obj, "scale", (1.0, 1.0, 1.0))),
        }
        state["euler"] = state["transform"]["rotation"]
    except Exception:
        unavailable.add("euler")
        partial = True
    return state, partial


def _build_model_state(objects: Iterable[Any]) -> Dict[str, Any]:
    targets = list(objects)
    unavailable: Set[str] = set()
    partial = False
    parts: List[str] = []
    hierarchy: List[str] = []
    meshes: List[Dict[str, Any]] = []
    object_states: List[Dict[str, Any]] = []

    for obj in targets:
        name = _object_name(obj)
        if name:
            parts.append(name)
        try:
            hierarchy.append(_hierarchy_path(obj))
        except Exception:
            unavailable.add("hierarchy")
            partial = True
        object_state, object_partial = _object_state(obj, unavailable)
        object_states.append(object_state)
        partial = partial or object_partial
        if getattr(obj, "type", None) == "MESH":
            mesh_state, mesh_partial = _mesh_state(obj, unavailable)
            meshes.append(mesh_state)
            partial = partial or mesh_partial

    return {
        "schema_name": SCHEMA_NAME,
        "schema_version": SCHEMA_VERSION,
        "partial": partial,
        "unavailable": sorted(unavailable),
        "parts": parts,
        "hierarchy": hierarchy,
        "meshes": meshes,
        "objects": object_states,
    }


def export_model_state(object_names: Optional[List[str]] = None) -> dict:
    """Export bounded modeling state for the whole scene or named objects."""
    try:
        import bpy

        if object_names:
            objects, issues = _objects_for_names(bpy, object_names)
            if issues:
                return skill_error(
                    "Modeling scope contains missing objects",
                    "modeling_scope_missing",
                    issues=issues,
                )
        else:
            objects = _objects(bpy)
        state = _build_model_state(objects)
        return skill_success(
            "Modeling state exported",
            state=state,
            object_count=len(state["objects"]),
            mesh_count=len(state["meshes"]),
            partial=state["partial"],
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message="Failed to export modeling state")


__all__ = ["CHECK_NAMES", "SCHEMA_NAME", "SCHEMA_VERSION", "export_model_state"]
