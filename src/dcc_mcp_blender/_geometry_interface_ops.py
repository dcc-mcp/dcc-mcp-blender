"""Bounded, revision-pinned Geometry Nodes interface operations (Blender 4+)."""

from __future__ import annotations

import hashlib
import json
import math
import re
from typing import Optional

from dcc_mcp_core.skill import skill_error, skill_success

from dcc_mcp_blender._modeling_common import object_identity

MAX_INTERFACE_ITEMS = 256
SOCKET_TYPES = {
    "NodeSocketGeometry",
    "NodeSocketFloat",
    "NodeSocketInt",
    "NodeSocketBool",
    "NodeSocketVector",
    "NodeSocketColor",
    "NodeSocketString",
}


def _failure(code, detail, *, mutation=False, **context):
    return skill_error(
        "Geometry Nodes interface operation failed",
        detail,
        error_code=code,
        mutation_applied=mutation,
        rollback_attempted=False,
        rollback_verified=False,
        **context,
    )


def _resolve(group_name, *, writable=False):
    if not isinstance(group_name, str) or not group_name.strip():
        return None, _failure("invalid_group_name", "Provide an existing Geometry Nodes group name.")
    import bpy

    group = bpy.data.node_groups.get(group_name)
    if group is None or group.bl_idname != "GeometryNodeTree":
        return None, _failure("geometry_group_not_found", "Choose an existing GeometryNodeTree.")
    if getattr(group, "interface", None) is None:
        return None, _failure(
            "interface_api_unavailable", "This interface editing surface requires Blender 4.0 or newer."
        )
    if writable and (group.library is not None or group.override_library is not None):
        return None, _failure("local_group_required", "Linked and library-override node groups are read-only here.")
    if len(group.interface.items_tree) > MAX_INTERFACE_ITEMS:
        return None, _failure("interface_scan_limit", "Interface exceeds the 256-item bound; no partial revisions.")
    return group, None


def _bounded_text(value):
    if not isinstance(value, str) or len(value) > 1024 or len(value.encode("utf-8")) > 1024:
        raise ValueError("Interface text exceeds the 1024-byte readback bound")
    return value


def _default_value(socket):
    if socket.socket_type not in SOCKET_TYPES or not hasattr(socket, "default_value"):
        return None
    value = socket.default_value
    if socket.socket_type in ("NodeSocketVector", "NodeSocketColor"):
        if len(value) > 4:
            raise ValueError("Invalid socket vector dimension")
        value = list(value)
    if isinstance(value, str):
        value = _bounded_text(value)
    return value


def _snapshot(group):
    if len(group.interface.items_tree) > MAX_INTERFACE_ITEMS:
        raise ValueError("Interface exceeds the bounded readback limit")
    sockets, panels = [], []
    for position, item in enumerate(group.interface.items_tree):
        parent = getattr(item, "parent", None)
        location = {"position": position, "parent_identity": object_identity(parent) if parent is not None else None}
        if item.item_type == "SOCKET":
            sockets.append(
                {
                    "identifier": _bounded_text(item.identifier),
                    "name": _bounded_text(item.name),
                    "in_out": item.in_out,
                    "socket_type": item.socket_type,
                    "description": _bounded_text(item.description),
                    "default_value": _default_value(item),
                    "default_editable": item.socket_type in SOCKET_TYPES and hasattr(item, "default_value"),
                    **location,
                }
            )
        elif item.item_type == "PANEL":
            panels.append(
                {"name": _bounded_text(item.name), "description": _bounded_text(item.description), **location}
            )
    payload = [object_identity(group), sockets, panels]
    revision = (
        "gn-interface-v1:"
        + hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
        ).hexdigest()
    )
    return {
        "group_name": group.name,
        "group_users": group.users,
        "revision": revision,
        "sockets": sockets,
        "panels": panels,
    }


def inspect_geometry_node_interface(group_name: str) -> dict:
    """Inspect a complete bounded interface, without evaluating geometry or changing the graph."""
    try:
        group, error = _resolve(group_name)
        if error:
            return error
        return skill_success("Inspected Geometry Nodes interface", **_snapshot(group))
    except Exception as exc:
        return _failure(
            "interface_unavailable", "The interface could not be read safely.", error_type=type(exc).__name__
        )


def _prepare_edit(group_name, expected_revision):
    if (
        not isinstance(expected_revision, str)
        or re.fullmatch(r"gn-interface-v1:[0-9a-f]{64}", expected_revision) is None
    ):
        return (
            None,
            None,
            _failure("invalid_interface_revision", "Use the revision from inspect_geometry_node_interface."),
        )
    group, error = _resolve(group_name, writable=True)
    if error:
        return None, None, error
    before = _snapshot(group)
    if before["revision"] != expected_revision:
        return (
            None,
            None,
            _failure(
                "stale_interface_revision",
                "Inspect again before editing this group.",
                current_revision=before["revision"],
            ),
        )
    return group, before, None


def _valid_name(name):
    return isinstance(name, str) and bool(name.strip()) and len(name.encode("utf-8")) <= 63


def _named_socket(group, identifier):
    return next(
        (item for item in group.interface.items_tree if item.item_type == "SOCKET" and item.identifier == identifier),
        None,
    )


def _socket_record(snapshot, identifier):
    return next(item for item in snapshot["sockets"] if item["identifier"] == identifier)


def create_geometry_node_socket(
    group_name: str, name: str, socket_type: str, in_out: str, expected_revision: str
) -> dict:
    """Create one supported socket on a local group and verify its native identifier."""
    started = False
    try:
        if not _valid_name(name) or not isinstance(socket_type, str) or socket_type not in SOCKET_TYPES:
            return _failure("invalid_socket", "Use a nonempty UTF-8 name up to 63 bytes and a supported socket type.")
        if in_out not in ("INPUT", "OUTPUT"):
            return _failure("invalid_direction", "Choose INPUT or OUTPUT.")
        group, before, error = _prepare_edit(group_name, expected_revision)
        if error:
            return error
        if len(group.interface.items_tree) >= MAX_INTERFACE_ITEMS:
            return _failure("interface_scan_limit", "The interface has no room within the 256-item bound.")
        if any(item["name"] == name and item["in_out"] == in_out for item in before["sockets"]):
            return _failure("duplicate_socket_name", "Choose a unique name within this input/output direction.")
        started = True
        socket = group.interface.new_socket(name=name, in_out=in_out, socket_type=socket_type)
        after = _snapshot(group)
        record = _socket_record(after, socket.identifier)
        if (record["name"], record["in_out"], record["socket_type"]) != (name, in_out, socket_type):
            raise ValueError("Socket creation readback mismatch")
        if len(after["sockets"]) != len(before["sockets"]) + 1:
            raise ValueError("Socket count readback mismatch")
        return skill_success("Created Geometry Nodes socket; affects all group users", socket=record, **after)
    except Exception as exc:
        return _failure(
            "interface_edit_failed",
            "Inspect the group before retrying; no rollback was attempted.",
            mutation=started,
            error_type=type(exc).__name__,
        )


def _normalise_default(socket, value):
    kind = socket.socket_type
    if kind == "NodeSocketBool" and isinstance(value, bool):
        return value
    if kind == "NodeSocketInt" and isinstance(value, int) and not isinstance(value, bool) and abs(value) <= 1_000_000:
        return value
    if kind == "NodeSocketString" and isinstance(value, str) and len(value.encode("utf-8")) <= 1024:
        return value
    if kind == "NodeSocketFloat":
        values = [value]
    elif kind in ("NodeSocketVector", "NodeSocketColor"):
        size = 3 if kind == "NodeSocketVector" else 4
        if not isinstance(value, (list, tuple)) or len(value) != size:
            raise ValueError("Vector/color defaults require exactly three/four components")
        values = list(value)
    else:
        raise ValueError("Unsupported or invalid socket default")
    if any(
        isinstance(item, bool) or not isinstance(item, (int, float)) or not math.isfinite(item) or abs(item) > 1_000_000
        for item in values
    ):
        raise ValueError("Numeric defaults must be finite and within +/-1000000")
    return float(values[0]) if kind == "NodeSocketFloat" else [float(item) for item in values]


def _equal_default(actual, expected):
    if isinstance(expected, list):
        return (
            isinstance(actual, list)
            and len(actual) == len(expected)
            and all(_equal_default(left, right) for left, right in zip(actual, expected))
        )
    if isinstance(expected, float):
        return isinstance(actual, (int, float)) and math.isclose(actual, expected, rel_tol=1e-6, abs_tol=1e-7)
    return type(actual) is type(expected) and actual == expected


def update_geometry_node_socket(
    group_name: str,
    socket_identifier: str,
    expected_revision: str,
    new_name: Optional[str] = None,
    description: Optional[str] = None,
    default_value=None,
) -> dict:
    """Update a socket label, description or supported default without replacing its identity."""
    started = False
    try:
        if new_name is None and description is None and default_value is None:
            return _failure("empty_socket_update", "Provide a name, description, or supported default value.")
        if new_name is not None and not _valid_name(new_name):
            return _failure("invalid_socket_name", "Socket names must be nonempty and at most 63 UTF-8 bytes.")
        if description is not None and (not isinstance(description, str) or len(description.encode("utf-8")) > 1024):
            return _failure("invalid_description", "Descriptions must be strings up to 1024 UTF-8 bytes.")
        group, before, error = _prepare_edit(group_name, expected_revision)
        if error:
            return error
        socket = _named_socket(group, socket_identifier)
        if socket is None:
            return _failure("socket_not_found", "Choose a socket identifier from the current interface query.")
        if new_name is not None and any(
            item["name"] == new_name and item["in_out"] == socket.in_out and item["identifier"] != socket_identifier
            for item in before["sockets"]
        ):
            return _failure("duplicate_socket_name", "Choose a unique name within this input/output direction.")
        if default_value is not None:
            try:
                if not hasattr(socket, "default_value"):
                    raise ValueError("This socket has no editable default")
                default_value = _normalise_default(socket, default_value)
            except ValueError as exc:
                return _failure("invalid_socket_default", str(exc))
        started = True
        if new_name is not None:
            socket.name = new_name
        if description is not None:
            socket.description = description
        if default_value is not None:
            socket.default_value = default_value
        after = _snapshot(group)
        record = _socket_record(after, socket_identifier)
        if new_name is not None and record["name"] != new_name:
            raise ValueError("Name readback mismatch")
        if description is not None and record["description"] != description:
            raise ValueError("Description readback mismatch")
        if default_value is not None and not _equal_default(record["default_value"], default_value):
            raise ValueError("Default readback mismatch")
        return skill_success("Updated Geometry Nodes socket; affects all group users", socket=record, **after)
    except Exception as exc:
        return _failure(
            "interface_edit_failed",
            "Inspect the group before retrying; no rollback was attempted.",
            mutation=started,
            error_type=type(exc).__name__,
        )


def remove_geometry_node_socket(group_name: str, socket_identifier: str, expected_revision: str) -> dict:
    """Remove one socket; Blender may disconnect its links and discard per-instance input values."""
    started = False
    try:
        group, before, error = _prepare_edit(group_name, expected_revision)
        if error:
            return error
        socket = _named_socket(group, socket_identifier)
        if socket is None:
            return _failure("socket_not_found", "Choose a socket identifier from the current interface query.")
        removed = _socket_record(before, socket_identifier)
        started = True
        group.interface.remove(socket)
        after = _snapshot(group)
        if any(item["identifier"] == socket_identifier for item in after["sockets"]):
            raise ValueError("Removed socket still exists")
        if len(after["sockets"]) != len(before["sockets"]) - 1:
            raise ValueError("Socket count readback mismatch")
        return skill_success("Removed Geometry Nodes socket; affects all group users", removed_socket=removed, **after)
    except Exception as exc:
        return _failure(
            "interface_edit_failed",
            "Inspect the group before retrying; no rollback was attempted.",
            mutation=started,
            error_type=type(exc).__name__,
        )
