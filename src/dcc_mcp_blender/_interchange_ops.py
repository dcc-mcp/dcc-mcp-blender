"""Shared implementations for Blender interchange, export preset, and shot export tools."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from dcc_mcp_core.skill import skill_error, skill_exception, skill_success

_PRESET_STORE_KEY = "dcc_mcp_export_presets"
_IMPORT_FORMATS = {"fbx", "obj"}
_EXPORT_FORMATS = {"fbx", "obj", "gltf", "usd", "alembic"}
_FORMAT_EXTENSIONS = {
    ".fbx": "fbx",
    ".obj": "obj",
    ".gltf": "gltf",
    ".glb": "gltf",
    ".usd": "usd",
    ".usda": "usd",
    ".usdc": "usd",
    ".abc": "alembic",
}


def _mapping(value: Mapping[str, Any] | None, label: str) -> tuple[dict[str, Any] | None, dict | None]:
    if value is None:
        return {}, None
    if not isinstance(value, Mapping):
        return None, skill_error(f"Invalid {label}", f"{label} must be an object.")
    return dict(value), None


def _path(path: str, *, must_exist: bool = False, create_parent: bool = False) -> tuple[Path | None, dict | None]:
    if not path or not str(path).strip():
        return None, skill_error("Invalid path", "path must be a non-empty file path.")
    target = Path(path).expanduser()
    if not target.is_absolute():
        target = target.resolve()
    if must_exist and not target.is_file():
        return None, skill_error(f"File not found: {target}", f"No file exists at '{target}'.")
    if create_parent:
        target.parent.mkdir(parents=True, exist_ok=True)
    return target, None


def _format_from_path(path: Path, format: str | None = None) -> tuple[str | None, dict | None]:  # noqa: A002
    if format:
        key = format.lower()
    else:
        key = _FORMAT_EXTENSIONS.get(path.suffix.lower())
    if key is None:
        return None, skill_error("Unsupported format", f"Could not infer format from extension '{path.suffix}'.")
    if key not in _IMPORT_FORMATS | _EXPORT_FORMATS:
        return None, skill_error("Unsupported format", f"Format '{key}' is not supported.")
    return key, None


def _object_names(bpy: Any) -> set[str]:
    return {obj.name for obj in bpy.data.objects}


def _objects_by_name(bpy: Any, object_names: Sequence[str] | None) -> tuple[list[Any], list[str], dict | None]:
    if object_names is None:
        return [], [], None
    if isinstance(object_names, (str, bytes)) or not object_names:
        return [], [], skill_error("Invalid object_names", "object_names must be a non-empty list when provided.")
    objects = []
    missing = []
    for name in object_names:
        obj = bpy.data.objects.get(name)
        if obj is None:
            missing.append(name)
        else:
            objects.append(obj)
    return objects, missing, None


def _select_objects(bpy: Any, object_names: Sequence[str] | None) -> tuple[bool, list[str], dict | None]:
    objects, missing, error = _objects_by_name(bpy, object_names)
    if error:
        return False, [], error
    if missing:
        return False, [], skill_error("Object not found", f"Missing object(s): {', '.join(missing)}")
    if not objects:
        return False, [], None
    try:
        bpy.ops.object.mode_set(mode="OBJECT")
    except Exception:
        pass
    bpy.ops.object.select_all(action="DESELECT")
    for obj in objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]
    return True, [obj.name for obj in objects], None


def _call_with_options(operator: Any, base: dict[str, Any], options: dict[str, Any], warnings: list[str]) -> None:
    payload = dict(base)
    payload.update(options)
    try:
        operator(**payload)
    except TypeError as exc:
        if options:
            warnings.append(f"Retried without unsupported options: {sorted(options)}")
            operator(**base)
        else:
            raise exc


def _has_nonempty_file(path: Path) -> bool:
    return path.is_file() and path.stat().st_size > 0


def _iter_mesh_objects(bpy: Any, object_names: Sequence[str] | None = None):
    allowed = set(object_names) if object_names else None
    for obj in bpy.data.objects:
        if allowed is not None and obj.name not in allowed:
            continue
        if getattr(obj, "type", None) == "MESH" and getattr(obj, "data", None) is not None:
            yield obj


def _coordinate(obj: Any, vertex: Any) -> tuple[float, float, float]:
    co = getattr(vertex, "co", vertex)
    matrix = getattr(obj, "matrix_world", None)
    if matrix is not None:
        try:
            co = matrix @ co
        except Exception:
            pass
    return (float(co[0]), float(co[1]), float(co[2]))


def _write_basic_obj(bpy: Any, path: Path, object_names: Sequence[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    vertex_offset = 1
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write("# Exported by dcc-mcp-blender\n")
        for obj in _iter_mesh_objects(bpy, object_names):
            mesh = obj.data
            vertices = list(getattr(mesh, "vertices", []))
            polygons = list(getattr(mesh, "polygons", []))
            handle.write(f"o {getattr(obj, 'name', 'Object')}\n")
            for vertex in vertices:
                x, y, z = _coordinate(obj, vertex)
                handle.write(f"v {x:.9g} {y:.9g} {z:.9g}\n")
            for polygon in polygons:
                indices = [str(vertex_offset + int(index)) for index in getattr(polygon, "vertices", [])]
                if len(indices) >= 3:
                    handle.write(f"f {' '.join(indices)}\n")
            vertex_offset += len(vertices)


def _import_by_format(
    bpy: Any,
    target: Path,
    format: str,  # noqa: A002
    options: dict[str, Any],
) -> tuple[list[str], list[str], dict | None]:
    before = _object_names(bpy)
    warnings = []
    try:
        if format == "fbx":
            _call_with_options(bpy.ops.import_scene.fbx, {"filepath": str(target)}, options, warnings)
        elif format == "obj":
            wm_import = getattr(bpy.ops.wm, "obj_import", None)
            scene_import = getattr(getattr(bpy.ops, "import_scene", None), "obj", None)
            operator = wm_import if callable(wm_import) else scene_import
            if not callable(operator):
                return (
                    [],
                    warnings,
                    skill_error("OBJ import unavailable", "No Blender OBJ import operator is available."),
                )
            _call_with_options(operator, {"filepath": str(target)}, options, warnings)
        else:
            return [], warnings, skill_error("Unsupported import format", f"Format '{format}' is not importable.")
    except Exception as exc:
        return [], warnings, skill_exception(exc, message=f"Failed to import {target}")
    after = _object_names(bpy)
    return sorted(after - before), warnings, None


def _export_by_format(
    bpy: Any,
    target: Path,
    format: str,  # noqa: A002
    object_names: Sequence[str] | None,
    options: dict[str, Any],
    frame_range: Sequence[int] | None = None,
) -> tuple[list[str], list[str], dict | None]:
    selected, selected_names, error = _select_objects(bpy, object_names)
    if error:
        return [], [], error
    warnings = []
    try:
        if format == "fbx":
            _call_with_options(
                bpy.ops.export_scene.fbx, {"filepath": str(target), "use_selection": selected}, options, warnings
            )
        elif format == "obj":
            wm_export = getattr(bpy.ops.wm, "obj_export", None)
            scene_export = getattr(getattr(bpy.ops, "export_scene", None), "obj", None)
            try:
                if callable(wm_export):
                    _call_with_options(
                        wm_export,
                        {"filepath": str(target), "export_selected_objects": selected},
                        options,
                        warnings,
                    )
                elif callable(scene_export):
                    _call_with_options(
                        scene_export, {"filepath": str(target), "use_selection": selected}, options, warnings
                    )
                else:
                    raise RuntimeError("No OBJ export operator is available")
                if not _has_nonempty_file(target):
                    raise RuntimeError("OBJ exporter produced no file")
            except Exception:
                warnings.append("Used basic OBJ fallback writer")
                _write_basic_obj(bpy, target, selected_names if selected else None)
        elif format == "gltf":
            _call_with_options(
                bpy.ops.export_scene.gltf, {"filepath": str(target), "use_selection": selected}, options, warnings
            )
        elif format == "usd":
            _call_with_options(
                bpy.ops.wm.usd_export, {"filepath": str(target), "selected_objects_only": selected}, options, warnings
            )
        elif format == "alembic":
            base = {"filepath": str(target), "selected": selected}
            if frame_range is not None:
                base.update({"start": int(frame_range[0]), "end": int(frame_range[1])})
            _call_with_options(bpy.ops.wm.alembic_export, base, options, warnings)
        else:
            return [], warnings, skill_error("Unsupported export format", f"Format '{format}' is not exportable.")
    except Exception as exc:
        return [], warnings, skill_exception(exc, message=f"Failed to export {target}")
    written = [str(target)] if target.exists() else []
    return written, warnings, None


def _result_for_export(
    label: str, target: Path, written: list[str], warnings: list[str], options: dict[str, Any]
) -> dict:
    return skill_success(
        label,
        filepath=str(target),
        written_files=written,
        warnings=warnings,
        normalized_options=options,
        prompt="Use import_file or downstream validation tools to inspect exported data.",
    )


def import_file(
    path: str,
    format: str | None = None,  # noqa: A002
    collection_name: str | None = None,
    options: Mapping[str, Any] | None = None,
) -> dict:
    """Import an FBX or OBJ file with Blender-native operators."""
    opts, error = _mapping(options, "options")
    if error:
        return error
    target, error = _path(path, must_exist=True)
    if error:
        return error
    format_key, error = _format_from_path(target, format)
    if error:
        return error
    if format_key not in _IMPORT_FORMATS:
        return skill_error("Unsupported import format", f"Format '{format_key}' is not importable.")
    try:
        import bpy

        imported, warnings, error = _import_by_format(bpy, target, format_key, opts)
        if error:
            return error
        if collection_name and imported:
            collection = bpy.data.collections.get(collection_name) or bpy.data.collections.new(collection_name)
            try:
                bpy.context.scene.collection.children.link(collection)
            except Exception:
                pass
            for name in imported:
                obj = bpy.data.objects.get(name)
                if obj is not None:
                    try:
                        collection.objects.link(obj)
                    except Exception:
                        pass
        return skill_success(
            f"Imported {format_key.upper()}: {target}",
            filepath=str(target),
            format=format_key,
            collection_name=collection_name,
            imported_object_names=imported,
            imported_count=len(imported),
            warnings=warnings,
            normalized_options=opts,
            prompt="Use scene or object tools to inspect imported objects.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to import {target}")


def import_fbx(path: str, options: Mapping[str, Any] | None = None) -> dict:
    """Import an FBX file."""
    return import_file(path=path, format="fbx", options=options)


def import_obj(path: str, options: Mapping[str, Any] | None = None) -> dict:
    """Import an OBJ file."""
    return import_file(path=path, format="obj", options=options)


def export_file(
    path: str,
    format: str,  # noqa: A002
    object_names: Sequence[str] | None = None,
    options: Mapping[str, Any] | None = None,
    frame_range: Sequence[int] | None = None,
) -> dict:
    """Export the current scene or selected objects."""
    opts, error = _mapping(options, "options")
    if error:
        return error
    target, error = _path(path, create_parent=True)
    if error:
        return error
    format_key, error = _format_from_path(target, format)
    if error:
        return error
    if format_key not in _EXPORT_FORMATS:
        return skill_error("Unsupported export format", f"Format '{format_key}' is not exportable.")
    if frame_range is not None:
        if isinstance(frame_range, (str, bytes)) or len(frame_range) != 2 or int(frame_range[0]) > int(frame_range[1]):
            return skill_error("Invalid frame_range", "frame_range must contain [start, end] with start <= end.")
    try:
        import bpy

        written, warnings, error = _export_by_format(bpy, target, format_key, object_names, opts, frame_range)
        if error:
            return error
        return _result_for_export(f"Exported {format_key.upper()}: {target}", target, written, warnings, opts)
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to export {target}")


def export_fbx(path: str, object_names: Sequence[str] | None = None, options: Mapping[str, Any] | None = None) -> dict:
    """Export FBX."""
    return export_file(path=path, format="fbx", object_names=object_names, options=options)


def export_obj(path: str, object_names: Sequence[str] | None = None, options: Mapping[str, Any] | None = None) -> dict:
    """Export OBJ."""
    return export_file(path=path, format="obj", object_names=object_names, options=options)


def export_gltf(path: str, object_names: Sequence[str] | None = None, options: Mapping[str, Any] | None = None) -> dict:
    """Export glTF or GLB."""
    return export_file(path=path, format="gltf", object_names=object_names, options=options)


def export_usd(path: str, object_names: Sequence[str] | None = None, options: Mapping[str, Any] | None = None) -> dict:
    """Export USD."""
    return export_file(path=path, format="usd", object_names=object_names, options=options)


def export_alembic(
    path: str,
    object_names: Sequence[str] | None = None,
    frame_range: Sequence[int] | None = None,
    options: Mapping[str, Any] | None = None,
) -> dict:
    """Export Alembic."""
    return export_file(path=path, format="alembic", object_names=object_names, options=options, frame_range=frame_range)


def _get_store(scene: Any) -> dict[str, Any]:
    raw = scene.get(_PRESET_STORE_KEY, "{}") if callable(getattr(scene, "get", None)) else "{}"
    if isinstance(raw, dict):
        return dict(raw)
    try:
        payload = json.loads(raw)
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _save_store(scene: Any, store: dict[str, Any]) -> None:
    scene[_PRESET_STORE_KEY] = json.dumps(store, sort_keys=True)


def list_export_presets() -> dict:
    """List scene-stored export presets."""
    try:
        import bpy

        store = _get_store(bpy.context.scene)
        presets = [
            {"name": name, "format": data.get("format"), "option_count": len(data.get("options", {}))}
            for name, data in sorted(store.items())
        ]
        return skill_success(
            f"Found {len(presets)} export preset(s)",
            presets=presets,
            count=len(presets),
            prompt="Use load_export_preset to inspect options or batch_export to apply a preset.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message="Failed to list export presets")


def save_export_preset(name: str, format: str, options: Mapping[str, Any]) -> dict:  # noqa: A002
    """Save a scene-stored export preset."""
    if not name or not name.strip():
        return skill_error("Invalid name", "name must be a non-empty preset name.")
    opts, error = _mapping(options, "options")
    if error:
        return error
    format_key = format.lower()
    if format_key not in _EXPORT_FORMATS:
        return skill_error("Unsupported export format", f"Format '{format_key}' is not exportable.")
    try:
        import bpy

        store = _get_store(bpy.context.scene)
        store[name] = {"name": name, "format": format_key, "options": opts}
        _save_store(bpy.context.scene, store)
        return skill_success(
            f"Saved export preset {name}",
            name=name,
            format=format_key,
            normalized_options=opts,
            preset_count=len(store),
            prompt="Use batch_export with preset_name to reuse these options.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to save export preset {name}")


def load_export_preset(name: str) -> dict:
    """Load a scene-stored export preset."""
    try:
        import bpy

        store = _get_store(bpy.context.scene)
        preset = store.get(name)
        if preset is None:
            return skill_error(f"Preset not found: {name}", f"No export preset named '{name}'.")
        return skill_success(
            f"Loaded export preset {name}",
            name=name,
            format=preset.get("format"),
            normalized_options=preset.get("options", {}),
            prompt="Use batch_export or a format-specific export tool with these options.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to load export preset {name}")


def delete_export_preset(name: str) -> dict:
    """Delete a scene-stored export preset."""
    try:
        import bpy

        store = _get_store(bpy.context.scene)
        if name not in store:
            return skill_error(f"Preset not found: {name}", f"No export preset named '{name}'.")
        del store[name]
        _save_store(bpy.context.scene, store)
        return skill_success(
            f"Deleted export preset {name}",
            name=name,
            preset_count=len(store),
            prompt="Use list_export_presets to inspect remaining presets.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to delete export preset {name}")


def batch_export(items: Sequence[Mapping[str, Any]], preset_name: str | None = None) -> dict:
    """Run multiple exports with optional preset options."""
    if isinstance(items, (str, bytes)) or not items:
        return skill_error("Invalid items", "items must be a non-empty list of export item objects.")
    try:
        import bpy

        preset = {}
        if preset_name:
            store = _get_store(bpy.context.scene)
            preset = store.get(preset_name)
            if preset is None:
                return skill_error(f"Preset not found: {preset_name}", f"No export preset named '{preset_name}'.")
        results = []
        written_files = []
        warnings = []
        for item in items:
            if not isinstance(item, Mapping):
                return skill_error("Invalid batch item", "Every batch export item must be an object.")
            path = item.get("path")
            if not path:
                return skill_error("Invalid batch item", "Every batch export item must include a non-empty path.")
            format_key = str(item.get("format") or preset.get("format") or "").lower()
            options = dict(preset.get("options", {}))
            options.update(dict(item.get("options") or {}))
            target, error = _path(str(path), create_parent=True)
            if error:
                return error
            format_key, error = _format_from_path(target, format_key)
            if error:
                return error
            written, item_warnings, error = _export_by_format(
                bpy,
                target,
                format_key,
                item.get("object_names"),
                options,
                item.get("frame_range"),
            )
            if error:
                return error
            written_files.extend(written)
            warnings.extend(item_warnings)
            results.append(
                {"path": str(target), "format": format_key, "written_files": written, "warnings": item_warnings}
            )
        return skill_success(
            f"Batch exported {len(results)} item(s)",
            preset_name=preset_name,
            results=results,
            written_files=written_files,
            warnings=warnings,
            count=len(results),
            prompt="Use file_exists or import_file to validate exported files.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message="Failed to run batch export")


def _camera_info(camera: Any) -> dict[str, Any]:
    data = getattr(camera, "data", None)
    return {
        "camera_name": camera.name,
        "data_name": getattr(data, "name", None),
        "lens": getattr(data, "lens", None),
        "sensor_width": getattr(data, "sensor_width", None),
        "location": [float(value) for value in getattr(camera, "location", [0.0, 0.0, 0.0])],
        "rotation_euler": [float(value) for value in getattr(camera, "rotation_euler", [0.0, 0.0, 0.0])],
    }


def get_shot_info(camera_name: str | None = None, frame_range: Sequence[int] | None = None) -> dict:
    """Return camera, frame-range, and render metadata for shot export."""
    if frame_range is not None:
        if isinstance(frame_range, (str, bytes)) or len(frame_range) != 2 or int(frame_range[0]) > int(frame_range[1]):
            return skill_error("Invalid frame_range", "frame_range must contain [start, end] with start <= end.")
    try:
        import bpy

        scene = bpy.context.scene
        camera = bpy.data.objects.get(camera_name) if camera_name else getattr(scene, "camera", None)
        if camera is None:
            return skill_error(
                "Camera not found",
                f"No camera named '{camera_name}'." if camera_name else "Scene has no active camera.",
            )
        if getattr(camera, "type", None) != "CAMERA":
            return skill_error(f"{camera.name} is not a camera", f"Object type is {getattr(camera, 'type', None)}.")
        frames = list(frame_range) if frame_range else [int(scene.frame_start), int(scene.frame_end)]
        return skill_success(
            f"Shot info for {camera.name}",
            camera=_camera_info(camera),
            frame_range=frames,
            fps=getattr(scene.render, "fps", None),
            resolution=[getattr(scene.render, "resolution_x", None), getattr(scene.render, "resolution_y", None)],
            prompt="Use export_camera to write camera metadata or export_alembic/export_fbx for animated shots.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message="Failed to get shot info")


def export_camera(camera_name: str, path: str, format: str = "json", frame_range: Sequence[int] | None = None) -> dict:  # noqa: A002
    """Write camera and shot metadata to a JSON file."""
    if format.lower() != "json":
        return skill_error("Unsupported camera export format", "Only json camera export is currently supported.")
    target, error = _path(path, create_parent=True)
    if error:
        return error
    try:
        info = get_shot_info(camera_name=camera_name, frame_range=frame_range)
        if not info.get("success"):
            return info
        payload = info["context"]
        target.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        return skill_success(
            f"Exported camera metadata: {target}",
            camera_name=camera_name,
            filepath=str(target),
            format="json",
            written_files=[str(target)],
            shot_info=payload,
            prompt="Use the JSON file with downstream shot, camera, or layout tooling.",
        )
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to export camera metadata to {target}")
