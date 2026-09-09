"""Bounded component discovery for the original, object-local mesh."""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Optional, Sequence, Tuple

from dcc_mcp_core.skill import skill_error, skill_exception, skill_success

from dcc_mcp_blender._modeling_common import object_identity

MAX_SCAN_ELEMENTS = 100_000
MAX_PAGE_SIZE = 256
MAX_RECORD_CONNECTIONS = 64


def _vector(value: Any) -> list:
    result = list(value)
    if len(result) != 3 or any(isinstance(item, bool) or not isinstance(item, (int, float)) for item in result):
        raise ValueError("Expected three finite numeric coordinates")
    result = [float(item) for item in result]
    if not all(math.isfinite(item) for item in result):
        raise ValueError("Expected three finite numeric coordinates")
    return result


def _revision(obj: Any) -> str:
    mesh = obj.data
    digest = hashlib.sha256()

    def append(value: Any) -> None:
        digest.update(json.dumps(value, allow_nan=False, separators=(",", ":")).encode("ascii"))
        digest.update(b"\n")

    append(["mesh-query-v1", object_identity(obj), object_identity(mesh)])
    for vertex in mesh.vertices:
        append(["v", _vector(vertex.co), _vector(vertex.normal)])
    for edge in mesh.edges:
        append(["e", list(edge.vertices)])
    for face in mesh.polygons:
        append(["f", list(face.vertices), _vector(face.normal)])
    return "mesh-query-v1:" + digest.hexdigest()


def mesh_revision(obj: Any, expected_revision: Optional[str] = None) -> Tuple[Optional[str], Optional[dict]]:
    """Read or check a bounded revision without selection, mode changes or adjacency allocation."""
    if expected_revision is not None and (
        not isinstance(expected_revision, str)
        or not expected_revision.startswith("mesh-query-v1:")
        or len(expected_revision) != 78
        or any(character not in "0123456789abcdef" for character in expected_revision[14:])
    ):
        return None, skill_error(
            "Invalid revision",
            "Use the unchanged revision returned by inspect_mesh_components.",
            error_code="invalid_mesh_revision",
            mutation_applied=False,
        )
    try:
        if obj.mode != "OBJECT" or obj.data.is_editmode:
            return None, skill_error(
                "Object mode required",
                "Leave Edit/Sculpt/Paint mode explicitly before querying or using a component revision.",
                error_code="mesh_revision_mode_required",
                mutation_applied=False,
            )
        mesh = obj.data
        if sum(len(items) for items in (mesh.vertices, mesh.edges, mesh.polygons, mesh.loops)) > MAX_SCAN_ELEMENTS:
            return None, skill_error(
                "Mesh scan limit exceeded",
                "Use a smaller mesh; component revisions are never partial.",
                error_code="mesh_revision_scan_limit",
                mutation_applied=False,
            )
        revision = _revision(obj)
        if expected_revision is not None and revision != expected_revision:
            return None, skill_error(
                "Mesh revision changed",
                "Discard previous component indices and query again without expected_revision.",
                error_code="stale_mesh_revision",
                current_revision=revision,
                mutation_applied=False,
            )
        return revision, None
    except Exception as exc:
        return None, skill_error(
            "Mesh revision unavailable",
            "The original mesh could not be read safely. Inspect the object before retrying.",
            error_code="mesh_revision_unavailable",
            error_type=type(exc).__name__,
            mutation_applied=False,
        )


def _connectivity(mesh: Any) -> dict:
    vertex_edges = [[] for _ in mesh.vertices]
    vertex_faces = [[] for _ in mesh.vertices]
    edge_faces = [[] for _ in mesh.edges]
    face_edges = []
    edge_lookup = {}
    for index, edge in enumerate(mesh.edges):
        left, right = edge.vertices
        vertex_edges[left].append(index)
        vertex_edges[right].append(index)
        edge_lookup[tuple(sorted((left, right)))] = index
    for index, face in enumerate(mesh.polygons):
        vertices = list(face.vertices)
        edges = []
        for left, right in zip(vertices, vertices[1:] + vertices[:1]):
            vertex_faces[left].append(index)
            edge_index = edge_lookup[tuple(sorted((left, right)))]
            edge_faces[edge_index].append(index)
            edges.append(edge_index)
        face_edges.append(edges)
    return {
        "vertex_edges": vertex_edges,
        "vertex_faces": vertex_faces,
        "edge_faces": edge_faces,
        "face_edges": face_edges,
    }


def _record(mesh: Any, connectivity: dict, component: str, index: int) -> dict:
    record = {"index": index}
    if component == "vertex":
        vertex = mesh.vertices[index]
        record.update(position=_vector(vertex.co), normal=_vector(vertex.normal))
        connections = {"edge": connectivity["vertex_edges"][index], "face": connectivity["vertex_faces"][index]}
    else:
        item = (mesh.edges if component == "edge" else mesh.polygons)[index]
        vertices = list(item.vertices)
        positions = [_vector(mesh.vertices[vertex].co) for vertex in vertices]
        record["position"] = _vector(
            [sum(position[axis] / len(positions) for position in positions) for axis in range(3)]
        )
        connections = {"vertex": vertices}
        if component == "edge":
            connections["face"] = connectivity["edge_faces"][index]
        else:
            record["normal"] = _vector(item.normal)
            connections["edge"] = connectivity["face_edges"][index]
    record["connectivity_complete"] = True
    for kind, indices in connections.items():
        record[kind + "_count"] = len(indices)
        record[kind + "_indices"] = indices[:MAX_RECORD_CONNECTIONS]
        record["connectivity_complete"] &= len(indices) <= MAX_RECORD_CONNECTIONS
    return record


def _unit_vector(value: Any) -> list:
    vector = _vector(value)
    scale = max(abs(item) for item in vector)
    if not scale:
        raise ValueError("Normal direction cannot be zero")
    scaled = [item / scale for item in vector]
    length = math.sqrt(sum(item * item for item in scaled))
    return [item / length for item in scaled]


def _matches(
    record: dict, bounds_min: Optional[list], bounds_max: Optional[list], direction: Optional[list], dot: float
) -> bool:
    if bounds_min is not None and any(
        not low <= coordinate <= high for coordinate, low, high in zip(record["position"], bounds_min, bounds_max)
    ):
        return False
    if direction is not None:
        normal = record["normal"]
        if not any(normal):
            return False
        if sum(left * right for left, right in zip(_unit_vector(normal), direction)) < dot:
            return False
    return True


def inspect_mesh_components(
    object_name: str,
    component: str = "vertex",
    offset: int = 0,
    limit: int = 64,
    expected_revision: Optional[str] = None,
    bounds_min: Optional[Sequence[float]] = None,
    bounds_max: Optional[Sequence[float]] = None,
    normal_direction: Optional[Sequence[float]] = None,
    normal_min_dot: float = 0.9,
) -> dict:
    """Return a bounded page of original-mesh components without changing mode."""
    if not isinstance(object_name, str) or not object_name.strip():
        return skill_error("Invalid object name", "Provide a non-empty mesh object name.")
    if component not in ("vertex", "edge", "face"):
        return skill_error("Invalid component", "Choose vertex, edge, or face.")
    if isinstance(offset, bool) or not isinstance(offset, int) or not 0 <= offset <= MAX_SCAN_ELEMENTS:
        return skill_error("Invalid offset", "Offset must be an integer within the scan bound.")
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_PAGE_SIZE:
        return skill_error("Invalid limit", "Limit must be an integer between 1 and 256.")
    try:
        if (bounds_min is None) != (bounds_max is None):
            raise ValueError("Provide both bounds_min and bounds_max")
        lower = _vector(bounds_min) if bounds_min is not None else None
        upper = _vector(bounds_max) if bounds_max is not None else None
        if lower is not None and any(low > high for low, high in zip(lower, upper)):
            raise ValueError("bounds_min must not exceed bounds_max")
        if (
            isinstance(normal_min_dot, bool)
            or not isinstance(normal_min_dot, (int, float))
            or not -1 <= normal_min_dot <= 1
        ):
            raise ValueError("normal_min_dot must be finite and between -1 and 1")
        direction = _unit_vector(normal_direction) if normal_direction is not None else None
        if direction is not None and component == "edge":
            raise ValueError("Edges have no unique normal; use a vertex or face normal filter")
    except (TypeError, ValueError) as exc:
        return skill_error("Invalid geometric filter", str(exc))
    try:
        import bpy

        obj = bpy.data.objects.get(object_name)
        if obj is None or obj.type != "MESH":
            return skill_error("Mesh not found", "Choose an existing mesh object.")
        revision, error = mesh_revision(obj, expected_revision)
        if error:
            return error
        mesh = obj.data
        counts = {"vertex": len(mesh.vertices), "edge": len(mesh.edges), "face": len(mesh.polygons)}
        connectivity = _connectivity(mesh)
        records = []
        stop = min(offset, counts[component])
        for index in range(offset, counts[component]):
            stop = index + 1
            record = _record(mesh, connectivity, component, index)
            if _matches(record, lower, upper, direction, normal_min_dot):
                records.append(record)
                if len(records) == limit:
                    break
        return skill_success(
            "Inspected mesh components",
            object_name=obj.name,
            mesh_name=mesh.name,
            component=component,
            coordinate_space="local",
            mesh_source="original",
            revision=revision,
            counts=counts,
            records=records,
            next_offset=stop if stop < counts[component] else None,
            prompt="Re-query after geometry edits; component indices are not stable across topology changes.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported.")
    except Exception as exc:
        return skill_exception(exc, message="Failed to inspect mesh components")
