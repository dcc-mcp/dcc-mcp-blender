"""Shared validation, selection, and readback helpers for typed modeling verbs."""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any, List, Optional, Sequence, Tuple

from dcc_mcp_core.skill import skill_error, skill_success

AXIS_INDEX = {"x": 0, "y": 1, "z": 2}
MAX_EVIDENCE_ELEMENTS = 1_000_000


def operator_finished(result: Any) -> bool:
    """Return whether a Blender operator explicitly reported FINISHED."""
    return isinstance(result, set) and "FINISHED" in result


def object_identity(obj: Any) -> int:
    """Return one process-local identity for provenance checks."""
    try:
        pointer = obj.as_pointer()
    except Exception:
        pointer = None
    if isinstance(pointer, int) and not isinstance(pointer, bool) and pointer > 0:
        return pointer
    return id(obj)


def _float_sequence(value: Any) -> List[float]:
    try:
        return [round(float(component), 9) for component in value]
    except (TypeError, ValueError):
        return []


def _int_sequence(value: Any) -> List[int]:
    try:
        return [int(component) for component in value]
    except (TypeError, ValueError):
        return []


def _bounded_collection_length(collection: Any, label: str) -> int:
    count = len(collection)
    if count > MAX_EVIDENCE_ELEMENTS:
        raise ValueError(f"{label} exceeds the modeling evidence limit of {MAX_EVIDENCE_ELEMENTS} elements")
    return count


def _update_digest(digest: Any, label: str, value: Any) -> None:
    """Append one canonical record without materializing the whole mesh."""
    encoded = json.dumps([label, value], allow_nan=False, separators=(",", ":")).encode("ascii")
    digest.update(encoded)
    digest.update(b"\n")


def mesh_state(obj: Any) -> dict:
    """Return topology and coordinate evidence for an object's owned mesh."""
    mesh = obj.data
    vertices = getattr(mesh, "vertices", [])
    edges = getattr(mesh, "edges", [])
    polygons = getattr(mesh, "polygons", [])
    vertex_count = _bounded_collection_length(vertices, "mesh vertices")
    edge_count = _bounded_collection_length(edges, "mesh edges")
    face_count = _bounded_collection_length(polygons, "mesh polygons")
    if vertex_count + edge_count + face_count > MAX_EVIDENCE_ELEMENTS:
        raise ValueError(f"mesh exceeds the modeling evidence limit of {MAX_EVIDENCE_ELEMENTS} elements")
    digest = hashlib.sha256()
    _update_digest(digest, "schema", "dcc-mcp/blender-mesh-evidence@1")
    _update_digest(digest, "counts", [vertex_count, edge_count, face_count])
    for vertex in vertices:
        _update_digest(digest, "v", _float_sequence(getattr(vertex, "co", [])))
    for edge in edges:
        _update_digest(digest, "e", _int_sequence(getattr(edge, "vertices", [])))
    for polygon in polygons:
        _update_digest(digest, "p", _int_sequence(getattr(polygon, "vertices", [])))
    return {
        "vertex_count": vertex_count,
        "edge_count": edge_count,
        "face_count": face_count,
        "mesh_digest": digest.hexdigest(),
    }


def uv_state(obj: Any) -> dict:
    """Return active UV-set identity and exact coordinate evidence."""
    layers = getattr(obj.data, "uv_layers", [])
    active = getattr(getattr(obj.data, "uv_layers", None), "active", None)
    data = getattr(active, "data", []) if active is not None else []
    layer_count = _bounded_collection_length(layers, "UV layers")
    coordinate_count = _bounded_collection_length(data, "UV coordinates")
    if layer_count + coordinate_count > MAX_EVIDENCE_ELEMENTS:
        raise ValueError(f"UV data exceeds the modeling evidence limit of {MAX_EVIDENCE_ELEMENTS} elements")
    active_name = getattr(active, "name", None)
    digest = hashlib.sha256()
    _update_digest(digest, "schema", "dcc-mcp/blender-uv-evidence@1")
    _update_digest(digest, "active", active_name)
    _update_digest(digest, "counts", [layer_count, coordinate_count])
    for layer in layers:
        _update_digest(digest, "layer", getattr(layer, "name", None))
    for loop in data:
        _update_digest(digest, "uv", _float_sequence(getattr(loop, "uv", [])))
    return {
        "active_uv_map": active_name,
        "uv_map_count": layer_count,
        "uv_coordinate_count": coordinate_count,
        "uv_digest": digest.hexdigest(),
    }


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


def mesh_evidence_counts(obj: Any) -> dict:
    """Return bounded-size readback without iterating mesh elements."""
    counts = mesh_counts(obj)
    counts["evidence_limited"] = sum(counts.values()) > MAX_EVIDENCE_ELEMENTS
    return counts


def post_mutation_mesh_state(operation: str, obj: Any, before: dict) -> Tuple[Optional[dict], Optional[dict]]:
    """Hash a mutated mesh or return a truthful bounded failure receipt."""
    counts = mesh_evidence_counts(obj)
    if counts["evidence_limited"]:
        return None, skill_error(
            f"{operation} evidence limit exceeded",
            "The mutated mesh is too large for bounded verification.",
            mutation_applied=True,
            rollback_attempted=False,
            rollback_verified=False,
            mesh_before=before,
            mesh_after_counts=counts,
        )
    try:
        return mesh_state(obj), None
    except Exception as exc:
        return None, skill_error(
            f"{operation} evidence failed",
            "The mutated mesh could not be verified safely.",
            mutation_applied=True,
            rollback_attempted=False,
            rollback_verified=False,
            error_type=type(exc).__name__,
            mesh_before=before,
            mesh_after_counts=counts,
        )


def uv_evidence_counts(obj: Any) -> dict:
    """Return bounded-size UV readback without iterating UV coordinates."""
    layers = getattr(obj.data, "uv_layers", [])
    active = getattr(layers, "active", None)
    data = getattr(active, "data", []) if active is not None else []
    layer_count = len(layers)
    coordinate_count = len(data)
    return {
        "active_uv_map": getattr(active, "name", None),
        "uv_map_count": layer_count,
        "uv_coordinate_count": coordinate_count,
        "evidence_limited": layer_count + coordinate_count > MAX_EVIDENCE_ELEMENTS,
    }


def post_mutation_uv_state(operation: str, obj: Any, before: dict) -> Tuple[Optional[dict], Optional[dict]]:
    """Hash mutated UV data or return a truthful bounded failure receipt."""
    counts = uv_evidence_counts(obj)
    if counts["evidence_limited"]:
        return None, skill_error(
            f"{operation} evidence limit exceeded",
            "The mutated UV data is too large for bounded verification.",
            mutation_applied=True,
            rollback_attempted=False,
            rollback_verified=False,
            uv_before=before,
            uv_after_counts=counts,
        )
    try:
        return uv_state(obj), None
    except Exception as exc:
        return None, skill_error(
            f"{operation} evidence failed",
            "The mutated UV data could not be verified safely.",
            mutation_applied=True,
            rollback_attempted=False,
            rollback_verified=False,
            error_type=type(exc).__name__,
            uv_before=before,
            uv_after_counts=counts,
        )


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
            mutation_applied=after.get("mesh_digest") != before.get("mesh_digest"),
            rollback_attempted=False,
            rollback_verified=False,
            before=before,
            after=after,
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
