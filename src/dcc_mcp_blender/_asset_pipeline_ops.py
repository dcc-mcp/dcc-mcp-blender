"""Blender asset validation and local publish pipeline helpers."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from dcc_mcp_core.skill import skill_error, skill_exception, skill_success

ASSET_METADATA_KEY = "dcc_mcp_asset_metadata"
PROJECT_CONTEXT_KEY = "dcc_mcp_project_context"
SUPPORTED_EXPORT_FORMATS = {"fbx", "obj", "gltf", "glb", "usd", "usda", "usdc", "abc", "blend"}

_REPORTS: Dict[str, Dict[str, Any]] = {}
_LATEST_REPORT_ID: Optional[str] = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _issue(
    code: str,
    severity: str,
    message: str,
    object_name: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    item = {
        "code": code,
        "severity": severity,
        "message": message,
    }
    if object_name is not None:
        item["object_name"] = object_name
    if details:
        item["details"] = details
    return item


def _issue_counts(issues: List[Dict[str, Any]]) -> Dict[str, int]:
    counts = {"info": 0, "warning": 0, "error": 0}
    for issue in issues:
        severity = issue.get("severity", "info")
        counts[severity] = counts.get(severity, 0) + 1
    return counts


def _make_report(
    report_type: str,
    issues: List[Dict[str, Any]],
    checked_objects: Optional[List[str]] = None,
    context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    global _LATEST_REPORT_ID

    counts = _issue_counts(issues)
    report = {
        "report_id": str(uuid.uuid4()),
        "report_type": report_type,
        "created_at": _now(),
        "passed": counts.get("error", 0) == 0,
        "counts": counts,
        "issues": issues,
        "checked_objects": checked_objects or [],
        "context": context or {},
    }
    _REPORTS[report["report_id"]] = report
    _LATEST_REPORT_ID = report["report_id"]
    return report


def _len_or_zero(value: Any) -> int:
    try:
        return len(value)
    except Exception:
        return 0


def _iter_or_empty(value: Any) -> Iterable[Any]:
    if value is None:
        return []
    try:
        return list(value)
    except TypeError:
        return []


def _objects(bpy) -> List[Any]:
    return list(_iter_or_empty(getattr(bpy.data, "objects", [])))


def _object_named(bpy, object_name: str) -> Any:
    return bpy.data.objects.get(object_name)


def _object_name(obj: Any) -> str:
    return str(getattr(obj, "name", ""))


def _objects_for_names(bpy, object_names: Optional[List[str]]) -> Tuple[List[Any], List[Dict[str, Any]]]:
    if not object_names:
        return _objects(bpy), []

    found = []
    issues = []
    for name in object_names:
        obj = _object_named(bpy, name)
        if obj is None:
            issues.append(_issue("OBJECT_MISSING", "error", f"Object not found: {name}", object_name=name))
            continue
        found.append(obj)
    return found, issues


def _mesh_stats(obj: Any) -> Dict[str, int]:
    data = getattr(obj, "data", None)
    return {
        "vertices": _len_or_zero(getattr(data, "vertices", [])),
        "edges": _len_or_zero(getattr(data, "edges", [])),
        "polygons": _len_or_zero(getattr(data, "polygons", [])),
        "materials": _len_or_zero(getattr(data, "materials", [])),
        "uv_layers": _len_or_zero(getattr(data, "uv_layers", [])),
    }


def _material_slots(obj: Any) -> List[Any]:
    return list(_iter_or_empty(getattr(obj, "material_slots", [])))


def _object_materials(obj: Any) -> List[Any]:
    data = getattr(obj, "data", None)
    materials = list(_iter_or_empty(getattr(data, "materials", [])))
    if materials:
        return materials
    return [getattr(slot, "material", None) for slot in _material_slots(obj)]


def _custom_get(target: Any, key: str, default: Any = None) -> Any:
    getter = getattr(target, "get", None)
    if callable(getter):
        return getter(key, default)
    try:
        return target[key]
    except Exception:
        return default


def _custom_set(target: Any, key: str, value: Any) -> None:
    try:
        target[key] = value
    except Exception:
        setattr(target, key, value)


def _custom_delete(target: Any, key: str) -> None:
    try:
        del target[key]
    except Exception:
        if hasattr(target, key):
            delattr(target, key)


def _load_json_prop(target: Any, key: str) -> Dict[str, Any]:
    raw = _custom_get(target, key, None)
    if not raw:
        return {}
    if isinstance(raw, dict):
        return dict(raw)
    try:
        data = json.loads(str(raw))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _store_json_prop(target: Any, key: str, value: Dict[str, Any]) -> None:
    _custom_set(target, key, json.dumps(value, sort_keys=True))


def _visibility(obj: Any) -> Dict[str, Any]:
    hidden = None
    hide_get = getattr(obj, "hide_get", None)
    if callable(hide_get):
        try:
            hidden = bool(hide_get())
        except Exception:
            hidden = None
    if hidden is None:
        hidden = bool(getattr(obj, "hide_viewport", False))
    return {
        "hidden": hidden,
        "hide_viewport": bool(getattr(obj, "hide_viewport", False)),
        "hide_render": bool(getattr(obj, "hide_render", False)),
    }


def _object_summary(obj: Any) -> Dict[str, Any]:
    return {
        "name": _object_name(obj),
        "type": getattr(obj, "type", None),
        "mesh": _mesh_stats(obj) if getattr(obj, "type", None) == "MESH" else {},
        "visibility": _visibility(obj),
        "metadata": _load_json_prop(obj, ASSET_METADATA_KEY),
    }


def _safe_json_path(output_path: str) -> Tuple[Optional[Path], Optional[dict]]:
    raw = str(output_path or "").strip()
    if not raw:
        return None, skill_error("Missing output path", "Pass a local JSON output path.")
    if "://" in raw or raw.startswith("\\\\"):
        return None, skill_error("Unsafe output path", "Use a local filesystem path, not a URL or UNC path.")
    path = Path(raw).expanduser()
    if path.suffix.lower() != ".json":
        path = path.with_suffix(".json")
    return path.resolve(), None


def _safe_output_dir(output_dir: str) -> Tuple[Optional[Path], Optional[dict]]:
    raw = str(output_dir or "").strip()
    if not raw:
        return None, skill_error("Missing output directory", "Pass a local output directory.")
    if "://" in raw or raw.startswith("\\\\"):
        return None, skill_error("Unsafe output directory", "Use a local filesystem directory, not a URL or UNC path.")
    return Path(raw).expanduser().resolve(), None


def _project_context(scene: Any) -> Dict[str, Any]:
    context = _load_json_prop(scene, PROJECT_CONTEXT_KEY)
    render = getattr(scene, "render", None)
    unit_settings = getattr(scene, "unit_settings", None)
    return {
        "name": context.get("name"),
        "root": context.get("root"),
        "unit_scale": context.get("unit_scale", getattr(unit_settings, "scale_length", None)),
        "frame_rate": context.get("frame_rate", getattr(render, "fps", None)),
        "metadata": context.get("metadata", {}),
    }


def validate_mesh(object_name: str, rules: Optional[Dict[str, Any]] = None) -> dict:
    """Validate one mesh object and store a structured report."""
    try:
        import bpy

        rules = rules or {}
        obj = _object_named(bpy, object_name)
        issues: List[Dict[str, Any]] = []
        if obj is None:
            issues.append(_issue("OBJECT_MISSING", "error", f"Object not found: {object_name}", object_name))
            report = _make_report("mesh", issues, [object_name], {"rules": rules})
            return skill_success("Mesh validation completed", report=report)
        if getattr(obj, "type", None) != "MESH":
            issues.append(_issue("OBJECT_NOT_MESH", "error", f"{object_name} is not a mesh object.", object_name))
            report = _make_report("mesh", issues, [object_name], {"rules": rules})
            return skill_success("Mesh validation completed", report=report)

        stats = _mesh_stats(obj)
        if stats["vertices"] == 0:
            issues.append(_issue("MESH_NO_VERTICES", "error", "Mesh has no vertices.", object_name))
        if stats["polygons"] == 0:
            issues.append(_issue("MESH_NO_FACES", "warning", "Mesh has no polygons.", object_name))
        max_polygons = rules.get("max_polygons")
        if max_polygons is not None and stats["polygons"] > int(max_polygons):
            issues.append(
                _issue(
                    "MESH_TOO_MANY_POLYGONS",
                    "warning",
                    f"Mesh has {stats['polygons']} polygons, above limit {max_polygons}.",
                    object_name,
                    {"polygons": stats["polygons"], "max_polygons": int(max_polygons)},
                )
            )
        if rules.get("require_uvs") and stats["uv_layers"] == 0:
            issues.append(_issue("MESH_MISSING_UVS", "warning", "Mesh has no UV layers.", object_name))
        if rules.get("require_materials") and stats["materials"] == 0:
            issues.append(_issue("MESH_MISSING_MATERIALS", "warning", "Mesh has no assigned materials.", object_name))

        if not issues:
            issues.append(_issue("MESH_VALID", "info", "Mesh validation passed.", object_name, stats))
        report = _make_report("mesh", issues, [object_name], {"rules": rules, "mesh": stats})
        return skill_success("Mesh validation completed", report=report)
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to validate mesh {object_name}")


def validate_materials(object_names: Optional[List[str]] = None, rules: Optional[Dict[str, Any]] = None) -> dict:
    """Validate material assignments for scene objects."""
    try:
        import bpy

        rules = rules or {}
        objects, issues = _objects_for_names(bpy, object_names)
        for obj in objects:
            name = _object_name(obj)
            if getattr(obj, "type", None) != "MESH":
                continue
            materials = _object_materials(obj)
            assigned = [material for material in materials if material is not None]
            if rules.get("require_materials", True) and not assigned:
                issues.append(_issue("MATERIALS_MISSING", "warning", "Mesh has no assigned materials.", name))
            for index, material in enumerate(materials):
                if material is None:
                    issues.append(
                        _issue(
                            "MATERIAL_SLOT_EMPTY", "warning", f"Material slot {index} is empty.", name, {"slot": index}
                        )
                    )
                    continue
                if rules.get("require_nodes") and not bool(getattr(material, "use_nodes", False)):
                    issues.append(
                        _issue(
                            "MATERIAL_NODES_DISABLED",
                            "warning",
                            f"Material {getattr(material, 'name', '<unnamed>')} does not use nodes.",
                            name,
                        )
                    )
        if not issues:
            issues.append(_issue("MATERIALS_VALID", "info", "Material validation passed."))
        report = _make_report("materials", issues, [_object_name(obj) for obj in objects], {"rules": rules})
        return skill_success("Material validation completed", report=report)
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message="Failed to validate materials")


def validate_animation(
    object_names: Optional[List[str]] = None,
    frame_range: Optional[List[int]] = None,
    rules: Optional[Dict[str, Any]] = None,
) -> dict:
    """Validate animation data and frame ranges."""
    try:
        import bpy

        rules = rules or {}
        objects, issues = _objects_for_names(bpy, object_names)
        scene = bpy.context.scene
        start = int(frame_range[0]) if frame_range else int(getattr(scene, "frame_start", 1))
        end = int(frame_range[1]) if frame_range and len(frame_range) > 1 else int(getattr(scene, "frame_end", start))
        if start > end:
            issues.append(_issue("ANIMATION_FRAME_RANGE_INVALID", "error", "Frame range start is after end."))

        require_keyframes = bool(rules.get("require_keyframes", False))
        for obj in objects:
            name = _object_name(obj)
            action = getattr(getattr(obj, "animation_data", None), "action", None)
            fcurves = list(_iter_or_empty(getattr(action, "fcurves", []))) if action is not None else []
            keyframe_count = sum(_len_or_zero(getattr(fcurve, "keyframe_points", [])) for fcurve in fcurves)
            if require_keyframes and keyframe_count == 0:
                issues.append(_issue("ANIMATION_MISSING_KEYFRAMES", "warning", "Object has no keyframes.", name))
            for fcurve in fcurves:
                for point in _iter_or_empty(getattr(fcurve, "keyframe_points", [])):
                    co = getattr(point, "co", [0])
                    try:
                        frame = float(co[0])
                    except Exception:
                        frame = 0.0
                    if frame < start or frame > end:
                        issues.append(
                            _issue(
                                "ANIMATION_KEYFRAME_OUT_OF_RANGE",
                                "warning",
                                f"Keyframe at frame {frame:g} is outside the validation range.",
                                name,
                                {"frame": frame, "frame_start": start, "frame_end": end},
                            )
                        )
        if not issues:
            issues.append(_issue("ANIMATION_VALID", "info", "Animation validation passed."))
        report = _make_report(
            "animation",
            issues,
            [_object_name(obj) for obj in objects],
            {"frame_start": start, "frame_end": end, "rules": rules},
        )
        return skill_success("Animation validation completed", report=report)
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message="Failed to validate animation")


def validate_export_readiness(
    object_names: List[str],
    target_format: str,
    preset_name: Optional[str] = None,
    rules: Optional[Dict[str, Any]] = None,
) -> dict:
    """Validate selected objects for local export/publish readiness."""
    try:
        import bpy

        rules = rules or {}
        target = str(target_format).lower().lstrip(".")
        objects, issues = _objects_for_names(bpy, object_names)
        if target not in SUPPORTED_EXPORT_FORMATS:
            issues.append(
                _issue(
                    "EXPORT_FORMAT_UNSUPPORTED",
                    "error",
                    f"Unsupported export format: {target_format}",
                    details={"supported_formats": sorted(SUPPORTED_EXPORT_FORMATS)},
                )
            )
        for obj in objects:
            name = _object_name(obj)
            if not name.strip():
                issues.append(_issue("EXPORT_OBJECT_NAME_EMPTY", "error", "Object has an empty name."))
            if _visibility(obj).get("hide_render") and rules.get("warn_hidden_render", True):
                issues.append(_issue("EXPORT_OBJECT_HIDE_RENDER", "warning", "Object is hidden from renders.", name))
            if getattr(obj, "type", None) == "MESH":
                stats = _mesh_stats(obj)
                if stats["vertices"] == 0:
                    issues.append(_issue("EXPORT_MESH_EMPTY", "error", "Mesh has no vertices.", name))
        if not objects and not issues:
            issues.append(_issue("EXPORT_NO_OBJECTS", "error", "No objects were selected for export validation."))
        if not issues:
            issues.append(_issue("EXPORT_READY", "info", "Export readiness validation passed."))
        report = _make_report(
            "export_readiness",
            issues,
            [_object_name(obj) for obj in objects]
            + [name for name in object_names if _object_named(bpy, name) is None],
            {"target_format": target, "preset_name": preset_name, "rules": rules},
        )
        return skill_success("Export readiness validation completed", report=report)
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message="Failed to validate export readiness")


def run_scene_checks(checks: Optional[List[str]] = None, object_names: Optional[List[str]] = None) -> dict:
    """Run focused scene checks and store an aggregate report."""
    try:
        import bpy

        selected_checks = checks or ["objects", "meshes", "materials", "animation"]
        objects, issues = _objects_for_names(bpy, object_names)
        if "objects" in selected_checks and not objects:
            issues.append(_issue("SCENE_NO_OBJECTS", "warning", "Scene has no objects to validate."))
        if "meshes" in selected_checks:
            for obj in objects:
                if getattr(obj, "type", None) == "MESH":
                    stats = _mesh_stats(obj)
                    if stats["vertices"] == 0:
                        issues.append(_issue("MESH_NO_VERTICES", "error", "Mesh has no vertices.", _object_name(obj)))
        if "materials" in selected_checks:
            for obj in objects:
                if getattr(obj, "type", None) == "MESH" and not [m for m in _object_materials(obj) if m is not None]:
                    issues.append(
                        _issue("MATERIALS_MISSING", "warning", "Mesh has no assigned materials.", _object_name(obj))
                    )
        if "animation" in selected_checks:
            scene = bpy.context.scene
            if int(getattr(scene, "frame_start", 1)) > int(getattr(scene, "frame_end", 1)):
                issues.append(_issue("ANIMATION_FRAME_RANGE_INVALID", "error", "Scene frame range start is after end."))
        unknown = sorted(set(selected_checks) - {"objects", "meshes", "materials", "animation"})
        for check in unknown:
            issues.append(
                _issue("SCENE_CHECK_UNKNOWN", "warning", f"Unknown scene check: {check}", details={"check": check})
            )
        if not issues:
            issues.append(_issue("SCENE_VALID", "info", "Scene checks passed."))
        report = _make_report("scene", issues, [_object_name(obj) for obj in objects], {"checks": selected_checks})
        return skill_success("Scene checks completed", report=report)
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message="Failed to run scene checks")


def get_validation_report(report_id: Optional[str] = None) -> dict:
    """Return a stored validation report by id, or the latest report."""
    target_id = report_id or _LATEST_REPORT_ID
    if not target_id:
        return skill_error("No validation report available", "Run a validation tool before requesting a report.")
    report = _REPORTS.get(target_id)
    if report is None:
        return skill_error(f"Validation report not found: {target_id}", "No report exists for that id.")
    return skill_success("Validation report retrieved", report=report)


def get_asset_metadata(object_name: Optional[str] = None) -> dict:
    """Return object asset metadata and project context."""
    try:
        import bpy

        if object_name:
            obj = _object_named(bpy, object_name)
            if obj is None:
                return skill_error(f"Object not found: {object_name}", f"No object named '{object_name}'.")
            objects = [obj]
        else:
            objects = _objects(bpy)
        return skill_success(
            "Asset metadata retrieved",
            project_context=_project_context(bpy.context.scene),
            assets=[
                {"object_name": _object_name(obj), "metadata": _load_json_prop(obj, ASSET_METADATA_KEY)}
                for obj in objects
            ],
            count=len(objects),
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message="Failed to get asset metadata")


def tag_asset_metadata(object_name: str, metadata: Dict[str, Any]) -> dict:
    """Merge asset metadata into one Blender object."""
    try:
        import bpy

        obj = _object_named(bpy, object_name)
        if obj is None:
            return skill_error(f"Object not found: {object_name}", f"No object named '{object_name}'.")
        if not isinstance(metadata, dict):
            return skill_error("Invalid metadata", "metadata must be an object.")
        current = _load_json_prop(obj, ASSET_METADATA_KEY)
        current.update(metadata)
        _store_json_prop(obj, ASSET_METADATA_KEY, current)
        return skill_success("Asset metadata updated", object_name=object_name, metadata=current)
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to tag asset metadata for {object_name}")


def clear_asset_metadata(object_name: str, keys: Optional[List[str]] = None) -> dict:
    """Clear selected asset metadata keys, or all metadata for one object."""
    try:
        import bpy

        obj = _object_named(bpy, object_name)
        if obj is None:
            return skill_error(f"Object not found: {object_name}", f"No object named '{object_name}'.")
        current = _load_json_prop(obj, ASSET_METADATA_KEY)
        if keys:
            removed = [key for key in keys if key in current]
            for key in keys:
                current.pop(key, None)
            _store_json_prop(obj, ASSET_METADATA_KEY, current)
        else:
            removed = sorted(current)
            _custom_delete(obj, ASSET_METADATA_KEY)
            current = {}
        return skill_success("Asset metadata cleared", object_name=object_name, removed=removed, metadata=current)
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to clear asset metadata for {object_name}")


def set_project_context(
    name: Optional[str] = None,
    root: Optional[str] = None,
    unit_scale: Optional[float] = None,
    frame_rate: Optional[int] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> dict:
    """Store local project context on the current scene."""
    try:
        import bpy

        scene = bpy.context.scene
        current = _load_json_prop(scene, PROJECT_CONTEXT_KEY)
        if name is not None:
            current["name"] = name
        if root is not None:
            current["root"] = root
        if unit_scale is not None:
            current["unit_scale"] = float(unit_scale)
            unit_settings = getattr(scene, "unit_settings", None)
            if unit_settings is not None and hasattr(unit_settings, "scale_length"):
                unit_settings.scale_length = float(unit_scale)
        if frame_rate is not None:
            current["frame_rate"] = int(frame_rate)
            render = getattr(scene, "render", None)
            if render is not None and hasattr(render, "fps"):
                render.fps = int(frame_rate)
        if metadata:
            current_metadata = current.get("metadata", {})
            current_metadata.update(metadata)
            current["metadata"] = current_metadata
        _store_json_prop(scene, PROJECT_CONTEXT_KEY, current)
        return skill_success("Project context updated", project_context=_project_context(scene))
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message="Failed to set project context")


def _manifest_payload(
    bpy, object_names: List[str], metadata: Optional[Dict[str, Any]] = None
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    objects, issues = _objects_for_names(bpy, object_names)
    payload = {
        "schema": "dcc-mcp-blender.publish-manifest.v1",
        "created_at": _now(),
        "project_context": _project_context(bpy.context.scene),
        "metadata": metadata or {},
        "assets": [_object_summary(obj) for obj in objects],
        "validation": _make_report(
            "publish_manifest",
            issues or [_issue("PUBLISH_MANIFEST_READY", "info", "Publish manifest generated.")],
            [_object_name(obj) for obj in objects],
        ),
    }
    return payload, issues


def create_publish_manifest(
    object_names: List[str], output_path: str, metadata: Optional[Dict[str, Any]] = None
) -> dict:
    """Write a local JSON publish manifest for selected objects."""
    try:
        import bpy

        path, error = _safe_json_path(output_path)
        if error:
            return error
        payload, issues = _manifest_payload(bpy, object_names, metadata)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        return skill_success(
            "Publish manifest created",
            output_path=str(path),
            issue_count=len(issues),
            asset_count=len(payload["assets"]),
            manifest=payload,
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message="Failed to create publish manifest")


def prepare_publish_package(object_names: List[str], output_dir: str, preset_name: Optional[str] = None) -> dict:
    """Create a local publish package directory with a manifest."""
    try:
        import bpy

        package_dir, error = _safe_output_dir(output_dir)
        if error:
            return error
        package_dir.mkdir(parents=True, exist_ok=True)
        payload, issues = _manifest_payload(bpy, object_names, {"preset_name": preset_name} if preset_name else {})
        manifest_path = package_dir / "publish_manifest.json"
        manifest_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        readme_path = package_dir / "README.txt"
        readme_path.write_text("Local package prepared by dcc-mcp-blender.\n", encoding="utf-8")
        return skill_success(
            "Publish package prepared",
            output_dir=str(package_dir),
            manifest_path=str(manifest_path),
            readme_path=str(readme_path),
            issue_count=len(issues),
            asset_count=len(payload["assets"]),
            preset_name=preset_name,
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message="Failed to prepare publish package")
