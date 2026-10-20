"""Bounded, revision-pinned material assignments on the original mesh.

No operators, selection changes, mode switches, material creation or slot edits.
A revision pins geometry and effective material slots, but intentionally excludes
polygon material indices so repeating an assignment is safe and idempotent.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Optional

from dcc_mcp_core.skill import skill_error, skill_success

from dcc_mcp_blender._mesh_query_ops import MAX_SCAN_ELEMENTS, mesh_revision
from dcc_mcp_blender._modeling_common import object_identity

MAX_ASSIGNMENTS = 4096
MAX_PAGE_SIZE = 256
MAX_MATERIAL_SLOTS = 1024
REVISION_PREFIX = "face-materials-v1:"


def _error(code: str, detail: str, **context: Any) -> dict:
    context.setdefault("mutation_applied", False)
    return skill_error("Face material operation rejected", detail, error_code=code, **context)


def _integer(value: Any, upper: int) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= upper


def _valid_revision(value: Any) -> bool:
    return (
        isinstance(value, str)
        and value.startswith(REVISION_PREFIX)
        and len(value) == len(REVISION_PREFIX) + 64
        and all(character in "0123456789abcdef" for character in value[len(REVISION_PREFIX) :])
    )


def _slot_records(obj: Any) -> list:
    return [
        {
            "material_index": index,
            "material_name": slot.material.name if slot.material is not None else None,
            "link": slot.link,
        }
        for index, slot in enumerate(obj.material_slots)
    ]


def _revision(obj: Any) -> tuple:
    """Reuse the bounded original-mesh guard and also pin effective slot IDs."""
    geometry_revision, error = mesh_revision(obj)
    if error:
        return None, error
    if len(obj.material_slots) > MAX_MATERIAL_SLOTS:
        return None, _error("face_material_slot_limit", "At most 1024 material slots can be inspected or assigned.")
    slots = [
        [
            slot.link,
            object_identity(slot.material) if slot.material is not None else None,
            slot.material.name if slot.material is not None else None,
        ]
        for slot in obj.material_slots
    ]
    payload = json.dumps([geometry_revision, slots], ensure_ascii=True, separators=(",", ":"))
    return REVISION_PREFIX + hashlib.sha256(payload.encode("ascii")).hexdigest(), None


def _target(object_name: Any, expected_revision: Any, required: bool = False) -> tuple:
    if not isinstance(object_name, str) or not object_name.strip() or len(object_name) > 1024:
        return (
            None,
            None,
            _error("invalid_object_name", "Provide the exact non-empty object name (at most 1024 characters)."),
        )
    if (required or expected_revision is not None) and not _valid_revision(expected_revision):
        return (
            None,
            None,
            _error("invalid_face_material_revision", "Use the unchanged revision from inspect_face_materials."),
        )
    try:
        import bpy

        obj = bpy.data.objects.get(object_name)
        if obj is None:
            return None, None, _error("object_not_found", "No object exists with the exact requested name.")
        if obj.type != "MESH":
            return None, None, _error("mesh_required", "The target must be a mesh object.")
        revision, error = _revision(obj)
        if error:
            return None, None, error
        if expected_revision is not None and expected_revision != revision:
            return (
                None,
                None,
                _error(
                    "stale_face_material_revision",
                    "Geometry, object identity or material slots changed. Inspect again before assigning face indices.",
                    current_revision=revision,
                ),
            )
        return obj, revision, None
    except ImportError:
        return None, None, _error("blender_unavailable", "bpy could not be imported.")
    except Exception as exc:
        return (
            None,
            None,
            _error(
                "face_material_read_failed", "The target could not be inspected safely.", error_type=type(exc).__name__
            ),
        )


def _records(mesh: Any, indices: Any) -> list:
    return [{"face_index": index, "material_index": mesh.polygons[index].material_index} for index in indices]


def inspect_face_materials(
    object_name: str, offset: int = 0, limit: int = 64, expected_revision: Optional[str] = None
) -> dict:
    """Read a bounded page of original polygon indices and effective material slots."""
    if not _integer(offset, MAX_SCAN_ELEMENTS):
        return _error("invalid_face_material_offset", "offset must be an integer from 0 through 100000.")
    if not _integer(limit, MAX_PAGE_SIZE) or limit == 0:
        return _error("invalid_face_material_limit", "limit must be an integer from 1 through 256.")
    obj, revision, error = _target(object_name, expected_revision)
    if error:
        return error
    try:
        count = len(obj.data.polygons)
        stop = min(offset + limit, count)
        return skill_success(
            "Inspected face materials",
            object_name=obj.name,
            mesh_name=obj.data.name,
            mesh_source="original",
            face_count=count,
            revision=revision,
            assignments=_records(obj.data, range(min(offset, count), stop)),
            material_slots=_slot_records(obj),
            next_offset=stop if stop < count else None,
            mutation_applied=False,
            prompt="Use this session-local revision for assignment and pagination. Re-inspect after reopening a file; evaluated/exported topology may differ.",
        )
    except Exception as exc:
        return _error(
            "face_material_read_failed",
            "Polygon material indices could not be read safely.",
            error_type=type(exc).__name__,
        )


def _validate_assignments(assignments: Any) -> Optional[dict]:
    if not isinstance(assignments, list) or not 1 <= len(assignments) <= MAX_ASSIGNMENTS:
        return _error(
            "invalid_face_material_assignments", "assignments must be a list containing 1 through 4096 records."
        )
    seen = set()
    for record in assignments:
        if not isinstance(record, dict) or set(record) != {"face_index", "material_index"}:
            return _error(
                "invalid_face_material_assignments", "Each record must contain only face_index and material_index."
            )
        if not _integer(record["face_index"], MAX_SCAN_ELEMENTS - 1):
            return _error("invalid_face_index", "face_index must be an integer from 0 through 99999, never a boolean.")
        if not _integer(record["material_index"], MAX_MATERIAL_SLOTS - 1):
            return _error(
                "invalid_material_index", "material_index must be an integer from 0 through 1023, never a boolean."
            )
        if record["face_index"] in seen:
            return _error(
                "duplicate_face_index", "Each polygon may appear only once, even when repeated assignments agree."
            )
        seen.add(record["face_index"])
    return None


def _rollback(obj: Any, before: list, revision: str) -> dict:
    """Best effort restore every changed polygon; never infer success from setters."""
    errors = 0
    for index, value in enumerate(before):
        try:
            if obj.data.polygons[index].material_index != value:
                obj.data.polygons[index].material_index = value
        except Exception:
            errors += 1
    try:
        obj.data.update()
    except Exception:
        errors += 1
    try:
        after = [face.material_index for face in obj.data.polygons]
        actual_revision, error = _revision(obj)
        verified = not error and actual_revision == revision and after == before
        mutation_applied = (
            False if verified else (True if after != before or actual_revision != revision and not error else None)
        )
    except Exception:
        verified = False
        mutation_applied = None
    return {
        "rollback_attempted": True,
        "rollback_verified": bool(verified),
        "rollback_error_count": errors,
        "mutation_applied": mutation_applied,
    }


def assign_face_materials(object_name: str, assignments: list, expected_revision: str) -> dict:
    """Prevalidate a bounded batch, then apply and verify or restore its indices."""
    error = _validate_assignments(assignments)
    if error:
        return error
    obj, revision, error = _target(object_name, expected_revision, required=True)
    if error:
        return error
    try:
        mesh = obj.data
        if not len(mesh.polygons):
            return _error("empty_mesh", "The mesh has no polygons to assign.")
        if mesh.users > 1:
            return _error(
                "shared_mesh_data",
                "Make this mesh single-user explicitly before assigning; other objects must not change.",
            )
        if any(
            getattr(data, "library", None) is not None
            or getattr(data, "override_library", None) is not None
            or not getattr(data, "is_editable", True)
            for data in (obj, mesh)
        ):
            return _error("readonly_mesh_data", "Linked, overridden or read-only object/mesh data cannot be assigned.")
        for record in assignments:
            if record["face_index"] >= len(mesh.polygons):
                return _error("face_index_out_of_range", "Every face_index must address an existing polygon.")
            if record["material_index"] >= len(obj.material_slots):
                return _error(
                    "material_index_out_of_range", "Every material_index must address an existing material slot."
                )
            if obj.material_slots[record["material_index"]].material is None:
                return _error(
                    "empty_material_slot",
                    "Assign an existing material to each requested slot before assigning polygons.",
                )
        before = [face.material_index for face in mesh.polygons]
        desired = before.copy()
        for record in assignments:
            desired[record["face_index"]] = record["material_index"]
        changed_count = sum(left != right for left, right in zip(before, desired))
    except Exception as exc:
        return _error(
            "face_material_read_failed", "Preflight failed; no assignment was attempted.", error_type=type(exc).__name__
        )
    try:
        for record in assignments:
            index = record["face_index"]
            if before[index] != record["material_index"]:
                mesh.polygons[index].material_index = record["material_index"]
        if changed_count:
            mesh.update()
        after = [face.material_index for face in mesh.polygons]
        actual_revision, error = _revision(obj)
        if after != desired or error or actual_revision != revision:
            raise RuntimeError("Exact face material or geometry/slot readback did not match the request")
        return skill_success(
            "Assigned face materials",
            object_name=obj.name,
            mesh_name=mesh.name,
            mesh_source="original",
            face_count=len(mesh.polygons),
            revision=revision,
            assignments=_records(mesh, [record["face_index"] for record in assignments]),
            affected_count=len(assignments),
            changed_count=changed_count,
            mutation_applied=changed_count > 0,
            verified=True,
            postcondition={"method": "exact_polygon_material_indices_and_revision"},
        )
    except Exception as exc:
        return _error(
            "face_material_assignment_failed",
            "Assignment failed. Inspect rollback_verified and mutation_applied before retrying; inspect the mesh if rollback is unverified.",
            error_type=type(exc).__name__,
            **_rollback(obj, before, revision),
        )
