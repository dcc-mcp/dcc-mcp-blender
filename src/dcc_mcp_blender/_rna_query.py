"""Bounded, read-only queries of Blender's live RNA metadata and modifiers.

RNA knowledge belongs to this adapter; execution, discovery, and result
envelopes remain Core-owned. No expression evaluation or data-path traversal.
"""

from __future__ import annotations

import json
import math
import re
from itertools import islice
from typing import Any

from dcc_mcp_core.skill import skill_error, skill_exception, skill_success

_IDENTIFIER = re.compile(r"[A-Za-z][A-Za-z0-9_]*\Z")
_MAX_IDENTIFIER = 128
_MAX_PAGE = 100
_MAX_OFFSET = 100000
_MAX_PROPERTIES = 32
_MAX_ARRAY = 32
_MAX_ENUM = 64
_MAX_STRING = 4096
_PAGE_BYTES = 24 * 1024  # Reserve 8 KiB for context, envelope, and field names.
_ROW_BYTES = 12 * 1024
_SCALAR_TYPES = {"BOOLEAN", "INT", "FLOAT", "STRING", "ENUM"}
_SCHEMA = "dcc-mcp-blender.rna-query.v1"


def _identifier(value: Any) -> bool:
    return isinstance(value, str) and len(value) <= _MAX_IDENTIFIER and bool(_IDENTIFIER.fullmatch(value))


def _page_error(query: Any, offset: Any, limit: Any) -> str | None:
    if not isinstance(query, str) or len(query) > 128 or any(ord(char) < 32 for char in query):
        return "query must be a string of at most 128 characters without control characters."
    if type(offset) is not int or not 0 <= offset <= _MAX_OFFSET:
        return "offset must be an integer between 0 and 100000."
    if type(limit) is not int or not 1 <= limit <= _MAX_PAGE:
        return "limit must be an integer between 1 and 100."
    return None


def _text(value: Any, limit: int = 256) -> str:
    return value[:limit] if isinstance(value, str) else ""


def _context(bpy: Any) -> dict:
    return {"schema": _SCHEMA, "blender_version": _text(bpy.app.version_string, 128), "response_budget_bytes": 32768}


def _pagination(total: int, offset: int, limit: int, returned: int) -> dict:
    end = min(total, offset + returned)
    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "returned": returned,
        "next_offset": end if end < total else None,
        "truncated": end < total,
    }


def _byte_length(value: Any) -> int:
    # Use stdlib here only for byte accounting: the Core Rust codec can emit
    # UTF-8 even with ensure_ascii=True. Budget for the larger ASCII form too.
    return len(json.dumps(value, ensure_ascii=True, allow_nan=False).encode("utf-8"))


def _bounded_page(rows: Any) -> list[dict]:
    page = []
    used = 2
    for row in rows:
        cost = _byte_length(row) + 2
        if used + cost > _PAGE_BYTES:
            break
        page.append(row)
        used += cost
    return page


def _label_fields(source: Any, description_limit: int = 256) -> dict:
    name = getattr(source, "name", "")
    description = getattr(source, "description", "")
    return {
        "name": _text(name, 128),
        "description": _text(description, description_limit),
        "text_truncated": (isinstance(name, str) and len(name) > 128)
        or (isinstance(description, str) and len(description) > description_limit),
    }


def _enum_item(item: Any) -> dict:
    row = {"identifier": _text(item.identifier, 128), **_label_fields(item, 160)}
    row["text_truncated"] = row["text_truncated"] or len(item.identifier) > 128
    return row


def _rna_type(bpy: Any, type_name: str) -> Any:
    candidate = getattr(bpy.types, type_name, None)
    rna = getattr(candidate, "bl_rna", None)
    # Alias/inherited Python attributes are not another RNA type.
    return rna if rna is not None and getattr(rna, "identifier", None) == type_name else None


def search_rna_types(query: str = "", offset: int = 0, limit: int = 20) -> dict:
    """Search current RNA types without instantiating them or invoking operators."""
    error = _page_error(query, offset, limit)
    if error:
        return skill_error("Invalid RNA query", error)
    try:
        import bpy

        matches = []
        needle = query.casefold()
        for name in sorted(dir(bpy.types)):
            if not _identifier(name):
                continue
            rna = _rna_type(bpy, name)
            if rna is None:
                continue
            row = {
                "identifier": name,
                **_label_fields(rna),
            }
            if not needle or any(needle in row[key].casefold() for key in ("identifier", "name", "description")):
                matches.append(row)
        page = _bounded_page(matches[offset : offset + limit])
        return skill_success(
            "RNA type search completed",
            **_context(bpy),
            types=page,
            **_pagination(len(matches), offset, limit, len(page)),
            prompt="Use describe_rna_type with an exact returned identifier; this does not imply a typed mutation tool exists.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported.")
    except Exception as exc:
        return skill_exception(exc, message="RNA type search unavailable")


def _property_metadata(prop: Any) -> dict:
    kind = prop.type
    row = {
        "identifier": prop.identifier,
        **_label_fields(prop),
        "type": kind,
        "is_readonly": bool(prop.is_readonly),
        "is_array": bool(getattr(prop, "is_array", False)),
        "array_length": int(getattr(prop, "array_length", 0)),
        "is_runtime": bool(getattr(prop, "is_runtime", False)),
        "subtype": _text(getattr(prop, "subtype", ""), 128),
        "unit": _text(getattr(prop, "unit", ""), 128),
        "value_support": "supported"
        if kind in _SCALAR_TYPES
        and not getattr(prop, "is_runtime", False)
        and (not getattr(prop, "is_array", False) or 0 < getattr(prop, "array_length", 0) <= _MAX_ARRAY)
        else "unsupported",
    }
    limits = {}
    for key in ("hard_min", "hard_max", "soft_min", "soft_max"):
        value = getattr(prop, key, None)
        if type(value) in (int, float) and math.isfinite(value):
            limits[key] = value
    row["limits"] = limits
    if kind == "ENUM":
        # enum_items may call host/add-on dynamic item generators. Never use it.
        static_items = getattr(prop, "enum_items_static", None)
        if static_items is None:
            row.update(enum_items=[], enum_truncated=False, enum_status="unavailable")
        else:
            items = list(islice(iter(static_items), _MAX_ENUM + 1))
            row.update(
                enum_items=[_enum_item(item) for item in items[:_MAX_ENUM]],
                enum_truncated=len(items) > _MAX_ENUM,
                enum_status="static_only",
                is_enum_flag=bool(getattr(prop, "is_enum_flag", False)),
            )
            while row["enum_items"] and _byte_length(row) > _ROW_BYTES:
                row["enum_items"].pop()
                row["enum_truncated"] = True
    return row


def describe_rna_type(type_name: str, query: str = "", offset: int = 0, limit: int = 20) -> dict:
    """Describe one current RNA type's property metadata in bounded pages."""
    error = _page_error(query, offset, limit)
    if not _identifier(type_name):
        error = "type_name must be a public RNA identifier of at most 128 characters, not a path or expression."
    if error:
        return skill_error("Invalid RNA type query", error)
    try:
        import bpy

        rna = _rna_type(bpy, type_name)
        if rna is None:
            return skill_error(
                "RNA type unavailable", "Search the current runtime for an exact type identifier.", **_context(bpy)
            )
        needle = query.casefold()
        properties = [
            prop
            for prop in rna.properties
            if _identifier(prop.identifier)
            and prop.identifier != "rna_type"
            and (
                not needle
                or needle in prop.identifier.casefold()
                or needle in _text(getattr(prop, "name", ""), 128).casefold()
            )
        ]
        properties.sort(key=lambda prop: prop.identifier)
        page = _bounded_page(_property_metadata(prop) for prop in properties[offset : offset + limit])
        return skill_success(
            "RNA type properties described",
            **_context(bpy),
            type_name=type_name,
            properties=page,
            **_pagination(len(properties), offset, limit, len(page)),
            prompt="Use get_modifier_values for exact modifier readback. RNA metadata is not mutation support or permission.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported.")
    except Exception as exc:
        return skill_exception(exc, message="RNA property metadata unavailable")


def _scalar_value(value: Any, kind: str) -> Any:
    if kind == "BOOLEAN" and type(value) is bool:
        return value
    if kind == "INT" and type(value) is int:
        return value
    if kind == "FLOAT" and type(value) in (float, int) and math.isfinite(value):
        return value
    if kind in ("STRING", "ENUM") and isinstance(value, str) and len(value) <= _MAX_STRING:
        return value
    raise ValueError("Value is not a bounded finite scalar of its RNA type.")


def _read_property(modifier: Any, identifier: str) -> dict:
    prop = modifier.bl_rna.properties.get(identifier)
    if prop is None:
        return {"identifier": identifier, "status": "unavailable", "reason": "property_not_found"}
    kind = prop.type
    row = {"identifier": identifier, "type": kind}
    if kind not in _SCALAR_TYPES:
        return dict(row, status="unsupported", reason="pointer_collection_or_other_type_not_read")
    if getattr(prop, "is_runtime", False):
        return dict(row, status="unsupported", reason="runtime_property_callback_not_read")
    is_array = bool(getattr(prop, "is_array", False))
    if is_array and not 0 < getattr(prop, "array_length", 0) <= _MAX_ARRAY:
        return dict(row, status="unsupported", reason="array_length_out_of_bounds")
    try:
        value = getattr(modifier, identifier)
        if is_array:
            values = list(islice(iter(value), _MAX_ARRAY + 1))
            if len(values) != prop.array_length:
                raise ValueError("RNA array length changed during readback.")
            value = [_scalar_value(item, kind) for item in values]
        elif kind == "ENUM" and getattr(prop, "is_enum_flag", False):
            if not isinstance(value, (set, frozenset)) or len(value) > _MAX_ARRAY:
                raise ValueError("Enum flags are not a bounded set.")
            value = sorted(_scalar_value(item, kind) for item in value)
        else:
            value = _scalar_value(value, kind)
        return dict(row, status="available", value=value)
    except Exception:
        # Do not serialize repr(value), a Python wrapper, or callback exception text.
        return dict(row, status="unavailable", reason="value_read_failed_or_out_of_bounds")


def get_modifier_values(object_name: str, modifier_name: str, properties: list[str]) -> dict:
    """Read explicit built-in scalar/array modifier properties; never follow links."""
    for label, name in (("object_name", object_name), ("modifier_name", modifier_name)):
        if not isinstance(name, str) or not name.strip() or len(name) > 256 or any(ord(c) < 32 for c in name):
            return skill_error("Invalid modifier query", f"{label} must be a nonempty name of at most 256 characters.")
    if (
        not isinstance(properties, list)
        or not 1 <= len(properties) <= _MAX_PROPERTIES
        or any(not _identifier(name) or name == "rna_type" for name in properties)
        or len(set(properties)) != len(properties)
    ):
        return skill_error("Invalid property selection", "Pass 1 to 32 unique public property identifiers, not paths.")
    try:
        import bpy

        obj = bpy.data.objects.get(object_name)
        if obj is None:
            return skill_error(
                "Object unavailable", "Use blender-scene list_objects to choose an exact object.", **_context(bpy)
            )
        modifier = obj.modifiers.get(modifier_name)
        if modifier is None:
            return skill_error(
                "Modifier unavailable", "Use blender-mesh list_modifiers to choose an exact modifier.", **_context(bpy)
            )
        inspected = {}
        used = 2
        omitted = {
            name: {"identifier": name, "status": "unavailable", "reason": "response_budget_exceeded"}
            for name in properties
        }
        reserved = sum(_byte_length({name: row}) + 2 for name, row in omitted.items())
        for name in properties:
            reserved -= _byte_length({name: omitted[name]}) + 2
            row = _read_property(modifier, name)
            if used + _byte_length({name: row}) + 2 + reserved > _PAGE_BYTES:
                row = omitted[name]
            inspected[name] = row
            used += _byte_length({name: row}) + 2
        return skill_success(
            "Modifier properties inspected; check each property's status",
            **_context(bpy),
            object_name=obj.name,
            modifier_name=modifier.name,
            type_name=modifier.bl_rna.identifier,
            properties=inspected,
            prompt="Only available values are readback evidence; unsupported/unavailable entries do not verify a postcondition.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported.")
    except Exception as exc:
        return skill_exception(exc, message="Modifier readback unavailable")
