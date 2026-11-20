"""Asset build contracts and deterministic scene snapshots for Blender.

The regular pipeline tools operate on individual objects and files.  This
module adds the contract between those operations: a small, scene-stored
manifest describes the intended parts, controls, actions, references, and
delivery outputs.  Validation can then check the current Blender scene
against that contract before export or publish.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from dcc_mcp_core.skill import skill_error, skill_exception, skill_success

from dcc_mcp_blender._asset_pipeline_ops import (
    _custom_get,
    _issue,
    _iter_or_empty,
    _len_or_zero,
    _load_json_prop,
    _make_report,
    _mesh_stats,
    _now,
    _object_name,
    _object_named,
    _objects_for_names,
    _project_context,
    _safe_json_path,
)

BUILD_MANIFEST_KEY = "dcc_mcp_asset_build_manifest"
BUILD_MANIFEST_SCHEMA = "dcc-mcp-blender.asset-build-manifest.v1"
SNAPSHOT_SCHEMA = "dcc-mcp-blender.asset-snapshot.v1"
_MISSING = object()


def _as_float_list(value: Any, size: Optional[int] = None) -> Optional[List[float]]:
    try:
        values = [float(item) for item in value]
    except (TypeError, ValueError):
        return None
    if size is not None and len(values) != size:
        return None
    return values


def _names(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        value = [value]
    result = []
    for item in value:
        name = str(item).strip()
        if name and name not in result:
            result.append(name)
    return result


def _data_block_by_name(collection: Any, name: str) -> Any:
    getter = getattr(collection, "get", None)
    if callable(getter):
        try:
            return getter(name)
        except Exception:
            pass
    for item in _iter_or_empty(collection):
        if str(getattr(item, "name", "")) == name:
            return item
    return None


def _normalise_references(references: Any) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    result: List[Dict[str, Any]] = []
    issues: List[Dict[str, Any]] = []
    for index, reference in enumerate(references or []):
        if isinstance(reference, str):
            reference = {"path": reference}
        if not isinstance(reference, dict):
            issues.append(_issue("BUILD_REFERENCE_INVALID", "error", f"Reference {index} must be an object."))
            continue
        path = str(reference.get("path", "")).strip()
        if not path or "://" in path or path.startswith("\\\\"):
            issues.append(_issue("BUILD_REFERENCE_PATH_INVALID", "error", f"Reference {index} has an invalid path."))
            continue
        result.append(
            {
                "path": path,
                "kind": str(reference.get("kind", "reference")).strip() or "reference",
                "approved": bool(reference.get("approved", False)),
                "required": bool(reference.get("required", False)),
            }
        )
    return result, issues


def _normalise_outputs(outputs: Any) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    result: List[Dict[str, Any]] = []
    issues: List[Dict[str, Any]] = []
    for index, output in enumerate(outputs or []):
        if not isinstance(output, dict):
            issues.append(_issue("BUILD_OUTPUT_INVALID", "error", f"Output {index} must be an object."))
            continue
        path = str(output.get("path", "")).strip()
        if not path or "://" in path or path.startswith("\\\\"):
            issues.append(_issue("BUILD_OUTPUT_PATH_INVALID", "error", f"Output {index} has an invalid path."))
            continue
        result.append(
            {
                "path": path,
                "format": str(output.get("format", Path(path).suffix.lstrip(".") or "unknown")).lower(),
                "required": bool(output.get("required", True)),
            }
        )
    return result, issues


def _normalise_controls(
    controls: Any,
    armature_name: Optional[str],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    result: List[Dict[str, Any]] = []
    issues: List[Dict[str, Any]] = []
    seen = set()
    for index, control in enumerate(controls or []):
        if not isinstance(control, dict):
            issues.append(_issue("BUILD_CONTROL_INVALID", "error", f"Control {index} must be an object."))
            continue
        name = str(control.get("name", "")).strip()
        property_name = str(control.get("property", name)).strip()
        target_object = str(control.get("target_object", armature_name or "")).strip()
        try:
            minimum = float(control.get("min", 0.0))
            maximum = float(control.get("max", 1.0))
        except (TypeError, ValueError):
            minimum, maximum = 0.0, -1.0
        if not name or not property_name or not target_object or minimum >= maximum:
            issues.append(
                _issue("BUILD_CONTROL_INVALID", "error", f"Control {index} has invalid name, target, or range.")
            )
            continue
        if name in seen:
            issues.append(_issue("BUILD_CONTROL_DUPLICATE", "error", f"Control is declared more than once: {name}"))
            continue
        seen.add(name)
        result.append(
            {
                "name": name,
                "property": property_name,
                "target_object": target_object,
                "min": minimum,
                "max": maximum,
                "required": bool(control.get("required", True)),
            }
        )
    return result, issues


def _object_bounds(obj: Any) -> Optional[List[List[float]]]:
    raw = getattr(obj, "bound_box", None)
    if raw is None:
        return None
    points = []
    for point in _iter_or_empty(raw):
        converted = _as_float_list(point, 3)
        if converted is not None:
            points.append(converted)
    return points or None


def _object_snapshot(obj: Any) -> Dict[str, Any]:
    data = getattr(obj, "data", None)
    materials = [str(getattr(item, "name", "")) for item in _iter_or_empty(getattr(data, "materials", []))]
    modifiers = [
        {"name": str(getattr(item, "name", "")), "type": str(getattr(item, "type", ""))}
        for item in _iter_or_empty(getattr(obj, "modifiers", []))
    ]
    parent = getattr(obj, "parent", None)
    return {
        "name": _object_name(obj),
        "type": str(getattr(obj, "type", "")),
        "parent": str(getattr(parent, "name", "")) if parent is not None else None,
        "mesh": _mesh_stats(obj) if getattr(obj, "type", None) == "MESH" else {},
        "materials": sorted(name for name in materials if name),
        "modifiers": modifiers,
        "bounds": _object_bounds(obj),
        "transform": {
            "location": _as_float_list(getattr(obj, "location", []), 3),
            "rotation": _as_float_list(getattr(obj, "rotation_euler", []), 3),
            "scale": _as_float_list(getattr(obj, "scale", []), 3),
        },
    }


def _scene_snapshot(bpy: Any, object_names: Optional[List[str]] = None) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    objects, issues = _objects_for_names(bpy, object_names)
    objects = sorted(objects, key=lambda item: _object_name(item))
    armatures = []
    for obj in objects:
        if getattr(obj, "type", None) != "ARMATURE":
            continue
        bones = []
        for bone in _iter_or_empty(getattr(getattr(obj, "data", None), "bones", [])):
            parent = getattr(bone, "parent", None)
            bones.append(
                {
                    "name": str(getattr(bone, "name", "")),
                    "parent": str(getattr(parent, "name", "")) if parent is not None else None,
                }
            )
        armatures.append({"name": _object_name(obj), "bones": sorted(bones, key=lambda item: item["name"])})

    actions = []
    for action in _iter_or_empty(getattr(getattr(bpy, "data", None), "actions", [])):
        frame_range = _as_float_list(getattr(action, "frame_range", []), 2)
        actions.append(
            {
                "name": str(getattr(action, "name", "")),
                "frame_range": frame_range,
                "fcurve_count": _len_or_zero(getattr(action, "fcurves", [])),
            }
        )

    scene = getattr(getattr(bpy, "context", None), "scene", None)
    render = getattr(scene, "render", None)
    units = getattr(scene, "unit_settings", None)
    snapshot = {
        "schema": SNAPSHOT_SCHEMA,
        "scene": {
            "name": str(getattr(scene, "name", "")),
            "filepath": str(getattr(getattr(bpy, "data", None), "filepath", "") or ""),
            "frame_start": int(getattr(scene, "frame_start", 1)),
            "frame_end": int(getattr(scene, "frame_end", 1)),
            "frame_current": int(getattr(scene, "frame_current", 1)),
            "fps": int(getattr(render, "fps", 0)),
            "unit_scale": float(getattr(units, "scale_length", 0.0)),
            "render_engine": str(getattr(render, "engine", "")),
        },
        "objects": [_object_snapshot(obj) for obj in objects],
        "armatures": sorted(armatures, key=lambda item: item["name"]),
        "actions": sorted(actions, key=lambda item: item["name"]),
    }
    canonical = json.dumps(snapshot, sort_keys=True, separators=(",", ":"))
    snapshot["snapshot_hash"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return snapshot, issues


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def capture_asset_snapshot(object_names: Optional[List[str]] = None, output_path: Optional[str] = None) -> dict:
    """Capture a deterministic, lightweight snapshot of the active scene."""
    try:
        import bpy

        snapshot, issues = _scene_snapshot(bpy, _names(object_names))
        errors = [item for item in issues if item.get("severity") == "error"]
        if errors:
            return skill_error("Could not capture asset snapshot", "One or more objects were not found.", issues=issues)
        saved_path = None
        if output_path:
            path, error = _safe_json_path(output_path)
            if error:
                return error
            _write_json(path, snapshot)
            saved_path = str(path)
        return skill_success(
            "Asset snapshot captured",
            snapshot=snapshot,
            snapshot_hash=snapshot["snapshot_hash"],
            output_path=saved_path,
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message="Failed to capture asset snapshot")


def create_asset_build_manifest(
    asset_name: str,
    object_names: List[str],
    output_path: Optional[str] = None,
    armature_name: Optional[str] = None,
    controls: Optional[List[Dict[str, Any]]] = None,
    action_names: Optional[List[str]] = None,
    references: Optional[List[Any]] = None,
    outputs: Optional[List[Dict[str, Any]]] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> dict:
    """Create and store the machine-readable contract for a Blender asset."""
    try:
        import bpy

        clean_name = str(asset_name or "").strip()
        names = _names(object_names)
        if not clean_name or not names:
            return skill_error("Invalid asset build manifest", "asset_name and object_names are required.")
        controls_result, control_issues = _normalise_controls(controls, armature_name)
        references_result, reference_issues = _normalise_references(references)
        outputs_result, output_issues = _normalise_outputs(outputs)
        definition_issues = control_issues + reference_issues + output_issues
        if definition_issues:
            return skill_error(
                "Invalid asset build manifest", "Manifest definition failed validation.", issues=definition_issues
            )

        snapshot, snapshot_issues = _scene_snapshot(bpy, names)
        if any(item.get("severity") == "error" for item in snapshot_issues):
            return skill_error(
                "Invalid asset build manifest",
                "All declared object_names must exist in the scene.",
                issues=snapshot_issues,
            )
        manifest = {
            "schema": BUILD_MANIFEST_SCHEMA,
            "manifest_id": str(uuid.uuid4()),
            "created_at": _now(),
            "asset_name": clean_name,
            "scene_path": str(getattr(bpy.data, "filepath", "") or ""),
            "project_context": _project_context(bpy.context.scene),
            "object_names": names,
            "armature_name": str(armature_name).strip() if armature_name else None,
            "controls": controls_result,
            "action_names": _names(action_names),
            "references": references_result,
            "outputs": outputs_result,
            "metadata": dict(metadata or {}),
            "snapshot": snapshot,
        }
        # The manifest is intentionally kept on the scene so a reopened blend
        # retains the contract even when the external JSON was not supplied.
        scene = bpy.context.scene
        scene[BUILD_MANIFEST_KEY] = json.dumps(manifest, sort_keys=True)
        saved_path = None
        if output_path:
            path, error = _safe_json_path(output_path)
            if error:
                return error
            _write_json(path, manifest)
            saved_path = str(path)
        return skill_success(
            "Asset build manifest created",
            manifest=manifest,
            manifest_id=manifest["manifest_id"],
            output_path=saved_path,
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message="Failed to create asset build manifest")


def _load_manifest(
    bpy: Any, manifest_path: Optional[str], manifest: Optional[Dict[str, Any]]
) -> Tuple[Optional[Dict[str, Any]], Optional[dict]]:
    if manifest is not None:
        if not isinstance(manifest, dict):
            return None, skill_error("Invalid asset build manifest", "manifest must be an object.")
        return dict(manifest), None
    if manifest_path:
        path, error = _safe_json_path(manifest_path)
        if error:
            return None, error
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None, skill_error("Manifest not found", f"No manifest exists at {path}.")
        except (OSError, json.JSONDecodeError) as exc:
            return None, skill_error("Manifest unreadable", str(exc))
        if not isinstance(payload, dict):
            return None, skill_error("Invalid asset build manifest", "The JSON root must be an object.")
        return payload, None
    stored = _load_json_prop(bpy.context.scene, BUILD_MANIFEST_KEY)
    if not stored:
        return None, skill_error("No asset build manifest", "Create a manifest or pass manifest_path first.")
    return stored, None


def _validate_action_names(bpy: Any, action_names: List[str], issues: List[Dict[str, Any]]) -> None:
    actions = getattr(getattr(bpy, "data", None), "actions", [])
    for name in action_names:
        if _data_block_by_name(actions, name) is None:
            issues.append(_issue("BUILD_ACTION_MISSING", "error", f"Action not found: {name}"))


def validate_asset_build_manifest(
    manifest_path: Optional[str] = None,
    manifest: Optional[Dict[str, Any]] = None,
    compare_snapshot: bool = False,
    strict_snapshot: bool = False,
) -> dict:
    """Validate the active Blender scene against an asset build manifest."""
    try:
        import bpy

        payload, error = _load_manifest(bpy, manifest_path, manifest)
        if error:
            return error
        assert payload is not None
        issues: List[Dict[str, Any]] = []
        if payload.get("schema") != BUILD_MANIFEST_SCHEMA:
            issues.append(_issue("BUILD_SCHEMA_UNSUPPORTED", "error", "Unsupported asset build manifest schema."))
        object_names = _names(payload.get("object_names"))
        objects, object_issues = _objects_for_names(bpy, object_names)
        issues.extend(object_issues)

        armature_name = str(payload.get("armature_name") or "").strip()
        if armature_name:
            armature = _object_named(bpy, armature_name)
            if armature is None:
                issues.append(_issue("BUILD_ARMATURE_MISSING", "error", f"Armature not found: {armature_name}"))
            elif getattr(armature, "type", None) != "ARMATURE":
                issues.append(_issue("BUILD_ARMATURE_INVALID", "error", f"Object is not an armature: {armature_name}"))

        for control in payload.get("controls", []) or []:
            if not isinstance(control, dict):
                issues.append(_issue("BUILD_CONTROL_INVALID", "error", "Control entry must be an object."))
                continue
            target_name = str(control.get("target_object") or armature_name).strip()
            property_name = str(control.get("property") or control.get("name") or "").strip()
            target = _object_named(bpy, target_name)
            if target is None:
                issues.append(
                    _issue("BUILD_CONTROL_TARGET_MISSING", "error", f"Control target not found: {target_name}")
                )
                continue
            value = _custom_get(target, property_name, _MISSING)
            if value is _MISSING:
                severity = "error" if bool(control.get("required", True)) else "warning"
                issues.append(
                    _issue(
                        "BUILD_CONTROL_PROPERTY_MISSING",
                        severity,
                        f"Control property not found: {property_name}",
                        target_name,
                    )
                )
                continue
            try:
                numeric = float(value)
                minimum = float(control.get("min", 0.0))
                maximum = float(control.get("max", 1.0))
            except (TypeError, ValueError):
                issues.append(
                    _issue(
                        "BUILD_CONTROL_VALUE_INVALID",
                        "error",
                        f"Control value is not numeric: {property_name}",
                        target_name,
                    )
                )
                continue
            if numeric < minimum or numeric > maximum:
                issues.append(
                    _issue(
                        "BUILD_CONTROL_OUT_OF_RANGE",
                        "error",
                        f"Control {property_name} is outside [{minimum:g}, {maximum:g}].",
                        target_name,
                        {"value": numeric, "min": minimum, "max": maximum},
                    )
                )

        _validate_action_names(bpy, _names(payload.get("action_names")), issues)

        for reference in payload.get("references", []) or []:
            if not isinstance(reference, dict):
                issues.append(_issue("BUILD_REFERENCE_INVALID", "error", "Reference entry must be an object."))
                continue
            path = Path(str(reference.get("path", ""))).expanduser()
            if not path.exists():
                severity = "error" if bool(reference.get("required", False)) else "warning"
                issues.append(_issue("BUILD_REFERENCE_MISSING", severity, f"Reference file not found: {path}"))
            if bool(reference.get("required", False)) and not bool(reference.get("approved", False)):
                issues.append(
                    _issue("BUILD_REFERENCE_UNAPPROVED", "error", f"Required reference is not approved: {path}")
                )

        for output in payload.get("outputs", []) or []:
            if not isinstance(output, dict):
                issues.append(_issue("BUILD_OUTPUT_INVALID", "error", "Output entry must be an object."))
                continue
            path = Path(str(output.get("path", ""))).expanduser()
            if not path.exists():
                severity = "error" if bool(output.get("required", True)) else "warning"
                issues.append(_issue("BUILD_OUTPUT_MISSING", severity, f"Output file not found: {path}"))

        snapshot = None
        if compare_snapshot:
            snapshot, snapshot_issues = _scene_snapshot(bpy, object_names)
            issues.extend(snapshot_issues)
            expected = (payload.get("snapshot") or {}).get("snapshot_hash")
            if expected and snapshot.get("snapshot_hash") != expected:
                issues.append(
                    _issue(
                        "BUILD_SNAPSHOT_CHANGED",
                        "error" if strict_snapshot else "warning",
                        "The current scene differs from the snapshot recorded in the manifest.",
                        details={"expected": expected, "actual": snapshot.get("snapshot_hash")},
                    )
                )

        report = _make_report(
            "asset_build",
            issues or [_issue("BUILD_CONTRACT_VALID", "info", "Asset build contract validation passed.")],
            object_names,
            {
                "manifest_id": payload.get("manifest_id"),
                "asset_name": payload.get("asset_name"),
                "compare_snapshot": compare_snapshot,
                "strict_snapshot": strict_snapshot,
                "snapshot_hash": snapshot.get("snapshot_hash") if snapshot else None,
            },
        )
        return skill_success(
            "Asset build manifest validation completed", report=report, manifest=payload, snapshot=snapshot
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message="Failed to validate asset build manifest")


def compare_asset_snapshot(baseline_path: str, object_names: Optional[List[str]] = None, strict: bool = False) -> dict:
    """Compare the active scene with a previously captured snapshot."""
    try:
        import bpy

        path, error = _safe_json_path(baseline_path)
        if error:
            return error
        try:
            baseline = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return skill_error("Snapshot not found", f"No snapshot exists at {path}.")
        except (OSError, json.JSONDecodeError) as exc:
            return skill_error("Snapshot unreadable", str(exc))
        if not isinstance(baseline, dict) or baseline.get("schema") != SNAPSHOT_SCHEMA:
            return skill_error("Invalid snapshot", "The baseline is not a supported asset snapshot.")

        current, issues = _scene_snapshot(bpy, _names(object_names))
        if any(item.get("severity") == "error" for item in issues):
            return skill_error("Could not compare asset snapshot", "One or more objects were not found.", issues=issues)

        before = {
            item["name"]: item for item in baseline.get("objects", []) if isinstance(item, dict) and item.get("name")
        }
        after = {
            item["name"]: item for item in current.get("objects", []) if isinstance(item, dict) and item.get("name")
        }
        added = sorted(set(after) - set(before))
        removed = sorted(set(before) - set(after))
        changed = sorted(name for name in set(before) & set(after) if before[name] != after[name])
        before_actions = {item.get("name") for item in baseline.get("actions", []) if isinstance(item, dict)}
        after_actions = {item.get("name") for item in current.get("actions", []) if isinstance(item, dict)}
        action_changes = {
            "added": sorted(name for name in after_actions - before_actions if name),
            "removed": sorted(name for name in before_actions - after_actions if name),
        }
        changes = {
            "objects_added": added,
            "objects_removed": removed,
            "objects_changed": changed,
            "actions": action_changes,
        }
        change_count = (
            len(added) + len(removed) + len(changed) + len(action_changes["added"]) + len(action_changes["removed"])
        )
        if change_count:
            severity = "error" if strict else "warning"
            issues.append(
                _issue(
                    "SNAPSHOT_DIFFERENCE",
                    severity,
                    "The current scene differs from the baseline snapshot.",
                    details=changes,
                )
            )
        else:
            issues.append(_issue("SNAPSHOT_MATCH", "info", "The current scene matches the baseline snapshot."))

        report = _make_report("snapshot_compare", issues, sorted(after), {"changes": changes, "strict": strict})
        return skill_success(
            "Asset snapshot comparison completed",
            passed=report["passed"],
            report=report,
            baseline_hash=baseline.get("snapshot_hash"),
            current_hash=current.get("snapshot_hash"),
            changes=changes,
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message="Failed to compare asset snapshots")
