"""Shared implementations for expanded Blender animation operation tools."""

from __future__ import annotations

from typing import Any, Sequence

from dcc_mcp_core.skill import skill_error, skill_exception, skill_success

_DEFAULT_DATA_PATHS = ["location", "rotation_euler", "scale"]


def _object_by_name(bpy: Any, object_name: str) -> tuple[Any | None, dict | None]:
    obj = bpy.data.objects.get(object_name)
    if obj is None:
        return None, skill_error(f"Object not found: {object_name}", f"No object named '{object_name}'.")
    return obj, None


def _validate_object_names(object_names: Sequence[str]) -> dict | None:
    if not isinstance(object_names, Sequence) or isinstance(object_names, str) or not object_names:
        return skill_error("Invalid object_names", "object_names must be a non-empty list of object names.")
    if any(not isinstance(name, str) or not name.strip() for name in object_names):
        return skill_error("Invalid object_names", "Every object name must be a non-empty string.")
    return None


def _action(obj: Any) -> Any | None:
    return getattr(getattr(obj, "animation_data", None), "action", None)


def _frame_from_keyframe(point: Any) -> float:
    co = getattr(point, "co", None)
    if co is None:
        return 0.0
    if hasattr(co, "x"):
        return float(co.x)
    return float(co[0])


def _fcurve_matches(fcurve: Any, data_path: str | None) -> bool:
    return data_path is None or getattr(fcurve, "data_path", None) == data_path


def get_keyframes(object_name: str, data_path: str | None = None) -> dict:
    """Return keyframe times grouped by f-curve."""
    try:
        import bpy

        obj, error = _object_by_name(bpy, object_name)
        if error:
            return error
        action = _action(obj)
        curves = []
        keyframe_count = 0
        if action is not None:
            for fcurve in getattr(action, "fcurves", []):
                if not _fcurve_matches(fcurve, data_path):
                    continue
                frames = [_frame_from_keyframe(point) for point in getattr(fcurve, "keyframe_points", [])]
                curves.append(
                    {
                        "data_path": getattr(fcurve, "data_path", ""),
                        "array_index": getattr(fcurve, "array_index", 0),
                        "frames": frames,
                        "count": len(frames),
                    }
                )
                keyframe_count += len(frames)
        return skill_success(
            f"Found {keyframe_count} keyframe(s)",
            object_name=obj.name,
            data_path=data_path,
            action_name=getattr(action, "name", None),
            fcurves=curves,
            keyframe_count=keyframe_count,
            prompt="Use delete_keyframes to remove keys or bake_animation to add sampled keys.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to get keyframes for {object_name}")


def delete_keyframes(
    object_name: str,
    frame_range: Sequence[float] | None = None,
    data_path: str | None = None,
) -> dict:
    """Delete keyframes for an object, optionally filtered by frame range and data path."""
    start = None
    end = None
    if frame_range is not None:
        if isinstance(frame_range, (str, bytes)) or len(frame_range) != 2:
            return skill_error("Invalid frame_range", "frame_range must contain [start, end].")
        start = float(frame_range[0])
        end = float(frame_range[1])
        if start > end:
            return skill_error("Invalid frame_range", "frame_range start must be <= end.")
    try:
        import bpy

        obj, error = _object_by_name(bpy, object_name)
        if error:
            return error
        action = _action(obj)
        deleted = 0
        affected_curves = 0
        if action is not None:
            for fcurve in list(getattr(action, "fcurves", [])):
                if not _fcurve_matches(fcurve, data_path):
                    continue
                removed_on_curve = 0
                for point in list(getattr(fcurve, "keyframe_points", [])):
                    frame = _frame_from_keyframe(point)
                    if start is not None and (frame < start or frame > end):
                        continue
                    try:
                        fcurve.keyframe_points.remove(point, fast=True)
                    except TypeError:
                        fcurve.keyframe_points.remove(point)
                    deleted += 1
                    removed_on_curve += 1
                if removed_on_curve:
                    affected_curves += 1
                    update = getattr(fcurve, "update", None)
                    if callable(update):
                        update()
                if not getattr(fcurve, "keyframe_points", []):
                    remove = getattr(action.fcurves, "remove", None)
                    if callable(remove):
                        remove(fcurve)
        return skill_success(
            f"Deleted {deleted} keyframe(s)",
            object_name=obj.name,
            data_path=data_path,
            frame_range=[start, end] if start is not None else None,
            deleted_count=deleted,
            affected_curve_count=affected_curves,
            prompt="Use get_keyframes to verify the remaining animation keys.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to delete keyframes for {object_name}")


def bake_animation(
    object_names: Sequence[str],
    frame_start: int,
    frame_end: int,
    step: int = 1,
    data_paths: Sequence[str] | None = None,
) -> dict:
    """Sample objects over a frame range by inserting explicit keyframes."""
    names_error = _validate_object_names(object_names)
    if names_error:
        return names_error
    if int(frame_start) > int(frame_end):
        return skill_error("Invalid frame range", "frame_start must be <= frame_end.")
    if int(step) <= 0:
        return skill_error("Invalid step", "step must be a positive integer.")
    paths = list(data_paths or _DEFAULT_DATA_PATHS)
    if any(not isinstance(path, str) or not path.strip() for path in paths):
        return skill_error("Invalid data_paths", "data_paths must contain non-empty strings.")
    try:
        import bpy

        objects = []
        missing = []
        for name in object_names:
            obj, error = _object_by_name(bpy, name)
            if error:
                missing.append(name)
            else:
                objects.append(obj)
        if missing:
            return skill_error("Object not found", f"Missing object(s): {', '.join(missing)}")
        inserted = 0
        frames = list(range(int(frame_start), int(frame_end) + 1, int(step)))
        for frame in frames:
            frame_set = getattr(bpy.context.scene, "frame_set", None)
            if callable(frame_set):
                frame_set(frame)
            else:
                bpy.context.scene.frame_current = frame
            for obj in objects:
                for path in paths:
                    obj.keyframe_insert(data_path=path, frame=frame)
                    inserted += 1
        return skill_success(
            f"Baked {inserted} keyframe sample(s)",
            object_names=[obj.name for obj in objects],
            frame_start=int(frame_start),
            frame_end=int(frame_end),
            step=int(step),
            frames=frames,
            data_paths=paths,
            inserted_count=inserted,
            prompt="Use get_keyframes to inspect baked curves or delete_keyframes to trim them.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message="Failed to bake animation")
