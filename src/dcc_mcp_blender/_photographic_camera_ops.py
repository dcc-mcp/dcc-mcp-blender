"""Physical camera setup and continuous shot animation for Blender."""

from __future__ import annotations

import math
from typing import Any, Iterable, Sequence

from dcc_mcp_core.skill import skill_error, skill_exception, skill_success

from dcc_mcp_blender._animation_ops import action_fcurves

SHOT_TYPES = ("CHARACTER", "WIDE")
INTERPOLATIONS = ("BEZIER", "LINEAR", "CONSTANT")
LENS_MIN = 24.0
LENS_MAX = 85.0
SENSOR_WIDTH = 36.0
CAMERA_HEIGHT_MIN_CM = 1.0
CAMERA_HEIGHT_MAX_CM = 8.0
CHARACTER_FSTOP_MIN = 2.8
CHARACTER_FSTOP_MAX = 5.6
WIDE_FSTOP = 11.0


def _finite_number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise ValueError(f"{label} must be a finite number")
    return float(value)


def _vector(value: Sequence[Any], label: str) -> list[float]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence) or len(value) != 3:
        raise ValueError(f"{label} must contain exactly three finite numbers")
    return [_finite_number(component, f"{label}[{index}]") for index, component in enumerate(value)]


def _normalise_shot_type(value: str) -> str:
    shot_type = str(value or "CHARACTER").strip().upper()
    if shot_type not in SHOT_TYPES:
        raise ValueError("shot_type must be CHARACTER or WIDE")
    return shot_type


def _normalise_interpolation(value: str) -> str:
    interpolation = str(value or "BEZIER").strip().upper()
    if interpolation not in INTERPOLATIONS:
        raise ValueError("interpolation must be BEZIER, LINEAR, or CONSTANT")
    return interpolation


def _validate_fstop(shot_type: str, aperture_fstop: Any) -> float:
    fstop = _finite_number(aperture_fstop, "aperture_fstop")
    if shot_type == "CHARACTER" and not CHARACTER_FSTOP_MIN <= fstop <= CHARACTER_FSTOP_MAX:
        raise ValueError("character aperture_fstop must be between 2.8 and 5.6")
    if shot_type == "WIDE" and not math.isclose(fstop, WIDE_FSTOP, abs_tol=1e-6):
        raise ValueError("wide establishing shots require aperture_fstop 11.0")
    return fstop


def _camera_object(bpy: Any, camera_name: str) -> tuple[Any | None, dict | None]:
    obj = bpy.data.objects.get(camera_name)
    if obj is None:
        return None, skill_error("Camera not found", f"No object named '{camera_name}' exists.")
    if getattr(obj, "type", None) != "CAMERA":
        return None, skill_error("Object is not a camera", f"'{camera_name}' has type {getattr(obj, 'type', None)}.")
    return obj, None


def _focus_object(bpy: Any, focus_object: str | None) -> tuple[Any | None, dict | None]:
    if not focus_object:
        return None, None
    obj = bpy.data.objects.get(focus_object)
    if obj is None:
        return None, skill_error("Focus object not found", f"No object named '{focus_object}' exists.")
    return obj, None


def _camera_state(obj: Any) -> dict[str, Any]:
    data = obj.data
    dof = getattr(data, "dof", None)
    return {
        "camera_type": getattr(data, "type", None),
        "lens": getattr(data, "lens", None),
        "sensor_width": getattr(data, "sensor_width", None),
        "location": list(getattr(obj, "location", ())),
        "dof_enabled": getattr(dof, "use_dof", None),
        "aperture_fstop": getattr(dof, "aperture_fstop", None),
        "aperture_blades": getattr(dof, "aperture_blades", None),
        "aperture_ratio": getattr(dof, "aperture_ratio", None),
        "focus_object": getattr(getattr(dof, "focus_object", None), "name", None),
        "focus_distance": getattr(dof, "focus_distance", None),
    }


def _set_location_z(obj: Any, value: float) -> None:
    location = obj.location
    if hasattr(location, "z"):
        location.z = value
    else:
        location[2] = value


def _snapshot_camera(obj: Any) -> list[tuple[Any, str, Any]]:
    data = obj.data
    dof = getattr(data, "dof", None)
    snapshot = [(data, "type", data.type), (data, "lens", data.lens), (data, "sensor_width", data.sensor_width)]
    snapshot.append((obj, "location", list(obj.location)))
    if dof is not None:
        for attribute in (
            "use_dof",
            "aperture_fstop",
            "aperture_blades",
            "aperture_ratio",
            "focus_object",
            "focus_distance",
        ):
            if hasattr(dof, attribute):
                snapshot.append((dof, attribute, getattr(dof, attribute)))
    return snapshot


def _restore(snapshot: Iterable[tuple[Any, str, Any]]) -> None:
    for owner, attribute, value in snapshot:
        try:
            setattr(owner, attribute, value)
        except Exception:
            pass


def configure_photographic_camera(
    camera_name: str,
    shot_type: str = "CHARACTER",
    lens: float = 50.0,
    aperture_fstop: float | None = None,
    focus_object: str | None = None,
    focus_distance: float | None = None,
    camera_height_cm: float = 4.0,
    floor_z: float = 0.0,
) -> dict:
    """Configure a physical, ground-level camera and its depth of field."""
    try:
        shot = _normalise_shot_type(shot_type)
        focal_length = _finite_number(lens, "lens")
        if not LENS_MIN <= focal_length <= LENS_MAX:
            raise ValueError("lens must be between 24 and 85 millimetres")
        height = _finite_number(camera_height_cm, "camera_height_cm")
        if not CAMERA_HEIGHT_MIN_CM <= height <= CAMERA_HEIGHT_MAX_CM:
            raise ValueError("camera_height_cm must be between 1 and 8")
        ground = _finite_number(floor_z, "floor_z")
        fstop = _validate_fstop(
            shot, aperture_fstop if aperture_fstop is not None else (4.0 if shot == "CHARACTER" else 11.0)
        )
        if focus_distance is not None:
            focus = _finite_number(focus_distance, "focus_distance")
            if focus <= 0:
                raise ValueError("focus_distance must be greater than zero")
        else:
            focus = None

        import bpy

        obj, error = _camera_object(bpy, camera_name)
        if error:
            return error
        focus_obj, error = _focus_object(bpy, focus_object)
        if error:
            return error
        data = obj.data
        dof = getattr(data, "dof", None)
        if dof is None:
            return skill_error("Depth of field unavailable", "The camera data does not expose camera.dof.")
        snapshot = _snapshot_camera(obj)
        try:
            for owner, attribute, value in snapshot:
                if owner is data and attribute in {"type", "lens", "sensor_width"} and not hasattr(owner, attribute):
                    raise AttributeError(f"Camera data does not expose {attribute}")
            data.type = "PERSP"
            data.lens = focal_length
            data.sensor_width = SENSOR_WIDTH
            _set_location_z(obj, ground + height / 100.0)
            dof.use_dof = True
            dof.aperture_fstop = fstop
            dof.aperture_blades = 0
            dof.aperture_ratio = 1.0
            dof.focus_object = focus_obj
            if focus is not None:
                dof.focus_distance = focus
        except Exception as exc:
            _restore(snapshot)
            return skill_error("Photographic camera application failed", str(exc), camera_name=camera_name)

        state = _camera_state(obj)
        if (
            not math.isclose(float(state["sensor_width"]), SENSOR_WIDTH, abs_tol=1e-6)
            or state["dof_enabled"] is not True
        ):
            _restore(snapshot)
            return skill_error(
                "Photographic camera readback mismatch", "The camera did not retain the requested physical settings."
            )
        if not math.isclose(float(state["location"][2]), ground + height / 100.0, abs_tol=1e-6):
            _restore(snapshot)
            return skill_error(
                "Photographic camera readback mismatch", "The camera height did not retain the requested floor offset."
            )

        return skill_success(
            f"Photographic camera configured: {camera_name}",
            camera_name=camera_name,
            shot_type=shot,
            camera=state,
            physical_contract={
                "sensor_width_mm": SENSOR_WIDTH,
                "lens_range_mm": [LENS_MIN, LENS_MAX],
                "camera_height_cm": [CAMERA_HEIGHT_MIN_CM, CAMERA_HEIGHT_MAX_CM],
                "round_aperture": True,
                "focus_object": focus_object,
            },
            prompt="Use animate_photographic_camera for an eased move and validate_photographic_camera before rendering.",
        )
    except ValueError as exc:
        return skill_error("Invalid photographic camera request", str(exc))
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to configure photographic camera: {camera_name}")


def _unwrap_degrees(start: Sequence[float], end: Sequence[float]) -> list[float]:
    result = []
    for start_value, end_value in zip(start, end):
        candidate = float(end_value)
        while candidate - start_value > 180.0:
            candidate -= 360.0
        while candidate - start_value < -180.0:
            candidate += 360.0
        result.append(candidate)
    return result


def _set_interpolation(obj: Any, paths: set[str], frames: set[int], interpolation: str) -> None:
    for _, fcurve in action_fcurves(obj):
        if getattr(fcurve, "data_path", None) not in paths:
            continue
        for point in getattr(fcurve, "keyframe_points", ()):
            co = getattr(point, "co", None)
            frame = float(co.x if hasattr(co, "x") else co[0]) if co is not None else None
            if frame is not None and any(abs(frame - expected) < 1e-4 for expected in frames):
                point.interpolation = interpolation


def _point_frame(point: Any) -> float | None:
    co = getattr(point, "co", None)
    if co is None:
        return None
    return float(co.x if hasattr(co, "x") else co[0])


def _point_value(point: Any) -> float | None:
    co = getattr(point, "co", None)
    if co is None:
        return None
    return float(co.y if hasattr(co, "y") else co[1])


def _snapshot_animation_keys(obj: Any, paths: set[str], frames: set[int]) -> list[dict[str, Any]]:
    snapshot = []
    for _, fcurve in action_fcurves(obj):
        path = getattr(fcurve, "data_path", None)
        if path not in paths:
            continue
        array_index = int(getattr(fcurve, "array_index", 0))
        for point in getattr(fcurve, "keyframe_points", ()):
            frame = _point_frame(point)
            value = _point_value(point)
            if frame is None or value is None or not any(abs(frame - expected) < 1e-4 for expected in frames):
                continue
            snapshot.append(
                {
                    "data_path": path,
                    "array_index": array_index,
                    "frame": frame,
                    "value": value,
                    "interpolation": getattr(point, "interpolation", None),
                }
            )
    return snapshot


def _remove_animation_keys(obj: Any, paths: set[str], frames: set[int]) -> None:
    for collection, fcurve in list(action_fcurves(obj)):
        if getattr(fcurve, "data_path", None) not in paths:
            continue
        for point in reversed(list(getattr(fcurve, "keyframe_points", ()))):
            frame = _point_frame(point)
            if frame is None or not any(abs(frame - expected) < 1e-4 for expected in frames):
                continue
            try:
                fcurve.keyframe_points.remove(point, fast=True)
            except TypeError:
                fcurve.keyframe_points.remove(point)
        if not getattr(fcurve, "keyframe_points", ()):
            remove = getattr(collection, "remove", None)
            if callable(remove):
                remove(fcurve)


def _insert_component_keyframe(obj: Any, path: str, array_index: int, frame: float) -> None:
    try:
        obj.keyframe_insert(data_path=path, index=array_index, frame=frame)
    except TypeError:
        obj.keyframe_insert(data_path=path, frame=frame)


def _restore_animation_keys(obj: Any, snapshot: list[dict[str, Any]], paths: set[str], frames: set[int]) -> None:
    _remove_animation_keys(obj, paths, frames)
    for key in snapshot:
        path = key["data_path"]
        values = list(getattr(obj, path))
        values[key["array_index"]] = key["value"]
        setattr(obj, path, values)
        _insert_component_keyframe(obj, path, key["array_index"], key["frame"])
    for _, fcurve in action_fcurves(obj):
        path = getattr(fcurve, "data_path", None)
        if path not in paths:
            continue
        array_index = int(getattr(fcurve, "array_index", 0))
        for point in getattr(fcurve, "keyframe_points", ()):
            frame = _point_frame(point)
            if frame is None:
                continue
            for key in snapshot:
                if key["data_path"] == path and key["array_index"] == array_index and abs(frame - key["frame"]) < 1e-4:
                    if key["interpolation"] is not None:
                        point.interpolation = key["interpolation"]
                    break


def animate_photographic_camera(
    camera_name: str,
    frame_start: int,
    frame_end: int,
    start_location: Sequence[Any],
    end_location: Sequence[Any],
    start_rotation_degrees: Sequence[Any],
    end_rotation_degrees: Sequence[Any],
    interpolation: str = "BEZIER",
    endpoint_extension_frames: int = 1,
) -> dict:
    """Create an eased camera move with continuous, unwrapped Euler rotation."""
    try:
        start_frame = int(frame_start)
        end_frame = int(frame_end)
        if start_frame >= end_frame:
            raise ValueError("frame_start must be less than frame_end")
        extension = int(endpoint_extension_frames)
        if extension < 1:
            raise ValueError("endpoint_extension_frames must be at least 1")
        mode = _normalise_interpolation(interpolation)
        start_position = _vector(start_location, "start_location")
        end_position = _vector(end_location, "end_location")
        start_rotation = _vector(start_rotation_degrees, "start_rotation_degrees")
        end_rotation = _unwrap_degrees(start_rotation, _vector(end_rotation_degrees, "end_rotation_degrees"))
        import bpy

        obj, error = _camera_object(bpy, camera_name)
        if error:
            return error
        snapshot = [
            (obj, "location", list(obj.location)),
            (obj, "rotation_mode", getattr(obj, "rotation_mode", "XYZ")),
            (obj, "rotation_euler", list(obj.rotation_euler)),
        ]
        keyframes = [
            (start_frame - extension, start_position, start_rotation),
            (start_frame, start_position, start_rotation),
            (end_frame, end_position, end_rotation),
            (end_frame + extension, end_position, end_rotation),
        ]
        animated_paths = {"location", "rotation_euler"}
        animated_frames = {frame for frame, _, _ in keyframes}
        animation_snapshot = _snapshot_animation_keys(obj, animated_paths, animated_frames)
        try:
            obj.rotation_mode = "XYZ"
            for frame, position, rotation in keyframes:
                obj.location = position
                obj.rotation_euler = [math.radians(value) for value in rotation]
                if not obj.keyframe_insert(data_path="location", frame=frame):
                    raise RuntimeError(f"Blender rejected location keyframe at frame {frame}")
                if not obj.keyframe_insert(data_path="rotation_euler", frame=frame):
                    raise RuntimeError(f"Blender rejected rotation keyframe at frame {frame}")
            _set_interpolation(obj, {"location", "rotation_euler"}, {frame for frame, _, _ in keyframes}, mode)
        except Exception as exc:
            try:
                _restore_animation_keys(obj, animation_snapshot, animated_paths, animated_frames)
            except Exception:
                pass
            _restore(snapshot)
            return skill_error("Photographic camera animation failed", str(exc), camera_name=camera_name)

        return skill_success(
            f"Photographic camera move animated: {camera_name}",
            camera_name=camera_name,
            frame_start=start_frame,
            frame_end=end_frame,
            keyframe_frames=[frame for frame, _, _ in keyframes],
            interpolation=mode,
            start_rotation_degrees=start_rotation,
            end_rotation_degrees=end_rotation,
            rotation_unwrapped=True,
            camera_shake_added=False,
            prompt="The move has one-frame endpoint extensions for motion blur at cuts. Validate the shot before rendering.",
        )
    except (TypeError, ValueError) as exc:
        return skill_error("Invalid photographic camera animation request", str(exc))
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to animate photographic camera: {camera_name}")


def _animation_report(obj: Any) -> dict[str, Any]:
    curves = []
    noise_modifiers = []
    for _, fcurve in action_fcurves(obj):
        path = getattr(fcurve, "data_path", None)
        if path not in {"location", "rotation_euler"}:
            continue
        for modifier in getattr(fcurve, "modifiers", ()):
            if str(getattr(modifier, "type", "")).upper() == "NOISE":
                noise_modifiers.append({"data_path": path, "array_index": getattr(fcurve, "array_index", 0)})
        points = []
        for point in getattr(fcurve, "keyframe_points", ()):
            co = getattr(point, "co", None)
            if co is None:
                continue
            points.append(
                {
                    "frame": float(co.x if hasattr(co, "x") else co[0]),
                    "value": float(co.y if hasattr(co, "y") else co[1]),
                    "interpolation": getattr(point, "interpolation", None),
                }
            )
        curves.append({"data_path": path, "array_index": getattr(fcurve, "array_index", 0), "points": points})
    return {
        "fcurves": curves,
        "keyframe_count": sum(len(curve["points"]) for curve in curves),
        "noise_modifiers": noise_modifiers,
    }


def validate_photographic_camera(
    camera_name: str,
    shot_type: str = "CHARACTER",
    frame_start: int | None = None,
    frame_end: int | None = None,
    floor_z: float = 0.0,
    require_focus_object: bool = True,
) -> dict:
    """Read-only validation for the physical camera and shot-motion contract."""
    try:
        shot = _normalise_shot_type(shot_type)
        ground = _finite_number(floor_z, "floor_z")
        import bpy

        obj, error = _camera_object(bpy, camera_name)
        if error:
            return error
        state = _camera_state(obj)
        issues = []

        def issue(code: str, field: str, expected: Any, actual: Any, message: str) -> None:
            issues.append(
                {
                    "code": code,
                    "severity": "error",
                    "field": field,
                    "expected": expected,
                    "actual": actual,
                    "message": message,
                }
            )

        if state["camera_type"] != "PERSP":
            issue(
                "CAMERA_PROJECTION_MISMATCH",
                "camera_type",
                "PERSP",
                state["camera_type"],
                "Photographic shots require perspective projection.",
            )
        if state["lens"] is None or not LENS_MIN <= float(state["lens"]) <= LENS_MAX:
            issue("CAMERA_LENS_OUT_OF_RANGE", "lens", [LENS_MIN, LENS_MAX], state["lens"], "Use a 24–85 mm lens.")
        if state["sensor_width"] is None or not math.isclose(float(state["sensor_width"]), SENSOR_WIDTH, abs_tol=1e-6):
            issue(
                "CAMERA_SENSOR_MISMATCH",
                "sensor_width",
                SENSOR_WIDTH,
                state["sensor_width"],
                "The photographic contract uses a 36 mm sensor.",
            )
        height_cm = (float(state["location"][2]) - ground) * 100.0
        if not CAMERA_HEIGHT_MIN_CM <= height_cm <= CAMERA_HEIGHT_MAX_CM:
            issue(
                "CAMERA_HEIGHT_OUT_OF_RANGE",
                "camera_height_cm",
                [CAMERA_HEIGHT_MIN_CM, CAMERA_HEIGHT_MAX_CM],
                height_cm,
                "Place the camera 1–8 cm above the floor.",
            )
        if state["dof_enabled"] is not True:
            issue("CAMERA_DOF_DISABLED", "dof_enabled", True, state["dof_enabled"], "Depth of field must be enabled.")
        if state["aperture_blades"] not in (None, 0):
            issue(
                "CAMERA_APERTURE_NOT_ROUND", "aperture_blades", 0, state["aperture_blades"], "Use a circular aperture."
            )
        if shot == "CHARACTER":
            fstop_ok = (
                state["aperture_fstop"] is not None
                and CHARACTER_FSTOP_MIN <= float(state["aperture_fstop"]) <= CHARACTER_FSTOP_MAX
            )
            expected_fstop = [CHARACTER_FSTOP_MIN, CHARACTER_FSTOP_MAX]
        else:
            fstop_ok = state["aperture_fstop"] is not None and math.isclose(
                float(state["aperture_fstop"]), WIDE_FSTOP, abs_tol=1e-6
            )
            expected_fstop = WIDE_FSTOP
        if not fstop_ok:
            issue(
                "CAMERA_APERTURE_OUT_OF_RANGE",
                "aperture_fstop",
                expected_fstop,
                state["aperture_fstop"],
                "The aperture does not match the shot type.",
            )
        if require_focus_object and not state["focus_object"]:
            issue(
                "CAMERA_FOCUS_OBJECT_MISSING",
                "focus_object",
                "object name",
                None,
                "Focus the character's eyes through a focus object.",
            )

        animation = _animation_report(obj)
        if animation["noise_modifiers"]:
            issue(
                "CAMERA_SHAKE_DETECTED",
                "animation",
                "no Noise modifiers on location or rotation_euler f-curves",
                animation["noise_modifiers"],
                "Remove camera-shake Noise modifiers from the photographic camera.",
            )
        if not animation["fcurves"]:
            issue(
                "CAMERA_ANIMATION_MISSING",
                "animation",
                "location and rotation_euler f-curves",
                [],
                "Every shot requires an eased camera move.",
            )
        if frame_start is not None or frame_end is not None:
            if frame_start is None or frame_end is None or int(frame_start) >= int(frame_end):
                return skill_error(
                    "Invalid frame range", "frame_start and frame_end must be supplied with frame_start < frame_end."
                )
            first = int(frame_start) - 1
            last = int(frame_end) + 1
            required_frames = {first, int(frame_start), int(frame_end), last}
            for path in ("location", "rotation_euler"):
                curves = [curve for curve in animation["fcurves"] if curve["data_path"] == path]
                actual_frames = {point["frame"] for curve in curves for point in curve["points"]}
                missing_frames = sorted(frame for frame in required_frames if frame not in actual_frames)
                if missing_frames:
                    issue(
                        "CAMERA_ENDPOINT_EXTENSION_MISSING",
                        f"{path}_keyframe_frames",
                        sorted(required_frames),
                        sorted(actual_frames),
                        f"Animate {path} at both shot ends and one frame beyond each end.",
                    )
                if path == "rotation_euler" and not curves:
                    issue(
                        "CAMERA_ROTATION_ANIMATION_MISSING",
                        "rotation_euler",
                        "keyframes",
                        [],
                        "Animate rotation_euler for continuous camera motion.",
                    )
            for curve in animation["fcurves"]:
                if curve["data_path"] not in {"location", "rotation_euler"}:
                    continue
                required_points = [point for point in curve["points"] if first <= point["frame"] <= last]
                if required_points and any(point["interpolation"] != "BEZIER" for point in required_points):
                    issue(
                        "CAMERA_EASING_MISSING",
                        f"{curve['data_path']}_interpolation",
                        "BEZIER",
                        sorted({point["interpolation"] for point in required_points}),
                        "Camera motion must use eased Bezier interpolation.",
                    )

        for curve in animation["fcurves"]:
            if curve["data_path"] != "rotation_euler":
                continue
            values = [point["value"] for point in curve["points"]]
            if any(abs(second - first) > math.pi for first, second in zip(values, values[1:])):
                issue(
                    "CAMERA_ROTATION_DISCONTINUITY",
                    "rotation_euler",
                    "adjacent Euler keys within 180 degrees",
                    values,
                    "Keep camera rotation continuous to prevent motion-blur flips.",
                )

        return skill_success(
            f"Photographic camera validation completed: {camera_name}",
            valid=not issues,
            camera_name=camera_name,
            shot_type=shot,
            camera=state,
            animation=animation,
            issues=issues,
        )
    except (TypeError, ValueError) as exc:
        return skill_error("Invalid photographic camera validation request", str(exc))
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to validate photographic camera: {camera_name}")
