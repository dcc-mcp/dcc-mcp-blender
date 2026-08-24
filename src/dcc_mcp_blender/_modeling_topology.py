"""Verified component-level mesh edits for the shared modeling vocabulary."""

from __future__ import annotations

import math
from typing import Sequence

from dcc_mcp_core.skill import skill_error, skill_exception

from dcc_mcp_blender._modeling_common import (
    bounded_indices,
    mesh_counts,
    mesh_object,
    object_mode,
    object_mode_if_available,
    select_components,
    topology_result,
    vector,
)


def bevel_edges(object_name: str, edge_indices: Sequence[int], width: float, segments: int = 1) -> dict:
    """Bevel explicit edges and require a host topology delta."""
    try:
        width_value = float(width)
    except (TypeError, ValueError):
        return skill_error("Invalid width", "width must be numeric.")
    if not math.isfinite(width_value) or width_value <= 0 or width_value > 1_000_000:
        return skill_error("Invalid width", "width must be finite, greater than zero, and at most 1000000.")
    if not isinstance(segments, int) or isinstance(segments, bool) or not 1 <= segments <= 64:
        return skill_error("Invalid segments", "segments must be an integer between 1 and 64.")
    try:
        import bpy

        obj, error = mesh_object(bpy, object_name)
        if error:
            return error
        selected, error = bounded_indices(edge_indices, "edge_indices", len(obj.data.edges))
        if error:
            return error
        before = mesh_counts(obj)
        select_components(bpy, obj, "edges", selected)
        bpy.ops.mesh.bevel(offset=width_value, segments=segments, affect="EDGES")
        object_mode(bpy)
        return topology_result(
            "Bevel edges",
            obj,
            {"edge_indices": selected, "segments": segments, "width": width_value},
            before,
            mesh_counts(obj),
            "edge_count",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        object_mode_if_available()
        return skill_exception(exc, message=f"Failed to bevel edges on {object_name}")


def extrude_faces(
    object_name: str,
    face_indices: Sequence[int],
    distance: float = 0.0,
    direction: Sequence[float] = (0.0, 0.0, 1.0),
) -> dict:
    """Extrude explicit faces and require a host topology delta."""
    direction_value, error = vector(direction, "direction")
    if error:
        return error
    try:
        distance_value = float(distance)
    except (TypeError, ValueError):
        return skill_error("Invalid distance", "distance must be numeric.")
    if not math.isfinite(distance_value) or abs(distance_value) > 1_000_000:
        return skill_error("Invalid distance", "distance must be finite and within +/-1000000.")
    try:
        import bpy

        obj, error = mesh_object(bpy, object_name)
        if error:
            return error
        selected, error = bounded_indices(face_indices, "face_indices", len(obj.data.polygons))
        if error:
            return error
        before = mesh_counts(obj)
        select_components(bpy, obj, "polygons", selected)
        offset = [component * distance_value for component in direction_value]
        bpy.ops.mesh.extrude_region_move(TRANSFORM_OT_translate={"value": offset})
        object_mode(bpy)
        return topology_result(
            "Extrude faces",
            obj,
            {"direction": direction_value, "distance": distance_value, "face_indices": selected},
            before,
            mesh_counts(obj),
            "face_count",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        object_mode_if_available()
        return skill_exception(exc, message=f"Failed to extrude faces on {object_name}")


def inset(
    object_name: str,
    face_indices: Sequence[int],
    thickness: float,
    depth: float = 0.0,
) -> dict:
    """Inset explicit faces and require a host topology delta."""
    try:
        thickness_value = float(thickness)
        depth_value = float(depth)
    except (TypeError, ValueError):
        return skill_error("Invalid inset", "thickness and depth must be numeric.")
    if not 0 <= thickness_value <= 1_000_000 or abs(depth_value) > 1_000_000:
        return skill_error("Invalid inset", "thickness and depth exceed the supported bounds.")
    try:
        import bpy

        obj, error = mesh_object(bpy, object_name)
        if error:
            return error
        selected, error = bounded_indices(face_indices, "face_indices", len(obj.data.polygons))
        if error:
            return error
        before = mesh_counts(obj)
        select_components(bpy, obj, "polygons", selected)
        bpy.ops.mesh.inset(thickness=thickness_value, depth=depth_value, use_even_offset=True)
        object_mode(bpy)
        return topology_result(
            "Inset faces",
            obj,
            {"depth": depth_value, "face_indices": selected, "thickness": thickness_value},
            before,
            mesh_counts(obj),
            "face_count",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        object_mode_if_available()
        return skill_exception(exc, message=f"Failed to inset faces on {object_name}")


def add_edge_loop(object_name: str, edge_indices: Sequence[int], cuts: int = 1) -> dict:
    """Subdivide an explicit edge ring and require a host topology delta."""
    if not isinstance(cuts, int) or isinstance(cuts, bool) or not 1 <= cuts <= 64:
        return skill_error("Invalid cuts", "cuts must be an integer between 1 and 64.")
    try:
        import bpy

        obj, error = mesh_object(bpy, object_name)
        if error:
            return error
        selected, error = bounded_indices(edge_indices, "edge_indices", len(obj.data.edges))
        if error:
            return error
        before = mesh_counts(obj)
        select_components(bpy, obj, "edges", selected)
        bpy.ops.mesh.subdivide(number_cuts=cuts, smoothness=0.0)
        object_mode(bpy)
        return topology_result(
            "Add edge loop",
            obj,
            {"cuts": cuts, "edge_indices": selected},
            before,
            mesh_counts(obj),
            "edge_count",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        object_mode_if_available()
        return skill_exception(exc, message=f"Failed to add edge loop on {object_name}")
